"""Seeds the InstaKill database. The data and logic live in app/db/seed.py,
so tests can import them without depending on this scripts/ folder."""
import sys
from pathlib import Path

# Make `app` importable when this file is run directly as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.seed import seed  # noqa: E402

if __name__ == "__main__":
    seed()
