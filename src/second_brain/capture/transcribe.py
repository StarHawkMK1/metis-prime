from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from ..storage.frontmatter import RawSource

log = structlog.get_logger(__name__)

_AUDIO_EXTENSIONS: frozenset[str] = frozenset({".m4a", ".wav", ".mp3", ".ogg", ".flac"})


@dataclass
class TranscriptResult:
    source_path: Path
    transcript_path: Path
    duration_seconds: float
    language: str


# Top-level name so tests can patch `second_brain.capture.transcribe.WhisperModel`
try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None


class TranscribeWorker:
    """Transcribe audio files using faster-whisper and write transcripts to raw/transcripts/."""

    def __init__(self, vault_path: Path, model_size: str = "base") -> None:
        self.vault_path = vault_path
        self.model_size = model_size
        self._model: Any = None

    def _get_model(self) -> Any:
        if WhisperModel is None:
            raise ImportError("faster-whisper is not installed. Run: uv sync --extra capture")
        if self._model is None:
            self._model = WhisperModel(self.model_size)
        return self._model

    def transcribe_file(self, audio_path: Path) -> TranscriptResult:
        model = self._get_model()
        segments, info = model.transcribe(str(audio_path), beam_size=5)
        text = "\n".join(seg.text.strip() for seg in segments)

        transcript_dir = self.vault_path / "raw" / "transcripts"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = transcript_dir / f"{audio_path.stem}.md"

        raw_source = RawSource(
            title=f"Transcript of {audio_path.name}",
            sources=[str(audio_path)],
            body=text,
        )
        transcript_path.write_text(raw_source.to_markdown(), encoding="utf-8")
        log.info("capture.transcribe.done", audio=str(audio_path), transcript=str(transcript_path))

        return TranscriptResult(
            source_path=audio_path,
            transcript_path=transcript_path,
            duration_seconds=float(info.duration),
            language=str(info.language),
        )

    def process_inbox_audio(self) -> list[TranscriptResult]:
        audio_inbox = self.vault_path / "raw" / "inbox" / "audio"
        if not audio_inbox.exists():
            return []
        results = []
        for f in sorted(audio_inbox.iterdir()):
            if f.is_file() and f.suffix.lower() in _AUDIO_EXTENSIONS:
                results.append(self.transcribe_file(f))
        return results
