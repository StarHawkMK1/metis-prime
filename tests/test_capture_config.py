def test_capture_config_defaults() -> None:
    import os

    # Clear any env vars that might interfere
    for k in [
        "SECOND_BRAIN_CAPTURE_WATCH_DIRS",
        "SECOND_BRAIN_CLIPPER_PORT",
        "SECOND_BRAIN_CLIPPER_HOST",
        "SECOND_BRAIN_WHISPER_MODEL_SIZE",
    ]:
        os.environ.pop(k, None)

    from second_brain.config import Settings

    s = Settings()
    assert s.capture_watch_dirs == []
    assert s.clipper_port == 7331
    assert s.clipper_host == "127.0.0.1"
    assert s.whisper_model_size == "base"
    assert ".md" in s.capture_extensions
    assert ".pdf" in s.capture_extensions
    assert ".m4a" in s.capture_extensions
    assert ".wav" in s.capture_extensions
