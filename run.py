#!/usr/bin/env python3
import socket

import uvicorn

from backend.app.config import BASE_DIR, settings


def get_local_ip():
    """Finds the LAN IP address of this machine for phone access."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # does not send anything, just picks the outbound route
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    port = settings.PORT
    lan = settings.HOST not in ("127.0.0.1", "localhost")

    print("\n" + "=" * 60)
    print("ADFREESHONO - PERSONAL MUSIC SERVER")
    print("=" * 60)
    print(f"  On this PC:   http://localhost:{port}")
    if lan:
        print(f"  On your LAN:  http://{get_local_ip()}:{port}")
    print("=" * 60)
    print("  Stop server: Ctrl + C\n")

    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=port,
        reload=settings.DEBUG,
        reload_dirs=[str(BASE_DIR / "backend"), str(BASE_DIR / "frontend")] if settings.DEBUG else None,
    )


if __name__ == "__main__":
    main()
