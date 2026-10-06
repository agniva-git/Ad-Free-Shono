#!/usr/bin/env python3
import socket
import uvicorn
from backend.app.config import settings

def get_local_ip():
    """Finds the LAN IP address of this machine for phone access."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not actually connect, just resolves outbound route
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def main():
    local_ip = get_local_ip()
    port = settings.PORT

    print("\n" + "=" * 60)
    print("🎵  PERSONAL MUSIC CLOUD — ZERO-COST STREAMING SERVER")
    print("=" * 60)
    print(f"  💻 On this PC:          http://localhost:{port}")
    print(f"  📱 On your Phone/Wi-Fi: http://{local_ip}:{port}")
    print("=" * 60)
    print("  ⭐ Tips:")
    print("     • Install as PWA: Open on your phone's browser and tap 'Add to Home Screen'")
    print("     • Ingest music:   Use 'Upload & Scan' in the UI or run scripts/scan_library.py")
    print("     • Stop server:    Press Ctrl + C")
    print("=" * 60 + "\n")

    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, reload=settings.DEBUG)

if __name__ == "__main__":
    main()
