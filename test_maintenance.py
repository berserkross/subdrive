"""Maintenance regressions: isolated stub data; no production requests."""
import os
import sqlite3
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient

os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='subdrive-maintenance-')
os.environ['SEAFILE_MODE'] = 'stub'
os.environ['CALIBRATE_INTERVAL_SECONDS'] = '0'
os.environ['SUBDRIVE_ADMIN_USERNAME'] = 'boss'
os.environ.pop('SUBDRIVE_ADMIN_PASSWORD', None)
from app import main as m
from app.storage import StubStorage
from app import storage as sm


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.setattr(m, 'storage', StubStorage(tmp_path / 'files'))
    m.init_db()
    c = TestClient(m.app, raise_server_exceptions=False)
    r = c.post('/api/auth/register', json={'username': 'boss', 'password': 'test-password'})
    assert r.status_code == 200, r.text
    boss = r.json()
    auth = {'Authorization': 'Bearer ' + boss['token']}
    yield c, auth, boss['user']
    c.close()


def invite(c, auth):
    r = c.post('/api/admin/invite-codes', headers=auth, json={'max_uses': 1})
    assert r.status_code == 200
    return r.json()['code']


def register(c, code, name):
    return c.post('/api/auth/register', json={
        'username': name, 'password': 'test-password', 'invite_code': code})


def test_existing_folder_rolls_back_user_and_keeps_invite(env):
    c, auth, _ = env
    code = invite(c, auth)
    m.storage.ensure_user_folder('alice')
    r = register(c, code, 'alice')
    assert r.status_code == 409, r.text
    assert not any(u['username'] == 'alice' for u in c.get('/api/admin/users', headers=auth).json())
    assert register(c, code, 'bobby').status_code == 200


def test_single_use_invite_cannot_be_used_during_provisioning(env, monkeypatch):
    c, auth, _ = env
    code = invite(c, auth)
    entered, release = threading.Event(), threading.Event()
    original = m.storage.ensure_user_folder
    def delayed(name):
        if name == 'alice':
            entered.set()
            assert release.wait(10)
        return original(name)
    monkeypatch.setattr(m.storage, 'ensure_user_folder', delayed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(register, c, code, 'alice')
        assert entered.wait(10)
        try:
            second = pool.submit(register, c, code, 'bobby').result(timeout=5)
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
        assert second.status_code == 400, second.text


def test_disabled_owner_is_rejected(env):
    c, auth, owner = env
    r = c.post(f"/api/admin/users/{owner['id']}/disable", headers=auth)
    assert r.status_code in (400, 403), r.text
    assert c.get('/api/auth/me', headers=auth).status_code == 200


def test_admin_cannot_disable_self_or_owner(env):
    c, auth, owner = env
    member = register(c, invite(c, auth), 'alice').json()
    uid = member['user']['id']
    assert c.post(f'/api/admin/users/{uid}/admin', headers=auth, json={'is_admin': True}).status_code == 200
    member_auth = {'Authorization': 'Bearer ' + member['token']}
    for target in [owner['id'], uid]:
        r = c.post(f'/api/admin/users/{target}/disable', headers=member_auth)
        assert r.status_code in (400, 403), r.text


def test_negative_quota_is_rejected(env):
    c, auth, owner = env
    r = c.post(f"/api/admin/users/{owner['id']}/quota", headers=auth, json={'quota_bytes': -1})
    assert r.status_code == 422, r.text


def test_database_context_closes_connection(env):
    with m.get_db() as db:
        assert db.execute('SELECT 1').fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute('SELECT 1')


@pytest.mark.parametrize('filename', ['sample.html', 'sample.svg', 'sample.xml'])
def test_active_content_preview_is_plain_text(env, filename):
    c, auth, _ = env
    payload = b'<script>alert(1)</script>'
    assert c.post('/api/files/upload', headers=auth, files={'file': (filename, payload)}).status_code == 200
    r = c.get('/api/files/preview', params={'path': filename}, headers=auth)
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('text/plain')
    assert r.headers.get('x-content-type-options') == 'nosniff'
    assert r.headers.get('cache-control') == 'no-store'
    assert r.content == payload


def test_empty_file_suffix_range_is_416(env):
    c, auth, _ = env
    assert c.post('/api/files/upload', headers=auth, files={'file': ('empty.jpg', b'')}).status_code == 200
    r = c.get('/api/files/download', params={'path': 'empty.jpg'}, headers={**auth, 'Range': 'bytes=-1'})
    assert r.status_code == 416, r.text
    assert r.headers['content-range'] == 'bytes */0'


def test_missing_upstream_length_is_not_reported_as_zero(env, monkeypatch):
    c, auth, _ = env
    c.post('/api/files/upload', headers=auth, files={'file': ('image.jpg', b'abc')})
    monkeypatch.setattr(m.storage, 'download_iter', lambda *args: (iter([b'abc']), None))
    r = c.get('/api/files/download', params={'path': 'image.jpg'}, headers=auth)
    assert r.status_code == 200
    assert r.content == b'abc'
    assert r.headers.get('content-length') is None


def test_provisioning_failure_releases_reservation(env, monkeypatch):
    c, auth, _ = env
    code = invite(c, auth)
    original = m.storage.ensure_user_folder
    def failed(name):
        if name == 'alice':
            raise RuntimeError('simulated storage adapter failure')
        return original(name)
    monkeypatch.setattr(m.storage, 'ensure_user_folder', failed)
    assert register(c, code, 'alice').status_code == 500
    assert register(c, code, 'bobby').status_code == 200
    assert not any(u['username'] == 'alice' for u in c.get('/api/admin/users', headers=auth).json())


def make_live(handler):
    clients = []
    class Shim:
        Timeout = httpx.Timeout
        def Client(self, **kw):
            client = httpx.Client(transport=httpx.MockTransport(handler), **kw)
            clients.append(client)
            return client
    live = sm.LiveStorage('https://storage.example.test', 'test-only', 'repo')
    live._httpx = Shim()
    return live, clients


def test_live_download_without_content_length():
    def handler(req):
        if req.url.path.startswith('/api2/'):
            return httpx.Response(200, json='https://storage.example.test/file')
        return httpx.Response(200, stream=httpx.ByteStream(b'photo-bytes'))
    live, clients = make_live(handler)
    stream, length = live.download_iter('/alice/photo.jpg')
    assert length is None
    assert b''.join(stream) == b'photo-bytes'
    assert all(c.is_closed for c in clients)


def test_live_download_network_failure_closes_client():
    def handler(req):
        if req.url.path.startswith('/api2/'):
            return httpx.Response(200, json='https://storage.example.test/file')
        raise httpx.ConnectError('simulated network error', request=req)
    live, clients = make_live(handler)
    with pytest.raises(sm.StorageError) as caught:
        live.download_iter('/alice/photo.jpg')
    assert caught.value.status == 503
    assert all(c.is_closed for c in clients)


def test_unexpected_ping_result_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv('SEAFILE_MODE', 'live')
    monkeypatch.setenv('SEAFILE_BASE_URL', 'https://storage.example.test')
    monkeypatch.setenv('SEAFILE_API_TOKEN', 'test-only')
    monkeypatch.setenv('SEAFILE_REPO_ID', 'repo')
    monkeypatch.setattr(sm.LiveStorage, 'ping', lambda self: False)
    with pytest.raises(sm.StorageAuthError):
        sm.make_storage(tmp_path)
