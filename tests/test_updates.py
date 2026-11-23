from dupesort import updates

GITHUB = {
    "tag_name": "v0.3.0", "html_url": "https://github.com/x/y/releases/tag/v0.3.0",
    "body": "New things", "draft": False, "prerelease": False,
    "assets": [
        {"name": "DupeSort-0.3.0-Windows-Setup.exe", "browser_download_url": "https://d/win"},
        {"name": "DupeSort-0.3.0-macOS-arm64.dmg", "browser_download_url": "https://d/mac"},
        {"name": "DupeSort-linux-x86_64.tar.gz", "browser_download_url": "https://d/linux"},
    ],
}


def test_versions_compare_as_numbers():
    assert updates.is_newer("0.10.0", "0.9.9")
    assert updates.is_newer("v0.2.2", "0.2.1")
    assert not updates.is_newer("0.2.1", "0.2.1")
    assert not updates.is_newer("0.2.0", "0.2.1")


def test_release_from_github_and_platform_download():
    rel = updates.from_github(GITHUB)
    assert rel.version == "0.3.0" and rel.notes == "New things"
    assert updates.pick_asset(rel.assets, "Windows", "AMD64")[1] == "https://d/win"
    assert updates.pick_asset(rel.assets, "Darwin", "arm64")[1] == "https://d/mac"
    assert updates.pick_asset(rel.assets, "Linux", "x86_64")[1] == "https://d/linux"
    assert updates.from_github({**GITHUB, "prerelease": True}) is None
    assert updates.from_github({"message": "Not Found"}) is None


def test_check_offers_only_newer(monkeypatch):
    monkeypatch.setattr(updates, "latest_release", lambda timeout=15: updates.from_github(GITHUB))
    monkeypatch.setattr(updates, "__version__", "0.3.0")
    assert updates.check() is None
    monkeypatch.setattr(updates, "__version__", "0.2.1")
    assert updates.check().version == "0.3.0"
