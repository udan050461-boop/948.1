import websocket
import json
import logging
import time
from datetime import datetime
import pytz
import pandas as pd

import config
from indicators import calculate_indicators
from models import ModelManager
from risk_management import RiskManager
from strategy import StrategyEngine
from telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fetch_candles(symbol, granularity, count):
    """Ambil data candlestick historis via WebSocket (synchronous)."""
    url = f"wss://ws.derivws.com/websockets/v3?app_id={config.APP_ID}"
    ws = websocket.create_connection(url, timeout=15)
    request = {
        "ticks_history": symbol,
        "adjust_start_time": 1,
        "count": count,
        "end": "latest",
        "granularity": granularity,
        "style": "candles"
    }
    ws.send(json.dumps(request))
    result = ws.recv()
    ws.close()
    data = json.loads(result)
    if 'error' in data:
        logger.error(f"Deriv API error: {data['error']}")
        return None
    candles = data.get('candles', [])
    return candles

def candles_to_dataframe(candles):
    df = pd.DataFrame(candles)
    # Ubah kolom string ke float
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)
    df['time'] = pd.to_datetime(df['open_time'], unit='s')
    return df

def main():
    # Periksa jam aktif (WIB)
    tz = pytz.timezone('Asia/Jakarta')
    now = datetime.now(tz)
    if now.weekday() > 4:  # Sabtu/Minggu
        if now.weekday() == 5 and now.time() < config.ACTIVE_END:
            pass  # Sabtu sebelum 05:00 masih aktif
        else:
            logger.info("Di luar jam aktif, keluar")
            return
    elif now.weekday() == 0 and now.time() < config.ACTIVE_START:
        logger.info("Senin sebelum 05:00 WIB, keluar")
        return

    notifier = TelegramNotifier(config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID)
    models = ModelManager(config)
    risk_manager = RiskManager(config)

    # Kirim notifikasi startup hanya jika state file belum ada (sekali saja)
    if not os.path.exists(config.STATE_FILE):
        notifier.send_startup()
        # Buat state file kosong
        with open(config.STATE_FILE, 'w') as f:
            json.dump({'last_signal_time': '2000-01-01T00:00:00'}, f)

    signals = []
    for granularity in config.TIMEFRAMES:
        tf_label = f"M{granularity//60}" if granularity >= 60 else f"S{granularity}"
        logger.info(f"Memproses {tf_label}...")
        candles = fetch_candles(config.SYMBOL, granularity, config.HISTORY_COUNT)
        if not candles:
            logger.error(f"Gagal mengambil data untuk {tf_label}")
            continue
        df = candles_to_dataframe(candles)
        df = calculate_indicators(df)

        # Inisialisasi StrategyEngine dengan timeframe
        engine = StrategyEngine(config, models, risk_manager)
        engine.timeframe = tf_label
        signal = engine.process_dataframe(df)
        if signal:
            signals.append(signal)
            logger.info(f"Sinyal {tf_label}: {signal['direction']} @ {signal['entry']}")

    # Kirim sinyal (maksimal satu per run untuk anti‑spam)
    if signals:
        # Prioritaskan timeframe lebih kecil (M5)
        signals.sort(key=lambda x: x['timeframe'])
        best_signal = signals[0]
        notifier.send_signal(best_signal)
        logger.info("Sinyal terkirim ke Telegram")
    else:
        logger.info("Tidak ada sinyal valid")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Fatal error")
        # Coba kirim notifikasi error
        try:
            notifier = TelegramNotifier(config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID)
            notifier.send_error(str(e))
        except:
            pass
        raise
