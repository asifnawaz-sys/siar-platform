from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
EXPORT_DIR = ROOT / "exports"

for p in (DATA_DIR, LOG_DIR, EXPORT_DIR):
    p.mkdir(parents=True, exist_ok=True)

APP_NAME = "SIAR Digital Platform"
HOST = "127.0.0.1"
PORT = int(os.getenv("SIAR_PORT", "8765"))

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
