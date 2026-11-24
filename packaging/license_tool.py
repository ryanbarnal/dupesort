"""Make DupeSort license keys.

Once, to create your signing key (kept outside the repository) and put its public half
into the app:

    python packaging/license_tool.py init

Then for each person who buys a license:

    python packaging/license_tool.py issue "Jane Doe"

Send them the printed key. Keep the private key file safe and backed up: without it you can't
issue keys that existing copies of DupeSort accept, and anyone who has it can make keys.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dupesort import licensing  # noqa: E402

DEFAULT_KEY_FILE = Path.home() / ".dupesort-signing-key"
SOURCE = ROOT / "dupesort" / "licensing.py"


def load_secret(path: Path) -> bytes:
    try:
        secret = bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        sys.exit(f"No signing key at {path}. Run:  python packaging/license_tool.py init")
    if len(secret) != 32:
        sys.exit(f"{path} doesn't hold a valid signing key.")
    return secret


def cmd_init(args) -> None:
    path = Path(args.key_file).expanduser()
    if path.exists():
        secret = load_secret(path)
        print(f"Using the existing signing key at {path}")
    else:
        secret = os.urandom(32)
        path.write_text(secret.hex() + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        print(f"Created a new signing key: {path}")
        print("  Back it up somewhere safe (a password manager is ideal). Never commit it.")
    public = licensing.public_key_of(secret).hex()
    text = SOURCE.read_text(encoding="utf-8")
    current = re.search(r'^PUBLIC_KEY = "([0-9a-f]*)"', text, re.M)
    if current and current.group(1) == public:
        print("dupesort/licensing.py already has this public key.")
        return
    if current and current.group(1) and not args.replace:
        sys.exit("dupesort/licensing.py already has a different public key. Keys made with the "
                 "old signing key would stop working. Add --replace if you really mean it.")
    SOURCE.write_text(re.sub(r'^PUBLIC_KEY = "[0-9a-f]*"', f'PUBLIC_KEY = "{public}"', text,
                             count=1, flags=re.M), encoding="utf-8")
    print(f"Wrote the public key into dupesort/licensing.py: {public}")
    print("Commit and push that change, then release a new version.")


def cmd_issue(args) -> None:
    secret = load_secret(Path(args.key_file).expanduser())
    public = licensing.public_key_of(secret).hex()
    if licensing.PUBLIC_KEY != public:
        sys.exit("This signing key doesn't match the public key in dupesort/licensing.py. "
                 "Run `init` first (and release that version).")
    key = licensing.make_key(secret, args.name)
    assert licensing.read_key(key) is not None
    print(f"License key for {args.name}:\n\n{key}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Make DupeSort license keys.")
    parser.add_argument("--key-file", default=str(DEFAULT_KEY_FILE),
                        help=f"your private signing key (default {DEFAULT_KEY_FILE})")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init", help="create your signing key and put its public half in the app")
    init.add_argument("--replace", action="store_true", help="replace an existing public key")
    init.set_defaults(fn=cmd_init)
    issue = sub.add_parser("issue", help="make a license key for someone")
    issue.add_argument("name", help="the licensee's name (shown in the app)")
    issue.set_defaults(fn=cmd_issue)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
