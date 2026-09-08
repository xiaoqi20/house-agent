import base64

from fastapi.testclient import TestClient

from rentgraph.main import app

from .test_analyze import SAMPLE

# 1x1 png
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def test_image_upload_archives_and_serves() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/v1/contracts/upload", files={"file": ("房东拍的条款.png", PNG, "image/png")})
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["source_type"] == "image"
        assert data["storage_key"]
        assert "OCR" in (data["error"] or "")
        cid = data["id"]

        got = client.get(f"/api/v1/contracts/{cid}/file")
        assert got.status_code == 200
        assert got.content == PNG


def test_text_upload_stores_file() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/v1/contracts/upload", files={"file": ("合同.txt", SAMPLE.encode(), "text/plain")})
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["source_type"] == "txt"
        assert data["storage_key"]
        got = client.get(f"/api/v1/contracts/{data['id']}/file")
        assert got.status_code == 200
        assert "第八条" in got.text


def test_bad_extension_rejected() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/v1/contracts/upload", files={"file": ("doc.docx", b"x" * 10, "application/octet-stream")})
        assert resp.status_code == 415
