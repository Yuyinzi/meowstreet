import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.investing_chrome import start_investing_chrome

if __name__ == "__main__":
    start_investing_chrome()
