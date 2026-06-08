#!/usr/bin/env python3
"""Backend helper entrypoint for the native macOS shell."""

import os

# The SwiftUI shell owns presentation and lifecycle; the backend helper should
# stay private to this Mac and should not open an external browser.
os.environ.setdefault("MLX_MOXY_HOST", "127.0.0.1")
os.environ.setdefault("MLX_MOXY_OPEN_BROWSER", "0")

from server import main


if __name__ == "__main__":
    main()
