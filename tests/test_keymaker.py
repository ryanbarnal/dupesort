"""DupeSort Key Maker (packaging/keymaker.py): the portable owner's app that serves the
Key Maker page on 127.0.0.1 and keeps the signing key file and the ledger."""

import importlib.util
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def km(tmp_path, monkeypatch):
    monkeypatch.setenv("DUPESORT_KEYMAKER_CONFIG", str(tmp_path / "config"))
    spec = importlib.util.spec_from_file_location("keymaker", ROOT / "packaging" / "keymaker.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    app = mod.KeyMaker(start_dir=tmp_path / "usb")
    (tmp_path / "usb").mkdir()
    server, url = mod.serve(app, open_browser=False)
    yield mod, app, url, tmp_path
    server.shutdown()


def call(url, path, body=None, token=None, host=None):
    base = url.split("/?")[0]
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST")
    if token:
        req.add_header("X-Token", token)
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_only_this_page_with_its_token(km):
    mod, app, url, _ = km
    code, html = call(url, "/?t=" + app.token)
    assert code == 200 and "window.KEYMAKER" in html and "DupeSort Key Maker" in html
    assert call(url, "/?t=wrong")[0] == 403
    assert call(url, "/api/state", {})[0] == 403  # no token
    assert call(url, "/api/state", {}, token="nope")[0] == 403
    # A web page that points its own host name at 127.0.0.1 is refused too.
    assert call(url, "/api/state", {}, token=app.token, host="evil.example")[0] == 403
    assert call(url, "/api/state", {}, token=app.token)[0] == 200


def test_key_file_and_ledger(km):
    mod, app, url, tmp = km
    t = app.token
    st = json.loads(call(url, "/api/state", {}, token=t)[1])
    assert st["exists"] is False and st["ledger"] == []
    assert st["newKeyFile"] == str(tmp / "usb" / "dupesort-signing-key.txt")

    locked = "DUPESORT-PRIVATE-KEY-1:abc\n"
    code, body = call(url, "/api/key/save", {"text": locked}, token=t)
    assert code == 200
    saved = Path(json.loads(body)["path"])
    assert saved == (tmp / "usb" / "dupesort-signing-key.txt").resolve()
    assert saved.read_text() == locked
    # Never overwritten.
    code, body = call(url, "/api/key/save", {"text": "other"}, token=t)
    assert code == 400 and "already exists" in json.loads(body)["error"]

    st = json.loads(call(url, "/api/state", {}, token=t)[1])
    assert st["exists"] and st["locked"] and st["keyFile"] == str(saved)

    row = {"date": "2026-11-25", "name": "Jane, \"JD\" Doe", "key": "DUPESORT-AAAAA"}
    code, body = call(url, "/api/ledger/add", row, token=t)
    assert code == 200 and json.loads(body)["ledger"] == [row]
    call(url, "/api/ledger/add", {**row, "name": "Ryan"}, token=t)
    ledger = saved.parent / "DupeSort keys ledger.csv"
    text = ledger.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "date,name,key" and len(text.splitlines()) == 3
    assert ledger.read_bytes().startswith(b"\xef\xbb\xbf")  # opens in Excel with accents intact

    # Another key file, pasted as Windows "Copy as path" gives it (in quotes).
    other = tmp / "nas" / "my key.txt"
    other.parent.mkdir()
    other.write_text("00" * 32)
    code, body = call(url, "/api/key/read", {"path": f'"{other}"'}, token=t)
    assert code == 200 and json.loads(body)["text"].strip() == "00" * 32
    assert json.loads(call(url, "/api/state", {}, token=t)[1])["keyFile"] == str(other.resolve())
    assert call(url, "/api/key/read", {"path": str(tmp / "missing.txt")}, token=t)[0] == 400


def test_page_in_package_and_no_third_party_imports():
    """The program uses only the standard library, so it builds into one portable file."""
    import ast
    import sys

    tree = ast.parse((ROOT / "packaging" / "keymaker.py").read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    names.discard("__future__")
    assert names <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)
    assert (ROOT / "packaging" / "DupeSort Key Maker.html").is_file()
