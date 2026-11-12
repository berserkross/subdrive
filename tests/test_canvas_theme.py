"""组织外观 canvas 扩展与旧包兼容回归，使用隔离 stub 数据。"""
import os
from pathlib import Path
import sys
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="subdrive-canvas-theme-")
os.environ["SEAFILE_MODE"] = "stub"
os.environ["CALIBRATE_INTERVAL_SECONDS"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    response = client.post("/api/auth/register", json={"username":"canvasowner","password":"canvas-test-only"})
    assert response.status_code == 200, response.text
    headers = {"Authorization": "Bearer " + response.json()["token"]}
    canvas = {"v":1,"width":1000,"height":1200,"snap":False,
              "blocks":{"scope":{"x":37,"y":120,"w":240,"h":40}}, "stickers":[]}
    package = {"look":{"blocks":{"scope":{"visible":True,"order":0}}},"theme":"auto","accent":"","canvas":canvas}
    assert client.put("/api/admin/theme", json=package, headers=headers).status_code == 200
    assert client.get("/api/theme/org", headers=headers).json()["theme"]["canvas"] == canvas
    print("PASS canvas publish/read round trip")
    package.pop("canvas")
    assert client.put("/api/admin/theme", json=package, headers=headers).status_code == 200
    assert "canvas" not in client.get("/api/theme/org", headers=headers).json()["theme"]
    print("PASS legacy package replaces previous canvas")
    assert client.put("/api/admin/theme", json=package).status_code == 401
    print("PASS authentication preserved")
