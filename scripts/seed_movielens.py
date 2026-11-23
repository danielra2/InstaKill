"""Seeds InstaKill with MovieLens ml-latest-small (RESETS the database).

Usage:
    python scripts/seed_movielens.py                       # looks for ml-latest-small.zip or ml-latest-small/
    python scripts/seed_movielens.py path/to/ml-latest-small.zip
    python scripts/seed_movielens.py path/to/ml-latest-small --shift-to-now

Download: https://files.grouplens.org/datasets/movielens/ml-latest-small.zip
(do not commit it: it is in .gitignore).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db.movielens import seed_movielens  # noqa: E402

URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"


def find_default() -> Path | None:
    for candidate in (ROOT / "ml-latest-small.zip", ROOT / "ml-latest-small", ROOT / "data" / "ml-latest-small.zip", ROOT / "data" / "ml-latest-small"):
        if candidate.exists():
            return candidate
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", type=Path, help="ml-latest-small.zip or the unzipped folder")
    parser.add_argument("--shift-to-now", action="store_true",
                        help="move all times forward so the last rating is 'now' (makes freshness/popularity non-zero)")
    args = parser.parse_args()
    source = args.source or find_default()
    if source is None and args.source is None:
        import urllib.request

        target = ROOT / "ml-latest-small.zip"
        print(f"MovieLens not found locally, downloading it to {target} ...")
        try:
            urllib.request.urlretrieve(URL, target)
            source = target
        except Exception as exc:  # e.g. no internet, or GroupLens's certificate chain
            target.unlink(missing_ok=True)
            print(f"Download failed ({exc}). Download it in your browser from {URL}")
    if source is None or not source.exists():
        parser.error("MovieLens not found. Download ml-latest-small.zip into the repo folder or pass its path.")
    seed_movielens(source, shift_to_now=args.shift_to_now)
