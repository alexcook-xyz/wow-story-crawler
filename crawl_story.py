# crawl_story.py - entry point. See README.md.
# Usage: python crawl_story.py --help
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from storycrawler.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
