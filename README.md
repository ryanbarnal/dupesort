# DupeSort

A desktop app for Windows, macOS and Linux. It finds duplicate **music, photos, videos and documents**, moves the extra copies into a `_Duplicates` folder, and tidies up what's left. Nothing is ever deleted, and every change can be undone from the **History** page.

## What it does

| | Finds duplicates by | Organizing (optional) |
|---|---|---|
| **Music** | identical file · same artist + title + length · same *sound* (Chromaprint fingerprint, catches MP3 vs FLAC copies) | Looks up title, artist, album, album artist, genre, year, track number and cover art (MusicBrainz), plus lyrics (LRCLIB). Lyrics are embedded in the file. Files are renamed in place to `Artist - Title` (the pattern is editable). |
| **Photos** | identical file · visually similar (perceptual hash; catches resized and re-saved copies) | Moves photos into `YYYY/MM` folders by the date taken (EXIF). |
| **Videos** | identical file · same video re-encoded (frame fingerprints, needs FFmpeg) | `YYYY/MM` date folders. Renames movies to `Title (Year)` and episodes to `Show - S01E02 - Name` using TMDb. |
| **Documents** | identical file · same text in different files or formats (e.g. a `.docx` and its `.pdf`) | Sorts into PDF / Word / Spreadsheets / Presentations / Text / eBooks folders. |

**How it works:**
- In each duplicate group the app ticks the best copy to keep: highest quality (bitrate, lossless, resolution), or the oldest, newest or shortest path. You can change any tick.
- **Move duplicates** relocates the unticked copies to `<scanned folder>/_Duplicates/<original sub-folder>/`.
- **Music lookups:** matches at or above the confidence threshold (default 90%) are ticked automatically. Orange rows need review: pick another online match from the dropdown, or type the details yourself.
- **History:** every move, rename and tag change is logged and can be undone.

## Run from source

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m dupesort
```

On Windows the commands are `.venv\Scripts\pip` and `.venv\Scripts\python`.

## Optional helpers (recommended)

| Tool | Enables | Install |
|---|---|---|
| **Chromaprint `fpcalc`** | "same sound" music matching, plus AcoustID lookups for songs with no tags | macOS: `brew install chromaprint` · Linux: `apt install libchromaprint-tools` · Windows: [acoustid.org/chromaprint](https://acoustid.org/chromaprint) |
| **FFmpeg** | re-encoded video matching and video recording dates | macOS: `brew install ffmpeg` · Linux: `apt install ffmpeg` · Windows: [ffmpeg.org](https://ffmpeg.org/download.html) |

The app finds these on your `PATH`. For a self-contained build, put the executables in a `bin/` folder before building and they are bundled. Run the app with `--check` to see which helpers it found.

## Free API keys (optional, in Settings)

- **TMDb**: movie and TV names. Get a key at themoviedb.org → Settings → API.
- **AcoustID**: identifies songs by their sound when the tags and filename are useless. Register an application at acoustid.org.

MusicBrainz, Cover Art Archive and LRCLIB need no key. MusicBrainz allows one request per second, so the first lookup of a large library takes a while. Each artist's albums are cached for the rest of the session.

## Installing

- **macOS:** open `DupeSort-<version>-macOS-arm64.dmg` and drag **DupeSort** onto **Applications**. If the build isn't signed with an Apple Developer ID, macOS warns the first time it opens: right-click the app → **Open** → **Open**. On recent macOS versions you may need **System Settings → Privacy & Security → Open Anyway** instead.
- **Windows:** run `DupeSort-<version>-Windows-Setup.exe`. It installs for your user account without admin rights (all users can be chosen instead), adds a Start-menu entry and, optionally, a desktop shortcut. Remove it from **Settings → Apps**. Unsigned installers trigger SmartScreen: click **More info → Run anyway**.

Your settings and undo history are kept when you uninstall or upgrade.

## Building the installers

Each installer must be built on its own OS.

**macOS (.dmg):**
```bash
packaging/build_macos.sh
```
Output: `dist/DupeSort-<version>-macOS-<arch>.dmg`. Helpers in `bin/` are bundled. To sign and notarize, set `DEVELOPER_ID` and `NOTARY_PROFILE`; see the comments in the script.

**Windows (Setup.exe):** install [Inno Setup 6](https://jrsoftware.org/isdl.php), then:
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -FetchHelpers
```
Output: `dist\DupeSort-<version>-Windows-Setup.exe`. `-FetchHelpers` downloads the Windows versions of fpcalc (Chromaprint) and FFmpeg (BtbN builds) so they are bundled.

**All platforms at once:** push a tag such as `v0.1.0` to GitHub. `.github/workflows/build.yml` tests the app, builds the DMG, the Setup.exe and a Linux `.tar.gz`, and attaches them to a GitHub release.

The app icon is drawn by `packaging/make_icons.py`, which writes `icon.png`, `icon.ico` and `icon.icns`.

## Tests

```bash
python -m pytest tests
```

## Where data is stored

Settings and the undo history live in the OS's standard app-data folder (via `platformdirs`). Open it from **History → Open history folder**.
