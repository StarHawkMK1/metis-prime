from __future__ import annotations

from pathlib import Path

import pytest
from watchdog.events import FileCreatedEvent, FileMovedEvent

from second_brain.capture.watcher import InboxHandler, _is_sensitive_path


def test_handler_copies_md_file(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    src = tmp_path / "note.md"
    src.write_text("hello", encoding="utf-8")

    handler = InboxHandler(inbox_path=inbox, extensions={".md"})
    handler.on_created(FileCreatedEvent(str(src)))

    assert (inbox / "note.md").exists()
    assert (inbox / "note.md").read_text(encoding="utf-8") == "hello"


def test_handler_ignores_unknown_extension(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    src = tmp_path / "script.py"
    src.write_text("code", encoding="utf-8")

    handler = InboxHandler(inbox_path=inbox, extensions={".md"})
    handler.on_created(FileCreatedEvent(str(src)))

    assert not (inbox / "script.py").exists()


def test_handler_routes_audio_to_audio_subdir(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    audio_inbox = inbox / "audio"
    audio_inbox.mkdir(parents=True)
    src = tmp_path / "memo.m4a"
    src.write_bytes(b"audio data")

    handler = InboxHandler(inbox_path=inbox, extensions={".md", ".m4a"})
    handler.on_created(FileCreatedEvent(str(src)))

    assert (audio_inbox / "memo.m4a").exists()
    assert not (inbox / "memo.m4a").exists()


def test_handler_deduplicates_name_collision(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "note.md").write_text("existing", encoding="utf-8")
    src = tmp_path / "note.md"
    src.write_text("new", encoding="utf-8")

    handler = InboxHandler(inbox_path=inbox, extensions={".md"})
    handler.on_created(FileCreatedEvent(str(src)))

    md_files = list(inbox.glob("note*.md"))
    assert len(md_files) == 2


def test_handler_blocks_sensitive_path(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    sensitive_dir = tmp_path / ".ssh"
    sensitive_dir.mkdir()
    src = sensitive_dir / "id_rsa"
    src.write_text("PRIVATE KEY", encoding="utf-8")

    handler = InboxHandler(inbox_path=inbox, extensions={".md", ""})
    handler.on_created(FileCreatedEvent(str(src)))

    assert not (inbox / "id_rsa").exists()


def test_handler_ignores_directory_events(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    subdir = tmp_path / "subdir"
    subdir.mkdir()

    event = FileCreatedEvent(str(subdir))
    event.is_directory = True  # type: ignore[attr-defined]

    handler = InboxHandler(inbox_path=inbox, extensions={".md"})
    handler.on_created(event)  # Should not raise

    assert list(inbox.iterdir()) == []


@pytest.mark.parametrize(
    "path_str",
    [
        "/home/user/.ssh/id_rsa",
        "C:/Users/me/.aws/credentials",
        "/home/user/secrets/db_password.txt",
        "/home/user/Documents/password_list.md",
    ],
)
def test_is_sensitive_path(path_str: str) -> None:
    assert _is_sensitive_path(Path(path_str)) is True


@pytest.mark.parametrize(
    "path_str",
    [
        "/home/user/Documents/note.md",
        "/home/user/Downloads/article.pdf",
    ],
)
def test_is_not_sensitive_path(path_str: str) -> None:
    assert _is_sensitive_path(Path(path_str)) is False


def test_handler_blocks_symlink(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    real = tmp_path / "real.md"
    real.write_text("real content", encoding="utf-8")
    symlink = tmp_path / "link.md"
    try:
        symlink.symlink_to(real)
    except OSError:
        pytest.skip("symlink creation requires elevated privileges on this platform")

    handler = InboxHandler(inbox_path=inbox, extensions={".md"})
    handler.on_created(FileCreatedEvent(str(symlink)))

    assert not (inbox / "link.md").exists()


def test_handler_on_moved_copies_file(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    src = tmp_path / "tmp_note.md"
    src.write_text("atomic save", encoding="utf-8")
    dest_path = tmp_path / "note.md"
    src.rename(dest_path)

    handler = InboxHandler(inbox_path=inbox, extensions={".md"})
    handler.on_moved(FileMovedEvent(str(src), str(dest_path)))

    assert (inbox / "note.md").exists()
    assert (inbox / "note.md").read_text(encoding="utf-8") == "atomic save"
