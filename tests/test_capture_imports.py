def test_watchdog_importable() -> None:
    from watchdog.events import FileSystemEventHandler  # noqa: F401
    from watchdog.observers import Observer  # noqa: F401
