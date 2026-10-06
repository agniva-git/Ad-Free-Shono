#!/usr/bin/env python3
import sys
import shutil
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.config import settings

def main():
    parser = argparse.ArgumentParser(description="Backup Personal Music Cloud database and artwork.")
    parser.add_argument("--dest", default="./backups", help="Destination backup directory")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = Path(args.dest) / f"backup_{timestamp}"
    backup_root.mkdir(parents=True, exist_ok=True)

    print(f"📦 Starting zero-cost backup to: {backup_root.resolve()}")

    # Backup SQLite DB
    db_file = settings.data_path / "music.db"
    if db_file.exists():
        shutil.copy2(db_file, backup_root / "music.db")
        print("  ✓ Backed up SQLite database (music.db)")
    else:
        print("  ! No music.db found in data folder")

    # Backup Artwork directory
    artwork_dir = settings.artwork_path
    if artwork_dir.exists() and any(artwork_dir.iterdir()):
        shutil.copytree(artwork_dir, backup_root / "artwork", dirs_exist_ok=True)
        print("  ✓ Backed up artwork directory")

    print("\n✅ Backup successfully created!")

if __name__ == "__main__":
    main()
