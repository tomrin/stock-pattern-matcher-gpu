"""Safe local configuration template for stock-pattern-matcher-gpu.

Copy this file to config.py only if you want local overrides.
Do not put real API keys in this file or commit config.py.
"""

from pathlib import Path

# Project-local paths. The default application paths already use these locations.
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data" / "kline"
REPORT_DIR = PROJECT_DIR / "reports"

# GPU batch size. Lower this value if CUDA memory is insufficient.
BATCH_SIZE = 2048

# Number of historical matches to display.
TOP_N = 10

# Optional data-source placeholders. This GPU project does not download data
# during matching; keep credentials in environment variables when needed.
TUSHARE_TOKEN = ""
AKSHARE_TOKEN = ""
KIMI_API_KEY = ""
