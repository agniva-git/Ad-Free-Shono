#!/usr/bin/env python3
"""
Manage AdFreeShono accounts from the server's command line.
Useful if you forget the admin password, or want to add a friend without opening the website.

  python scripts/manage_users.py list
  python scripts/manage_users.py create alice            (add --admin for another admin)
  python scripts/manage_users.py reset-password alice
  python scripts/manage_users.py disable alice
  python scripts/manage_users.py enable alice

With Docker:  docker compose exec -it app python scripts/manage_users.py reset-password alice
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.database import Base, SessionLocal, engine
from backend.app.models import User
from backend.app.services.accounts import active_admin_count, create_user, normalize_username, set_password
from backend.app.services.migrate import migrate_schema


def ask_password() -> str:
    first = getpass.getpass("New password (10+ characters): ")
    if first != getpass.getpass("Type it again: "):
        sys.exit("The two passwords did not match.")
    return first


def find(db, name: str) -> User:
    user = db.query(User).filter(User.username == normalize_username(name)).first()
    if not user:
        sys.exit(f"No account named '{name}'.")
    return user


def main():
    parser = argparse.ArgumentParser(description="Manage AdFreeShono accounts.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    c = sub.add_parser("create"); c.add_argument("username"); c.add_argument("--admin", action="store_true")
    for name in ("reset-password", "disable", "enable"):
        sub.add_parser(name).add_argument("username")
    args = parser.parse_args()

    migrate_schema(engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.cmd == "list":
            for u in db.query(User).order_by(User.created_at):
                print(f"{u.username:<20} {u.role:<7} {'active' if u.is_active else 'DISABLED'}")
        elif args.cmd == "create":
            try:
                u = create_user(db, args.username, ask_password(), "admin" if args.admin else "member")
            except ValueError as err:
                sys.exit(str(err))
            print(f"Created {u.role} account '{u.username}'.")
        elif args.cmd == "reset-password":
            u = find(db, args.username)
            try:
                set_password(db, u, ask_password())
            except ValueError as err:
                sys.exit(str(err))
            print(f"Password changed for '{u.username}'. They are signed out everywhere.")
        else:
            u = find(db, args.username)
            enable = args.cmd == "enable"
            if not enable and u.role == "admin" and active_admin_count(db) <= 1:
                sys.exit("That is the last active admin; it cannot be disabled.")
            u.is_active = enable
            db.commit()
            print(f"'{u.username}' is now {'active' if enable else 'disabled'}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
