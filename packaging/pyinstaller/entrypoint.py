"""PyInstaller's ``Analysis`` needs a real script file as its entry
point (it cannot target ``python -m twick_hub.main`` directly). This is
a thin, otherwise-empty wrapper around the real entry point in
``twick_hub.main`` — no logic lives here, so there is nothing in this
file for FASE 19 (Packaging) to duplicate or drift out of sync with the
actual application.
"""

from __future__ import annotations

import sys

from twick_hub.main import main

if __name__ == "__main__":
    sys.exit(main())
