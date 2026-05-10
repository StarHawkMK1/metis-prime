from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import frontmatter as fm
import pytest

from second_brain.capture.transcribe import TranscribeWorker, TranscriptResult


@pytest.fixture()
def audio_vault(tmp_path: Path) -> Path:
    (tmp_path / "raw" / "inbox" / "audio").mkdir(parents=True)
    (tmp_path / "raw" / "transcripts").mkdir(parents=True)
    return tmp_path


def _make_mock_model(
    text: str = "Hello world.", duration: float = 3.5, lang: str = "en"
) -> MagicMock:
    seg = MagicMock()
    seg.text = text
    info = MagicMock()
    info.duration = duration
    info.language = lang
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([seg], info)
    return mock_model


def test_transcribe_file_creates_transcript(audio_vault: Path) -> None:
    audio = audio_vault / "raw" / "inbox" / "audio" / "memo.wav"
    audio.write_bytes(b"mock audio")

    with patch("second_brain.capture.transcribe.WhisperModel", return_value=_make_mock_model()):
        worker = TranscribeWorker(vault_path=audio_vault, model_size="base")
        result = worker.transcribe_file(audio)

    assert isinstance(result, TranscriptResult)
    assert result.transcript_path.exists()
    content = result.transcript_path.read_text(encoding="utf-8")
    assert "Hello world." in content
    assert result.duration_seconds == pytest.approx(3.5)
    assert result.language == "en"


def test_transcribe_file_frontmatter_is_valid_yaml(audio_vault: Path) -> None:
    audio = audio_vault / "raw" / "inbox" / "audio" / "note.m4a"
    audio.write_bytes(b"mock audio")

    with patch(
        "second_brain.capture.transcribe.WhisperModel", return_value=_make_mock_model("Text.")
    ):
        worker = TranscribeWorker(vault_path=audio_vault)
        result = worker.transcribe_file(audio)

    post = fm.loads(result.transcript_path.read_text(encoding="utf-8"))
    assert post["title"] == "Transcript of note.m4a"
    assert post["type"] == "ref"
    assert post["status"] == "draft"


def test_process_inbox_audio_returns_results(audio_vault: Path) -> None:
    for name in ("a.wav", "b.m4a"):
        (audio_vault / "raw" / "inbox" / "audio" / name).write_bytes(b"mock")

    with patch("second_brain.capture.transcribe.WhisperModel", return_value=_make_mock_model()):
        worker = TranscribeWorker(vault_path=audio_vault)
        results = worker.process_inbox_audio()

    assert len(results) == 2


def test_process_inbox_audio_empty_dir(audio_vault: Path) -> None:
    with patch("second_brain.capture.transcribe.WhisperModel", return_value=_make_mock_model()):
        worker = TranscribeWorker(vault_path=audio_vault)
        results = worker.process_inbox_audio()

    assert results == []
