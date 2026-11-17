"""Voice notes: original audio recordings attached to a garment (ADR-0007).

The recording is evidence and is kept byte-for-byte. Transcripts (Slice 2+) will be
separate records that point at the voice note: machine-generated and expert-corrected
text never replace each other or the audio.
"""

import uuid

# Declared types the client may upload (`MediaRecorder` output, parameters stripped).
# The stored `content_type` is always the container detected from the bytes.
SUPPORTED_AUDIO_TYPES = frozenset({"audio/mp4", "audio/webm"})


def voice_note_staging_key(voice_note_id: uuid.UUID) -> str:
    """Where the browser uploads (presigned PUT); shares the photo staging prefix."""
    return f"uploads/{voice_note_id}"


def voice_note_audio_key(garment_id: uuid.UUID, voice_note_id: uuid.UUID) -> str:
    """Verified original recording, written only by the server, never overwritten."""
    return f"voice-notes/{garment_id}/{voice_note_id}"


def voice_note_keys(garment_id: uuid.UUID, voice_note_id: uuid.UUID) -> list[str]:
    return [voice_note_staging_key(voice_note_id), voice_note_audio_key(garment_id, voice_note_id)]
