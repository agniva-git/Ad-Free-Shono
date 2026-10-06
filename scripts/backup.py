#!/usr/bin/env python3
"""
AdFreeShono Zero-Cost Backup & Restore Utility
Backs up SQLite database, album artwork, and audio files.
"""

import sys
import shutil
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.config import settings

def create_backup(dest_root: Path, include_music: bool = True):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = dest_root / f"adfree_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("📦  ADFREESHONO — ZERO-COST BACKUP UTILITY")
    print("=" * 60)
    print(f"Destination: {backup_dir.resolve()}\n")

    # 1. Backup SQLite DB
    db_file = settings.data_path / "music.db"
    if db_file.exists():
        shutil.copy2(db_file, backup_dir / "music.db")
        print("  ✓ Database backed up: music.db")
    else:
        print("  ! No database file found in data directory")

    # 2. Backup Artwork
    artwork_dir = settings.artwork_path
    if artwork_dir.exists() and any(artwork_dir.iterdir()):
        shutil.copytree(artwork_dir, backup_dir / "artwork", dirs_exist_ok=True)
        art_count = len(list(artwork_dir.iterdir()))
        print(f"  ✓ Artwork backed up: {art_count} files")
    else:
        print("  ! Artwork folder is empty or not found")

    # 3. Backup Audio Files (Fix for Problem 4)
    if include_music:
        music_dir = settings.music_path
        if music_dir.exists() and any(music_dir.iterdir()):
            dest_music = backup_dir / "audio"
            shutil.copytree(music_dir, dest_music, dirs_exist_ok=True)
            audio_count = len(list(dest_music.glob("*.*")))
            print(f"  ✓ Audio files backed up: {audio_count} tracks")
        else:
            print("  ! Internal audio folder is empty or not found")
    else:
        print("  ℹ Music audio backup skipped (--no-music specified)")

    print("\n" + "=" * 60)
    print("✅  BACKUP COMPLETED SUCCESSFULLY")
    print(f"Stored at: {backup_dir.resolve()}")
    print("=" * 60 + "\n")

def restore_backup(backup_path: Path):
    if not backup_path.exists() or not backup_path.is_dir():
        print(f"❌ Backup folder does not exist: {backup_path}")
        return

    print("\n" + "=" * 60)
    print(f"🔄 Restoring AdFreeShono from: {backup_path.resolve()}")
    print("=" * 60)

    # 1. Restore DB
    b_db = backup_path / "music.db"
    if b_db.exists():
        settings.data_path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(b_db, settings.data_path / "music.db")
        print("  ✓ Restored database (music.db)")

    # 2. Restore Artwork
    b_art = backup_path / "artwork"
    if b_art.exists():
        settings.artwork_path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(b_art, settings.artwork_path, dirs_exist_ok=True)
        print("  ✓ Restored album artwork")

    # 3. Restore Audio
    b_audio = backup_path / "audio"
    if b_audio.exists():
        settings.music_path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(b_audio, settings.music_path, dirs_exist_ok=True)
        print("  ✓ Restored audio tracks")

    print("\n✅ Restore finished successfully!\n")

def main():
    parser = argparse.ArgumentParser(description="Backup and restore AdFreeShono library.")
    parser.add_argument("--dest", default="./backups", help="Target backup directory (defaults to ./backups)")
    parser.add_argument("--no-music", action="store_true", help="Skip backing up audio files (only backup DB and artwork)")
    parser.add_argument("--restore", type=str, default=None, help="Path to backup folder to restore from")
    args = parser.parse_args()

    if args.restore:
        restore_backup(Path(args.restore))
    else:
        create_backup(Path(args.dest), include_music=not args.no_music)

if __name__ == "__main__":
    main()
