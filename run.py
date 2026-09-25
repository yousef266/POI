"""Run from a clean checkout without installing the package."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))
from poi_harvester.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
