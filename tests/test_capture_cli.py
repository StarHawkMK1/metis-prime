from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from second_brain.cli import app

runner = CliRunner()


def test_capture_journal_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    (tmp_path / "journal").mkdir()

    with patch("second_brain.capture.journal.generate_daily_journal") as mock_gen:
        mock_gen.return_value = tmp_path / "journal" / "2026" / "2026-05-10.md"
        result = runner.invoke(app, ["capture", "journal", "--date", "2026-05-10"])

    assert result.exit_code == 0
    assert "2026-05-10" in result.output


def test_capture_clip_calls_capture_clipboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    inbox = tmp_path / "raw" / "inbox"
    inbox.mkdir(parents=True)

    dest = inbox / "clip-2026-05-10-120000.md"
    dest.write_text("content", encoding="utf-8")

    with patch("second_brain.capture.clipboard.capture_clipboard", return_value=dest):
        result = runner.invoke(app, ["capture", "clip"])

    assert result.exit_code == 0
    assert "clip-" in result.output


def test_capture_transcribe_single_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from second_brain.capture.transcribe import TranscriptResult

    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    audio = tmp_path / "memo.wav"
    audio.write_bytes(b"mock")
    transcript = tmp_path / "raw" / "transcripts" / "memo.md"
    (tmp_path / "raw" / "transcripts").mkdir(parents=True)
    transcript.write_text("transcript", encoding="utf-8")

    mock_worker = MagicMock()
    mock_worker.transcribe_file.return_value = TranscriptResult(
        source_path=audio,
        transcript_path=transcript,
        duration_seconds=5.0,
        language="en",
    )

    with patch("second_brain.capture.transcribe.TranscribeWorker", return_value=mock_worker):
        result = runner.invoke(app, ["capture", "transcribe", str(audio)])

    assert result.exit_code == 0
    assert "memo.md" in result.output


def test_capture_watch_errors_without_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECOND_BRAIN_VAULT_PATH", str(tmp_path))
    monkeypatch.delenv("SECOND_BRAIN_CAPTURE_WATCH_DIRS", raising=False)
    result = runner.invoke(app, ["capture", "watch"])
    assert result.exit_code != 0
    assert "No watch directories" in result.output
