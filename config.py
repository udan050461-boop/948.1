import os
from datetime import time

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Deriv API
APP_ID = 1089
SYMBOL = "frxXAUUSD"
TIMEFRAMES = [300, 900, 1800]  # M5, M15, M30
HISTORY_COUNT = 500            # jumlah candle yang diambil

# Jam aktif (WIB, UTC+7)
ACTIVE_DAYS = range(0, 5)      # Senin=0 ... Jumat=4
ACTIVE_START = time(5, 0)      # 05:00 WIB
ACTIVE_END = time(5, 0)        # Sabtu 05:00 WIB (batas akhir)

# Parameter trading
MIN_TP_POINTS = 13
MIN_RRR = 2.0
MAX_SPREAD = 0.5

# Anti‑spam (menit)
SIGNAL_COOLDOWN_MINUTES = 5

# Paths
STATE_FILE = "state.json"
MODEL_DIR = "models"
