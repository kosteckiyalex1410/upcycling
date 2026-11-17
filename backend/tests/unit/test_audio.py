"""Audio verification (ADR-0007) against real browser recordings and crafted edge cases."""

from pathlib import Path

import pytest

from app.api.v1.voice_notes import _byte_range
from app.domain.media import RejectionReason
from app.infrastructure.audio import AudioRejected, probe_audio, sniff_audio_type

AUDIO = Path(__file__).parents[1] / "fixtures" / "audio"


def _read(name: str) -> bytes:
    return (AUDIO / name).read_bytes()


@pytest.mark.parametrize(
    ("name", "content_type", "codec", "seconds"),
    [
        # Safari/iOS MediaRecorder: fragmented MP4 (ftyp, moov, moof/mdat pairs), AAC.
        ("webkit-recording.mp4", "audio/mp4", "aac", 2.39),
        # Chrome MediaRecorder: WebM/Opus with unknown-size segment and no duration header.
        ("chromium-recording.webm", "audio/webm", "opus", 2.46),
        # Ordinary (non-fragmented) M4A, moov first and moov last.
        ("voice-memo.m4a", "audio/mp4", "aac", 2.52),
        ("moov-at-end.m4a", "audio/mp4", "aac", 2.02),
    ],
)
def test_browser_recordings_are_accepted_with_their_real_duration(
    name: str, content_type: str, codec: str, seconds: float
) -> None:
    info = probe_audio(_read(name))
    assert (info.content_type, info.codec) == (content_type, codec)
    assert info.duration_ms == pytest.approx(seconds * 1000, abs=60)


def test_duration_is_measured_not_trusted_from_headers() -> None:
    # 306 s of audio: reported correctly so the service can reject it as too long.
    assert probe_audio(_read("too-long.webm")).duration_ms == pytest.approx(306_000, abs=100)


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("video.mp4", RejectionReason.UNSUPPORTED_MEDIA_TYPE),  # has a video track
        ("video.webm", RejectionReason.UNSUPPORTED_MEDIA_TYPE),
        ("mp3-in-mp4.mp4", RejectionReason.UNSUPPORTED_MEDIA_TYPE),  # codec not AAC/Opus
        ("vorbis.webm", RejectionReason.UNSUPPORTED_MEDIA_TYPE),
        ("speech.wav", RejectionReason.UNSUPPORTED_MEDIA_TYPE),  # container not accepted
        ("truncated.mp4", RejectionReason.INVALID_AUDIO),  # interrupted upload/recording
        ("truncated.webm", RejectionReason.INVALID_AUDIO),
    ],
)
def test_unsupported_and_broken_files_are_rejected(name: str, reason: RejectionReason) -> None:
    with pytest.raises(AudioRejected) as caught:
        probe_audio(_read(name))
    assert caught.value.reason == reason


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\x00\x00\x00\x08ftyp",  # header only
        b"\x1a\x45\xdf\xa3\x80",  # empty EBML header, nothing else
        _read("webkit-recording.mp4")[:600],  # moov cut off
        b"\x00\x00\x00\x10ftypM4A \x00\x00\x00\x00" + b"\xff" * 64,  # garbage boxes
    ],
)
def test_malformed_input_never_crashes(data: bytes) -> None:
    with pytest.raises(AudioRejected):
        probe_audio(data)


def test_sniffing() -> None:
    assert sniff_audio_type(_read("webkit-recording.mp4")[:16]) == "audio/mp4"
    assert sniff_audio_type(_read("chromium-recording.webm")[:16]) == "audio/webm"
    assert sniff_audio_type(b"RIFF....WAVE") is None


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("bytes=0-1", (0, 1)),
        ("bytes=0-", (0, 99)),
        ("bytes=90-200", (90, 99)),
        ("bytes=-10", (90, 99)),
        ("bytes=-500", (0, 99)),
        ("bytes=0-1,5-6", None),  # multiple ranges: whole file
        ("items=0-1", None),
    ],
)
def test_byte_ranges(header: str | None, expected: tuple[int, int] | None) -> None:
    assert _byte_range(header, 100) == expected


@pytest.mark.parametrize("header", ["bytes=100-", "bytes=5-2", "bytes=-0"])
def test_unsatisfiable_byte_ranges(header: str) -> None:
    with pytest.raises(ValueError, match="range"):
        _byte_range(header, 100)
