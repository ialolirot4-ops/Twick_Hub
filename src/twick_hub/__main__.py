"""``python -m twick_hub`` — same entry point as the ``twick-hub`` script
(FASE 22.1, RISK-PKG-04). The ``__name__`` guard keeps importing this module
free of side effects (AD-03): nothing starts unless it is run as ``__main__``.
"""

from __future__ import annotations

import sys

from twick_hub.main import main

if __name__ == "__main__":
    sys.exit(main())
