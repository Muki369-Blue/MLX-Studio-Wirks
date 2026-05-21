#!/usr/bin/env python3
"""Desktop entrypoint for the packaged MLX-Moxy-Wirks macOS app."""

import os
import threading
import time
import webbrowser

# Packaged app builds should stay LAN-reachable unless the user overrides it.
os.environ.setdefault("MLX_MOXY_HOST", "0.0.0.0")

from server import PORT, main


def _open_ui() -> None:
    # Give uvicorn a moment to bind before opening the browser.
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=_open_ui, daemon=True).start()
    main()
