"""Trivial smoke test for the Python SDK.

Run ``python scripts/generate_sdk.py --py`` first to populate ``sdk/py``.
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    base = os.environ.get("AUTOCSR_BASE", "http://127.0.0.1:8766")
    try:
        # The generated package name is derived from the OpenAPI title.
        sys.path.insert(0, "py")
        try:
            from autocsr_api_client import Client  # type: ignore[import-not-found]
        except ImportError:
            from autocsr_api_client.client import Client  # type: ignore[import-not-found,no-redef]
    except Exception as e:  # noqa: BLE001
        print(f"[example.py] SDK not generated yet: {e}")
        return 0
    client = Client(base_url=base)
    print(f"[example.py] SDK loaded against {base}; client={client!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
