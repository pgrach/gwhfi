import os
import sys


INGESTION_DIR = os.path.join(os.path.dirname(__file__), "ingestion")
sys.path.insert(0, INGESTION_DIR)

from diagnose import main


if __name__ == "__main__":
    raise SystemExit(main())
