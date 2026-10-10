# AdFreeShono 🎵

A self-hosted, **100% Zero-Cost (₹0 / $0 recurring)** personal music library, streaming server, and installable PWA.

---

## 🌟 Highlights
* **Absolute Zero Infrastructure Cost:** Runs directly on your PC. No cloud subscriptions, no surprise bandwidth/egress bills, no server rentals.
* **Persistent Audio Player:** Built as a modern Single-Page Application (SPA). Seamlessly browse songs, artists, albums, and playlists while your music plays without interruptions.
* **Smart Range-Seeking:** Uses HTTP `206 Partial Content` byte-range streaming so tracks seek instantly without loading entire files into memory.
* **Metadata & Cover Extraction:** Automatically reads ID3 tags and embedded album art from MP3, FLAC, M4A, AAC, and WAV audio files.
* **Directory Scanner:** Ingest entire music folders directly from your drive in seconds using the UI or CLI.
* **PWA & Mobile Ready:** Open on your phone over home Wi-Fi and install directly to your home screen with Media Session API support (lock screen controls).
* **Git Cleanliness:** Git tracks source code only. Databases and audio files are strictly excluded.

---

## 🚀 Quick Start

> Hosting it on the internet? See **DEPLOY.md**.

### 0. Configure
Copy `.env.example` to `.env` and set `ADMIN_USERNAME`, `ADMIN_PASSWORD` (creates the first admin account on first start) and `SECRET_KEY` (32+ random characters).
Friends get their own accounts from the **Admin** page. Everyone shares one library; playlists, likes and history are private to each person.
Set `HOST=127.0.0.1` instead if you only want to use it on this PC.

### 1. Start the Server
With Python 3.10+ installed:
```bash
# Run the startup script using the virtual environment
.\.venv\Scripts\python.exe run.py
```

The terminal will display your access links:
* **On your PC:** [http://localhost:8000](http://localhost:8000)
* **On your Phone (Same Wi-Fi):** `http://<YOUR_PC_IP>:8000`

### 2. Add Music
* **Option A (Web UI):** Navigate to **Upload & Scan** in the sidebar. Drag and drop audio files, or enter an existing folder path (e.g. `D:\Music`) and click **Scan Folder**.
* **Option B (CLI):** Run the scanner script:
  ```bash
  .\.venv\Scripts\python.exe scripts/scan_library.py "D:\Path\To\MyMusic"
  ```

### 3. Install on Mobile (PWA)
1. Ensure your phone is connected to the same Wi-Fi network as your PC.
2. Open `http://<YOUR_PC_IP>:8000` in Chrome, Safari, or Firefox on your phone.
3. Tap the browser menu and select **"Add to Home Screen"** or **"Install App"**.
4. Enjoy lock-screen playback controls with background audio!

---

## 📁 Project Architecture

```
AdFreeShono/
├── backend/
│   ├── app/
│   │   ├── api/          # REST endpoints (songs, playlists, search, upload, scan)
│   │   ├── models/       # SQLAlchemy models (SQLite)
│   │   ├── schemas/      # Pydantic data schemas
│   │   ├── services/     # Metadata parsing, scanner, range streaming
│   │   ├── config.py     # Environment configuration
│   │   ├── database.py   # Database engine & session
│   │   └── main.py       # FastAPI application
│   ├── tests/            # Automated test suite
│   └── requirements.txt  # Python dependencies
├── frontend/
│   ├── css/              # Dark-mode streaming styles
│   ├── js/
│   │   ├── api.js        # API client
│   │   ├── player.js     # Persistent audio engine & MediaSession
│   │   └── app.js        # SPA navigation & view manager
│   ├── index.html        # App shell
│   ├── manifest.json     # PWA manifest
│   └── sw.js             # Service worker
├── scripts/
│   ├── scan_library.py   # Bulk music folder scanner
│   └── backup.py         # Zero-cost backup script
├── run.py                # Server launcher with LAN discovery
├── .env.example          # Sample environment variables
└── .gitignore            # Excludes media, databases, and secrets
```

---

## Running Tests
```bash
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -v backend/tests
```
Tests use a temporary database and never touch your library.

## Backups
```bash
.\.venv\Scripts\python.exe scripts/backup.py --include-external
```
Also copies songs added by folder scans. Restore with `--restore <backup folder>`.
