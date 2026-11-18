"""后端冒烟测试：覆盖首页、登录校验、鉴权拦截等核心链路。

运行方式（项目根目录）：
    python -m pytest tests/ -v

说明：测试通过 FastAPI TestClient 在内存中调用应用，不占用 8080 端口；
但模块加载时会读取本地 MySQL（默认 127.0.0.1:3306 / fusionlab），
请先启动 MySQL。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)


def test_home_page_returns_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "FusionLab" in r.text


def test_login_empty_fields_rejected_422():
    r = client.post("/api/auth/login", json={"username": "", "password": ""})
    assert r.status_code == 422


def test_login_wrong_password_rejected_401():
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-pass"})
    assert r.status_code == 401


def test_admin_api_requires_login_401():
    r = client.get("/api/admin/users")
    assert r.status_code == 401


def test_admin_login_succeeds():
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is True
    assert body["token"]
    assert body["user"]["role"] == "admin"
