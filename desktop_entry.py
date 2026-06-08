#!/usr/bin/env python3
"""Desktop entrypoint for the packaged MLX-Moxy-Wirks macOS app."""

import os
import secrets
import threading
import time
import webbrowser
from urllib.parse import quote

# Packaged app builds are local-only by default. Users can still override this
# explicitly in their shell, but the app should not expose itself on the LAN.
os.environ.setdefault("MLX_MOXY_HOST", "127.0.0.1")
os.environ.setdefault("MLX_MOXY_AUTH_TOKEN", secrets.token_urlsafe(32))

from server import PORT, main


def _open_ui() -> None:
    # Give uvicorn a moment to bind before opening the browser.
    time.sleep(1.2)
    token = quote(os.environ.get("MLX_MOXY_AUTH_TOKEN", ""), safe="")
    webbrowser.open(f"http://localhost:{PORT}?moxy_token={token}")


if __name__ == "__main__":
    if os.environ.get("MLX_MOXY_OPEN_BROWSER", "1") != "0":
        threading.Thread(target=_open_ui, daemon=True).start()
    main()
