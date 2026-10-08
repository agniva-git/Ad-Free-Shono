#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.config import settings
from backend.app.database import Base, SessionLocal, engine
from backend.app.services.scanner import is_safe_directory, scan_directory


def main():
    parser = argparse.ArgumentParser(description="Scan and index audio files into the AdFreeShono database.")
    parser.add_argument("directory", nargs="?", default=None, help="Folder to scan (defaults to MUSIC_DIR)")
    parser.add_argument("--copy", action="store_true", help="Copy scanned files into the app's own storage")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)

    target = Path(args.directory).expanduser().resolve() if args.directory else settings.music_path
    if not target.is_dir():
        sys.exit(f"Folder does not exist: {target}")
    if not is_safe_directory(target):
        sys.exit("Scanning this system folder is restricted.")

    print(f"Scanning: {target}")
    print(f"Copy files into app storage: {args.copy}")

    db = SessionLocal()
    try:
        results = scan_directory(target, db, copy_to_storage=args.copy)
    finally:
        db.close()

    print("\nScan complete.")
    print(f"  Scanned files:      {results.get('scanned', 0)}")
    print(f"  Newly added:        {results.get('added', 0)}")
    print(f"  Skipped (indexed):  {results.get('skipped', 0)}")


if __name__ == "__main__":
    main()
