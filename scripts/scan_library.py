#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.database import SessionLocal, engine, Base
from backend.app.config import settings
from backend.app.services.scanner import scan_directory

def main():
    parser = argparse.ArgumentParser(description="Scan and index audio files into Personal Music Cloud SQLite database.")
    parser.add_argument("directory", nargs="?", default=None, help="Directory to scan (defaults to configured MUSIC_DIR)")
    parser.add_argument("--copy", action="store_true", help="Copy scanned audio files into the app media store")
    args = parser.parse_args()

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    target_dir = Path(args.directory).resolve() if args.directory else settings.music_path
    print(f"🎵 Scanning directory: {target_dir}")
    print(f"📦 Copy files to internal storage: {args.copy}")

    db = SessionLocal()
    try:
        results = scan_directory(target_dir, db, copy_to_storage=args.copy)
        print("\n✅ Scan Complete!")
        print(f"  • Scanned files: {results.get('scanned', 0)}")
        print(f"  • Newly added:   {results.get('added', 0)}")
        print(f"  • Skipped (dups):{results.get('skipped', 0)}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
