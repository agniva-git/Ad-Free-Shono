#!/usr/bin/env python3
"""
AdFreeShono backup and restore.

Backs up the database (using SQLite's own backup API, so it is consistent even while
the server is running), album artwork, and the audio stored inside the app.
Songs added by scanning a folder live OUTSIDE the app: they are listed in
external_files.json and only copied when you pass --include-external.
"""
import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.config import settings

EXTERNAL_DIR = "external_audio"
MANIFEST = "external_files.json"


def backup_database(dest: Path) -> bool:
    db_file = settings.db_file
    if not db_file or not db_file.exists():
        print("  ! No SQLite database file found")
        return False
    src = sqlite3.connect(str(db_file))
    dst = sqlite3.connect(str(dest))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    print(f"  Database backed up: {dest.name}")
    return True


def external_song_paths(db_copy: Path) -> list[Path]:
    """Audio files referenced by the database that live outside MUSIC_DIR."""
    base = settings.music_path.resolve()
    conn = sqlite3.connect(str(db_copy))
    try:
        rows = conn.execute("SELECT audio_path FROM songs").fetchall()
    finally:
        conn.close()
    result = []
    for (audio_path,) in rows:
        p = Path(audio_path)
        if p.is_absolute() and not p.resolve().is_relative_to(base):
            result.append(p)
    return result


def create_backup(dest_root: Path, include_music: bool, include_external: bool):
    backup_dir = dest_root / f"adfree_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("ADFREESHONO BACKUP")
    print("=" * 60)
    print(f"Destination: {backup_dir.resolve()}\n")

    if not backup_database(backup_dir / "music.db"):
        return

    art = settings.artwork_path
    if art.exists() and any(art.iterdir()):
        shutil.copytree(art, backup_dir / "artwork", dirs_exist_ok=True)
        print(f"  Artwork backed up: {len(list(art.iterdir()))} files")

    if include_music:
        music = settings.music_path
        if music.exists() and any(music.iterdir()):
            shutil.copytree(music, backup_dir / "audio", dirs_exist_ok=True)
            print(f"  App audio backed up: {len(list((backup_dir / 'audio').iterdir()))} tracks")
        else:
            print("  App audio folder is empty")

    externals = [p for p in external_song_paths(backup_dir / "music.db") if p.is_file()]
    if externals:
        manifest = []
        if include_external:
            ext_dir = backup_dir / EXTERNAL_DIR
            ext_dir.mkdir()
            for i, src in enumerate(externals):
                rel = f"{i:05d}{src.suffix}"
                shutil.copy2(src, ext_dir / rel)
                manifest.append({"original": str(src), "backup": rel})
            print(f"  Scanned-folder audio copied: {len(externals)} files")
        else:
            manifest = [{"original": str(p), "backup": None} for p in externals]
            print(f"  NOTE: {len(externals)} scanned songs live outside the app and were NOT copied.")
            print("        Use --include-external to copy them too.")
        (backup_dir / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("\nBackup finished: " + str(backup_dir.resolve()) + "\n")


def restore_backup(backup_path: Path):
    if not backup_path.is_dir():
        print(f"Backup folder does not exist: {backup_path}")
        return

    print(f"\nRestoring from: {backup_path.resolve()}")

    if (backup_path / "music.db").exists() and settings.db_file:
        settings.db_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path / "music.db", settings.db_file)
        print("  Restored database")

    if (backup_path / "artwork").exists():
        settings.artwork_path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(backup_path / "artwork", settings.artwork_path, dirs_exist_ok=True)
        print("  Restored artwork")

    if (backup_path / "audio").exists():
        settings.music_path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(backup_path / "audio", settings.music_path, dirs_exist_ok=True)
        print("  Restored app audio")

    manifest_file = backup_path / MANIFEST
    if manifest_file.exists():
        restored = 0
        for item in json.loads(manifest_file.read_text(encoding="utf-8")):
            if not item["backup"]:
                continue
            target = Path(item["original"])
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path / EXTERNAL_DIR / item["backup"], target)
                restored += 1
        print(f"  Restored {restored} scanned-folder files to their original locations")

    print("\nRestore finished.\n")


def main():
    parser = argparse.ArgumentParser(description="Back up and restore the AdFreeShono library.")
    parser.add_argument("--dest", default="./backups", help="Backup folder (default ./backups)")
    parser.add_argument("--no-music", action="store_true", help="Skip the app's own audio folder")
    parser.add_argument("--include-external", action="store_true", help="Also copy songs added by folder scans")
    parser.add_argument("--restore", type=str, default=None, help="Path of a backup folder to restore")
    args = parser.parse_args()

    if args.restore:
        restore_backup(Path(args.restore))
    else:
        create_backup(Path(args.dest), include_music=not args.no_music, include_external=args.include_external)


if __name__ == "__main__":
    main()
