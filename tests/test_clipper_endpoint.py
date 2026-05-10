from __future__ import annotations

from pathlib import Path

import frontmatter as fm
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def clip_vault(tmp_path: Path) -> Path:
    (tmp_path / "raw" / "clips").mkdir(parents=True)
    return tmp_path


def test_clip_saves_to_clips_dir(clip_vault: Path) -> None:
    from second_brain.capture.clipper_endpoint import create_app

    client = TestClient(create_app(clip_vault))
    response = client.post(
        "/clip",
        json={
            "content": "Article text.",
            "url": "https://example.com/article",
            "title": "Test Article",
        },
    )
    assert response.status_code == 200
    saved = Path(response.json()["saved"])
    assert saved.exists()
    content = saved.read_text(encoding="utf-8")
    assert "Article text." in content


def test_clip_frontmatter_valid_yaml(clip_vault: Path) -> None:
    from second_brain.capture.clipper_endpoint import create_app

    client = TestClient(create_app(clip_vault))
    response = client.post(
        "/clip",
        json={"content": "Body.", "url": "https://ex.com/page", "title": "Page: A Guide"},
    )
    assert response.status_code == 200
    post = fm.loads(Path(response.json()["saved"]).read_text(encoding="utf-8"))
    assert post["title"] == "Page: A Guide"
    assert post["type"] == "ref"
    assert "https://ex.com/page" in post["sources"]


def test_clip_minimal_request_no_url_no_title(clip_vault: Path) -> None:
    from second_brain.capture.clipper_endpoint import create_app

    client = TestClient(create_app(clip_vault))
    response = client.post("/clip", json={"content": "Just content."})
    assert response.status_code == 200
    saved = Path(response.json()["saved"])
    assert saved.exists()


def test_clip_empty_content_returns_422(clip_vault: Path) -> None:
    from second_brain.capture.clipper_endpoint import create_app

    client = TestClient(create_app(clip_vault))
    response = client.post("/clip", json={"content": ""})
    assert response.status_code == 422


def test_health_endpoint(clip_vault: Path) -> None:
    from second_brain.capture.clipper_endpoint import create_app

    client = TestClient(create_app(clip_vault))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
