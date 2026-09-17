from __future__ import annotations

from pathlib import Path


class SpeechAdapter:
    def transcribe(self, audio_path: Path) -> str:
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Local speech engine is not installed. Install faster-whisper and ffmpeg to enable voice transcription."
            ) from exc

        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_path))
        return " ".join(segment.text.strip() for segment in segments).strip()
