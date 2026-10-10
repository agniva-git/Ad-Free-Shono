"""Upgrades a database created by an older version (before accounts) in place."""
from sqlalchemy import inspect

from ..models import Favorite, User


def migrate_schema(engine) -> None:
    if not inspect(engine).has_table("songs"):
        return  # brand-new database: create_all builds everything

    User.__table__.create(engine, checkfirst=True)  # the new columns below point at this table

    with engine.begin() as conn:
        def columns(table: str) -> set:
            return {c["name"] for c in inspect(conn).get_columns(table)}

        def add(table: str, column: str, ddl: str) -> None:
            if column not in columns(table):
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

        # users table migration (handles older schema with is_admin instead of role)
        if "users" in inspect(conn).get_table_names():
            add("users", "role", "VARCHAR(10) NOT NULL DEFAULT 'member'")
            add("users", "is_active", "BOOLEAN NOT NULL DEFAULT 1")
            if "is_admin" in columns("users"):
                conn.exec_driver_sql("UPDATE users SET role = 'admin' WHERE is_admin = 1")

        add("songs", "uploaded_by", "VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL")
        add("songs", "file_hash", "VARCHAR(64)")
        add("playlists", "user_id", "VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE")
        add("play_history", "user_id", "VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE")

        # favorites used to be unique per song; it must become unique per (user, song)
        if "user_id" not in columns("favorites"):
            conn.exec_driver_sql("ALTER TABLE favorites RENAME TO favorites_old")
            Favorite.__table__.create(conn)
            conn.exec_driver_sql(
                "INSERT INTO favorites (song_id, created_at) "
                "SELECT song_id, created_at FROM favorites_old WHERE song_id IN (SELECT id FROM songs)")
            conn.exec_driver_sql("DROP TABLE favorites_old")
