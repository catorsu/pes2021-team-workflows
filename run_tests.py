#!/usr/bin/env python3
"""Run the self-contained offline suite without model access."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


def main() -> int:
    if os.name == "nt" and not sys.flags.utf8_mode:
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        return subprocess.call([sys.executable, "-X", "utf8", *sys.argv], env=env)
    os.environ.setdefault("PYTHONUTF8", "1")
    root = Path(__file__).resolve().parent
    suite = unittest.TestLoader().discover(str(root / "tests"), top_level_dir=str(root))
    result = unittest.TextTestRunner(verbosity=2 if "-v" in sys.argv else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
