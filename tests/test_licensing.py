"""30-day trial, then activation with a signed key."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dupesort import licensing as L

DAY = 86400
T0 = 1_800_000_000.0
SECRET = bytes(range(32))
PUBLIC = L.public_key_of(SECRET).hex()


@pytest.fixture
def signer(monkeypatch):
    monkeypatch.setattr(L, "PUBLIC_KEY", PUBLIC)


def test_rfc8032_vector():
    sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    pk = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    sig = L.sign(sk, b"")
    assert L.public_key_of(sk) == pk
    assert sig.hex().startswith("e5564300c360ac729086e2cc806e828a")
    assert L.verify(pk, b"", sig) and not L.verify(pk, b"x", sig)


def test_trial_counts_down_and_ends():
    assert L.status(T0).days_left == 30  # first run starts the trial
    assert L.status(T0 + 0.5 * DAY).days_left == 30
    assert L.status(T0 + 10 * DAY).days_left == 20
    st = L.status(T0 + 29.9 * DAY)
    assert st.days_left == 1 and st.can_change_files and st.summary() == "Free trial: 1 day left"
    st = L.status(T0 + 30 * DAY)
    assert st.days_left == 0 and not st.can_change_files and st.summary() == "Free trial ended"


def test_setting_the_clock_back_does_not_add_days():
    L.status(T0)
    L.status(T0 + 25 * DAY)
    assert L.status(T0 + 1 * DAY).days_left == 5


def test_trial_survives_one_copy_being_deleted_and_edits_are_caught():
    L.status(T0)
    L.status(T0 + 20 * DAY)
    config, data = L._files()
    config.unlink()  # the other copy still knows when the trial began
    assert L.status(T0 + 20 * DAY).days_left == 10
    rec = json.loads(config.read_text())
    rec["start"] = T0 + 19 * DAY  # moving the start date forward by hand…
    config.write_text(json.dumps(rec))
    data.write_text(json.dumps(rec))
    assert L.status(T0 + 20 * DAY).days_left == 0  # …ends the trial instead


def test_keys(signer):
    key = L.make_key(SECRET, "Jane Doe", "2026-11-24")
    assert key.startswith("DUPESORT-")
    lic = L.read_key("  " + key.lower().replace("-", " ") + "\n")  # as pasted from an email
    assert lic.name == "Jane Doe" and lic.issued == "2026-11-24"
    tampered = key[:-2] + ("AA" if key[-2:] != "AA" else "BB")
    assert L.read_key(tampered) is None
    assert L.read_key(L.make_key(bytes(32), "Jane Doe")) is None  # someone else's signing key
    assert L.read_key("DUPESORT-HELLO") is None and L.read_key("") is None
    assert L.read_key(key, public_hex="") is None


def test_activation_after_the_trial(signer):
    L.status(T0)
    assert not L.status(T0 + 31 * DAY).can_change_files
    ok, msg = L.activate("not a key")
    assert not ok and "isn't valid" in msg
    ok, msg = L.activate(L.make_key(SECRET, "Jane Doe"))
    assert ok and "Jane Doe" in msg
    st = L.status(T0 + 400 * DAY)
    assert st.can_change_files and st.licensed.name == "Jane Doe"
    assert st.summary() == "Licensed to Jane Doe"
    L.deactivate()
    assert not L.status(T0 + 400 * DAY).can_change_files  # the trial doesn't restart


def test_without_a_public_key_nothing_activates(monkeypatch):
    monkeypatch.setattr(L, "PUBLIC_KEY", "")
    ok, msg = L.activate(L.make_key(SECRET, "Jane"))
    assert not ok and "can't check keys" in msg


def test_expired_trial_blocks_changes_until_activated(signer, monkeypatch):
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    from dupesort.gui import license_dialog

    QApplication.instance() or QApplication([])
    L.status(T0)
    monkeypatch.setattr(L.time, "time", lambda: T0 + 40 * DAY)
    shown = []
    monkeypatch.setattr(license_dialog.ActivateDialog, "exec", lambda self: shown.append(self) or 0)
    assert license_dialog.require(None, "move duplicates") is False
    assert "move duplicates" in shown[0].text.text()
    # Entering a key in the dialog activates.
    dlg = license_dialog.ActivateDialog("move duplicates")
    dlg.key.setPlainText(L.make_key(SECRET, "Jane Doe"))
    dlg._activate()
    assert "Thank you" in dlg.message.text()
    assert license_dialog.require(None, "move duplicates") is True


def test_license_tool(tmp_path):
    """`init` creates a signing key and writes its public half into (a copy of) the app;
    `issue` makes keys that the app accepts."""
    root = Path(__file__).resolve().parent.parent
    copy = tmp_path / "repo"
    (copy / "dupesort").mkdir(parents=True)
    (copy / "packaging").mkdir()
    for f in (root / "dupesort").glob("*.py"):
        (copy / "dupesort" / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    src = copy / "dupesort" / "licensing.py"
    src.write_text(src.read_text(encoding="utf-8").replace(
        f'PUBLIC_KEY = "{L.PUBLIC_KEY}"', 'PUBLIC_KEY = ""'), encoding="utf-8")
    tool = copy / "packaging" / "license_tool.py"
    tool.write_text((root / "packaging" / "license_tool.py").read_text(encoding="utf-8"),
                    encoding="utf-8")
    keyfile = tmp_path / "signing-key"
    run = lambda *a: subprocess.run([sys.executable, str(tool), "--key-file", str(keyfile), *a],
                                    capture_output=True, text=True, env={**os.environ})
    out = run("init")
    assert out.returncode == 0, out.stderr
    assert keyfile.exists() and len(keyfile.read_text().strip()) == 64
    public = L.public_key_of(bytes.fromhex(keyfile.read_text().strip())).hex()
    assert f'PUBLIC_KEY = "{public}"' in src.read_text(encoding="utf-8")
    assert run("init").returncode == 0  # running it again is harmless
    out = run("issue", "Jane Doe")
    assert out.returncode == 0, out.stderr
    key = next(line for line in out.stdout.splitlines() if line.startswith("DUPESORT-"))
    assert L.read_key(key, public_hex=public).name == "Jane Doe"
