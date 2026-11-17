"""Verifies uploaded voice recordings (ADR-0007). CPU-bound; call off the event loop.

A deliberately small, strict parser for the two containers browsers record with
`MediaRecorder`: MP4 (Safari/iOS: fragmented MP4 with AAC; also AAC or Opus from other
browsers) and WebM (Chrome: Opus, usually without a duration header). It checks the
container structure end to end (a truncated file fails), that there is exactly one audio
track and no video, the codec, and the real duration from the sample/block timing — never
from header fields alone. It does not decode the audio payload.
"""

import itertools
import struct
from dataclasses import dataclass

from app.domain.media import RejectionReason


class AudioRejected(Exception):
    def __init__(self, reason: RejectionReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AudioInfo:
    content_type: str  # detected container: audio/mp4 or audio/webm
    codec: str  # aac or opus
    duration_ms: int


class _Invalid(Exception):
    pass


def sniff_audio_type(head: bytes) -> str | None:
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "audio/mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm"
    return None


def probe_audio(data: bytes) -> AudioInfo:
    """Raises `AudioRejected` unless `data` is a complete, supported audio recording."""
    content_type = sniff_audio_type(data[:16])
    if content_type is None:
        raise AudioRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
    try:
        codec, seconds = _probe_mp4(data) if content_type == "audio/mp4" else _probe_webm(data)
    except AudioRejected:
        raise
    except (_Invalid, struct.error, IndexError, ValueError, ZeroDivisionError) as exc:
        raise AudioRejected(RejectionReason.INVALID_AUDIO) from exc
    if seconds <= 0:
        raise AudioRejected(RejectionReason.INVALID_AUDIO)
    return AudioInfo(content_type=content_type, codec=codec, duration_ms=round(seconds * 1000))


# MP4 / ISO BMFF -----------------------------------------------------------------------------

_U32 = struct.Struct(">I")
_U64 = struct.Struct(">Q")
_I32 = struct.Struct(">i")
# objectTypeIndication values for AAC in the `esds` DecoderConfigDescriptor.
_AAC_OBJECT_TYPES = frozenset({0x40, 0x66, 0x67, 0x68})


def _u32(data: bytes, offset: int) -> int:
    value: int = _U32.unpack_from(data, offset)[0]
    return value


def _u64(data: bytes, offset: int) -> int:
    value: int = _U64.unpack_from(data, offset)[0]
    return value


def _boxes(data: bytes, start: int, end: int) -> list[tuple[bytes, int, int, int]]:
    """Child boxes of [start, end) as (type, box_start, payload_start, box_end). The
    children must tile the range exactly: anything truncated is invalid."""
    boxes = []
    i = start
    while i < end:
        if end - i < 8:
            raise _Invalid("trailing bytes")
        size, kind = _u32(data, i), data[i + 4 : i + 8]
        header = 8
        if size == 1:
            size, header = _u64(data, i + 8), 16
        elif size == 0:
            size = end - i
        if size < header or i + size > end:
            raise _Invalid("box exceeds its parent")
        boxes.append((kind, i, i + header, i + size))
        i += size
    return boxes


def _child(data: bytes, start: int, end: int, kind: bytes) -> tuple[int, int] | None:
    for child_kind, _, payload, box_end in _boxes(data, start, end):
        if child_kind == kind:
            return payload, box_end
    return None


def _require(data: bytes, start: int, end: int, *path: bytes) -> tuple[int, int]:
    for kind in path:
        found = _child(data, start, end, kind)
        if found is None:
            raise _Invalid(f"missing {kind!r}")
        start, end = found
    return start, end


@dataclass(slots=True)
class _Mp4Track:
    track_id: int
    timescale: int
    codec: str
    sample_ticks: int  # from the moov sample table (non-fragmented part)
    sample_count: int
    sample_bytes: int
    default_duration: int = 0  # from mvex/trex, for fragments
    default_size: int = 0


def _mp4_codec(data: bytes, start: int, end: int) -> str:
    """Codec of the first `stsd` sample entry: AAC (`mp4a` + esds) or Opus."""
    payload, stsd_end = start + 8, end  # version/flags + entry_count
    entries = _boxes(data, payload, stsd_end)
    if not entries:
        raise _Invalid("no sample entry")
    kind, _, entry_payload, entry_end = entries[0]
    if kind == b"Opus":
        return "opus"
    if kind != b"mp4a":
        raise AudioRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
    version = struct.unpack_from(">H", data, entry_payload + 8)[0]
    children = entry_payload + 28 + {0: 0, 1: 16, 2: 36}.get(version, 0)
    esds = _child(data, children, entry_end, b"esds")
    if esds is None or _esds_object_type(data, esds[0] + 4, esds[1]) not in _AAC_OBJECT_TYPES:
        raise AudioRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
    return "aac"


def _descriptor(data: bytes, i: int) -> tuple[int, int, int]:
    tag, i, length = data[i], i + 1, 0
    for _ in range(4):
        byte = data[i]
        i += 1
        length = (length << 7) | (byte & 0x7F)
        if not byte & 0x80:
            break
    return tag, i, i + length


def _esds_object_type(data: bytes, start: int, end: int) -> int | None:
    tag, i, es_end = _descriptor(data, start)
    if tag != 0x03 or es_end > end:
        return None
    flags = data[i + 2]
    i += 3
    if flags & 0x80:
        i += 2
    if flags & 0x40:
        i += 1 + data[i]
    if flags & 0x20:
        i += 2
    while i < es_end:
        tag, payload, next_i = _descriptor(data, i)
        if tag == 0x04:
            return data[payload]
        i = next_i
    return None


def _mp4_track(data: bytes, start: int, end: int) -> tuple[bytes, _Mp4Track | None]:
    mdia = _require(data, start, end, b"mdia")
    hdlr = _require(data, *mdia, b"hdlr")
    handler = data[hdlr[0] + 8 : hdlr[0] + 12]
    if handler != b"soun":
        return handler, None
    tkhd = _require(data, start, end, b"tkhd")
    track_id = _u32(data, tkhd[0] + (20 if data[tkhd[0]] == 1 else 12))
    mdhd = _require(data, *mdia, b"mdhd")
    timescale = _u32(data, mdhd[0] + (20 if data[mdhd[0]] == 1 else 12))
    if timescale == 0:
        raise _Invalid("zero timescale")
    stbl = _require(data, *mdia, b"minf", b"stbl")
    codec = _mp4_codec(data, *_require(data, *stbl, b"stsd"))
    stts = _require(data, *stbl, b"stts")
    ticks = count = 0
    for n in range(_u32(data, stts[0] + 4)):
        sample_count, delta = _u32(data, stts[0] + 8 + 8 * n), _u32(data, stts[0] + 12 + 8 * n)
        ticks += sample_count * delta
        count += sample_count
    sample_bytes = 0
    stsz = _child(data, *stbl, b"stsz")
    if stsz is not None:
        uniform, entries = _u32(data, stsz[0] + 4), _u32(data, stsz[0] + 8)
        sample_bytes = (
            uniform * entries
            if uniform
            else sum(_u32(data, stsz[0] + 12 + 4 * n) for n in range(entries))
        )
    return handler, _Mp4Track(track_id, timescale, codec, ticks, count, sample_bytes)


def _apply_trex(data: bytes, start: int, end: int, track: _Mp4Track) -> None:
    for kind, _, payload, _ in _boxes(data, start, end):
        if kind == b"trex" and _u32(data, payload + 4) == track.track_id:
            track.default_duration = _u32(data, payload + 12)
            track.default_size = _u32(data, payload + 16)


@dataclass(frozen=True, slots=True)
class _TrackFragment:
    base: int  # where sample data offsets are counted from
    duration: int  # default sample duration
    size: int  # default sample size


def _tfhd(data: bytes, start: int, moof_start: int, track: _Mp4Track) -> _TrackFragment:
    flags = _u32(data, start) & 0xFFFFFF
    if _u32(data, start + 4) != track.track_id:
        raise _Invalid("fragment for an unknown track")
    i, base = start + 8, moof_start
    duration, size = track.default_duration, track.default_size
    if flags & 0x01:
        base, i = _u64(data, i), i + 8
    if flags & 0x02:
        i += 4
    if flags & 0x08:
        duration, i = _u32(data, i), i + 4
    if flags & 0x10:
        size = _u32(data, i)
    return _TrackFragment(base, duration, size)


def _trun(
    data: bytes, start: int, defaults: _TrackFragment, mdats: list[tuple[int, int]]
) -> tuple[int, int]:
    """(ticks, samples) of one track run; its sample bytes must lie inside an `mdat`."""
    flags = _u32(data, start) & 0xFFFFFF
    samples, j = _u32(data, start + 4), start + 8
    offset = None
    if flags & 0x01:
        offset, j = _I32.unpack_from(data, j)[0], j + 4
    if flags & 0x04:
        j += 4
    ticks = run_bytes = 0
    for _ in range(samples):
        duration, size = defaults.duration, defaults.size
        if flags & 0x100:
            duration, j = _u32(data, j), j + 4
        if flags & 0x200:
            size, j = _u32(data, j), j + 4
        j += (4 if flags & 0x400 else 0) + (4 if flags & 0x800 else 0)
        ticks += duration
        run_bytes += size
    if offset is not None:
        first = defaults.base + offset
        if not any(lo <= first and first + run_bytes <= hi for lo, hi in mdats):
            raise _Invalid("fragment samples outside media data")
    return ticks, samples


def _fragment(
    data: bytes, moof: tuple[int, int, int], track: _Mp4Track, mdats: list[tuple[int, int]]
) -> tuple[int, int, int]:
    """(end time in ticks or -1 without tfdt, sample ticks, sample count) of one `moof`
    given as (box_start, payload_start, box_end)."""
    moof_start, payload, end = moof
    end_time, total_ticks, total_samples = -1, 0, 0
    for kind, _, traf, traf_end in _boxes(data, payload, end):
        if kind != b"traf":
            continue
        defaults = _tfhd(data, _require(data, traf, traf_end, b"tfhd")[0], moof_start, track)
        traf_ticks = 0
        for run_kind, _, trun, _ in _boxes(data, traf, traf_end):
            if run_kind == b"trun":
                ticks, samples = _trun(data, trun, defaults, mdats)
                traf_ticks += ticks
                total_samples += samples
        total_ticks += traf_ticks
        tfdt = _child(data, traf, traf_end, b"tfdt")
        if tfdt is not None:
            version, at = data[tfdt[0]], tfdt[0] + 4
            decode_time = _u64(data, at) if version == 1 else _u32(data, at)
            end_time = max(end_time, decode_time + traf_ticks)
    return end_time, total_ticks, total_samples


def _probe_mp4(data: bytes) -> tuple[str, float]:
    top = _boxes(data, 0, len(data))
    if not top or top[0][0] != b"ftyp":
        raise _Invalid("missing ftyp")
    moovs = [box for box in top if box[0] == b"moov"]
    mdats = [(payload, end) for kind, _, payload, end in top if kind == b"mdat"]
    if len(moovs) != 1 or not mdats:
        raise _Invalid("need one moov and media data")
    _, _, moov, moov_end = moovs[0]
    audio: list[_Mp4Track] = []
    for kind, _, trak, trak_end in _boxes(data, moov, moov_end):
        if kind != b"trak":
            continue
        handler, track = _mp4_track(data, trak, trak_end)
        if handler == b"vide":
            raise AudioRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
        if track is not None:
            audio.append(track)
    if len(audio) != 1:
        raise AudioRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
    track = audio[0]
    if track.sample_bytes > sum(end - start for start, end in mdats):
        raise _Invalid("samples exceed media data")

    mvex = _child(data, moov, moov_end, b"mvex")
    if mvex is not None:
        _apply_trex(data, *mvex, track)
    ticks, samples = track.sample_ticks, track.sample_count
    fragment_end = -1
    for kind, box_start, payload, end in top:
        if kind == b"moof":
            end_time, frag_ticks, frag_samples = _fragment(
                data, (box_start, payload, end), track, mdats
            )
            fragment_end = max(fragment_end, end_time)
            ticks += frag_ticks
            samples += frag_samples
    if samples == 0:
        raise _Invalid("no audio samples")
    return track.codec, max(ticks, fragment_end) / track.timescale


# WebM / Matroska (EBML) ---------------------------------------------------------------------

_EBML = 0x1A45DFA3
_DOC_TYPE = 0x4282
_SEGMENT = 0x18538067
_INFO = 0x1549A966
_TIMECODE_SCALE = 0x2AD7B1
_TRACKS = 0x1654AE6B
_TRACK_ENTRY = 0xAE
_TRACK_NUMBER = 0xD7
_TRACK_TYPE = 0x83
_CODEC_ID = 0x86
_CLUSTER = 0x1F43B675
_CLUSTER_TIMECODE = 0xE7
_SIMPLE_BLOCK = 0xA3
_BLOCK_GROUP = 0xA0
_BLOCK = 0xA1
_BLOCK_DURATION = 0x9B
# Elements that can follow a cluster at segment level; they end an unknown-size cluster.
_SEGMENT_CHILDREN = frozenset(
    {_CLUSTER, _INFO, _TRACKS, 0x1C53BB6B, 0x1254C367, 0x1043A770, 0x1941A469, 0x114D9B74}
)
_AUDIO_TRACK, _VIDEO_TRACK = 2, 1


def _vint_length(first: int, max_length: int) -> int:
    for length in range(1, max_length + 1):
        if first & (0x80 >> (length - 1)):
            return length
    raise _Invalid("bad variable-length integer")


def _element_id(data: bytes, i: int) -> tuple[int, int]:
    length = _vint_length(data[i], 4)
    if i + length > len(data):
        raise _Invalid("truncated id")
    return int.from_bytes(data[i : i + length]), i + length


def _element_size(data: bytes, i: int) -> tuple[int | None, int]:
    """Size and the offset after it; None for "unknown size" (live recordings)."""
    length = _vint_length(data[i], 8)
    if i + length > len(data):
        raise _Invalid("truncated size")
    value = data[i] & (0xFF >> length)
    for byte in data[i + 1 : i + length]:
        value = (value << 8) | byte
    return (None if value == (1 << (7 * length)) - 1 else value), i + length


def _elements(data: bytes, start: int, end: int) -> list[tuple[int, int, int]]:
    """Children of a known-size element as (id, payload_start, payload_end)."""
    children = []
    i = start
    while i < end:
        element, i = _element_id(data, i)
        size, i = _element_size(data, i)
        if size is None or i + size > end:
            raise _Invalid("element exceeds its parent")
        children.append((element, i, i + size))
        i += size
    return children


def _uint(data: bytes, start: int, end: int) -> int:
    if end - start > 8:
        raise _Invalid("integer too long")
    return int.from_bytes(data[start:end])


@dataclass(slots=True)
class _Blocks:
    timestamps: list[int]
    last_duration: int | None = None


def _block(data: bytes, start: int, end: int, cluster_time: int, tracks: set[int]) -> int:
    length = _vint_length(data[start], 8)
    number = data[start] & (0xFF >> length)
    for byte in data[start + 1 : start + length]:
        number = (number << 8) | byte
    if number not in tracks or start + length + 3 > end:
        raise _Invalid("block for an unknown track")
    relative: int = struct.unpack_from(">h", data, start + length)[0]
    return cluster_time + relative


def _cluster(
    data: bytes, i: int, *, end: int | None, tracks: set[int], blocks: _Blocks, segment_end: int
) -> int:
    """Parse one cluster's children from `i`; returns where the cluster ends."""
    cluster_time = 0
    limit = end if end is not None else segment_end
    while i < limit:
        element, payload = _element_id(data, i)
        if end is None and element in _SEGMENT_CHILDREN:
            return i  # unknown-size cluster ends where the next top-level element starts
        size, payload = _element_size(data, payload)
        if size is None or payload + size > limit:
            raise _Invalid("cluster element exceeds the cluster")
        stop = payload + size
        if element == _CLUSTER_TIMECODE:
            cluster_time = _uint(data, payload, stop)
        elif element == _SIMPLE_BLOCK:
            blocks.timestamps.append(_block(data, payload, stop, cluster_time, tracks))
        elif element == _BLOCK_GROUP:
            for child, child_start, child_end in _elements(data, payload, stop):
                if child == _BLOCK:
                    blocks.timestamps.append(
                        _block(data, child_start, child_end, cluster_time, tracks)
                    )
                elif child == _BLOCK_DURATION:
                    blocks.last_duration = _uint(data, child_start, child_end)
        i = stop
    return limit


def _webm_tracks(data: bytes, start: int, end: int) -> set[int]:
    audio: set[int] = set()
    for element, entry, entry_end in _elements(data, start, end):
        if element != _TRACK_ENTRY:
            continue
        fields = {e: (s, t) for e, s, t in _elements(data, entry, entry_end)}
        kind = _uint(data, *fields[_TRACK_TYPE]) if _TRACK_TYPE in fields else None
        codec = data[slice(*fields[_CODEC_ID])].rstrip(b"\0") if _CODEC_ID in fields else b""
        if kind != _AUDIO_TRACK or codec != b"A_OPUS" or _TRACK_NUMBER not in fields:
            raise AudioRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
        audio.add(_uint(data, *fields[_TRACK_NUMBER]))
    if len(audio) != 1:
        raise AudioRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
    return audio


def _webm_header(data: bytes) -> int:
    """Checks the EBML header (DocType webm); returns where the segment starts."""
    element, i = _element_id(data, 0)
    size, i = _element_size(data, i)
    if element != _EBML or size is None:
        raise _Invalid("missing EBML header")
    header = {e: (s, t) for e, s, t in _elements(data, i, i + size)}
    if _DOC_TYPE not in header or data[slice(*header[_DOC_TYPE])].rstrip(b"\0") != b"webm":
        raise AudioRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
    return i + size


def _webm_duration(blocks: _Blocks, scale: int) -> float:
    stamps = sorted(blocks.timestamps)
    if not stamps or scale == 0:
        raise _Invalid("no audio blocks")
    gaps = sorted(b - a for a, b in itertools.pairwise(stamps) if b > a)
    last = blocks.last_duration or (gaps[len(gaps) // 2] if gaps else round(20e6 / scale))
    return (stamps[-1] - stamps[0] + last) * scale / 1e9


def _probe_webm(data: bytes) -> tuple[str, float]:
    element, i = _element_id(data, _webm_header(data))
    segment_size, i = _element_size(data, i)
    if element != _SEGMENT:
        raise _Invalid("missing segment")
    segment_end = len(data) if segment_size is None else i + segment_size
    if segment_end > len(data):
        raise _Invalid("truncated segment")

    scale, tracks, blocks = 1_000_000, set[int](), _Blocks(timestamps=[])
    while i < segment_end:
        element, payload = _element_id(data, i)
        size, payload = _element_size(data, payload)
        if element == _CLUSTER:
            if not tracks:
                raise _Invalid("cluster before tracks")
            end = None if size is None else payload + size
            if end is not None and end > segment_end:
                raise _Invalid("truncated cluster")
            i = _cluster(
                data, payload, end=end, tracks=tracks, blocks=blocks, segment_end=segment_end
            )
            continue
        if size is None or payload + size > segment_end:
            raise _Invalid("segment element exceeds the segment")
        if element == _INFO:
            for child, start, stop in _elements(data, payload, payload + size):
                if child == _TIMECODE_SCALE:
                    scale = _uint(data, start, stop)
        elif element == _TRACKS:
            tracks = _webm_tracks(data, payload, payload + size)
        i = payload + size

    if not tracks:
        raise AudioRejected(RejectionReason.UNSUPPORTED_MEDIA_TYPE)
    return "opus", _webm_duration(blocks, scale)
