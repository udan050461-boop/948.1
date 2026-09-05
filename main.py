import os
import sys
import logging
import requests
import numpy as np
import pandas as pd
from typing import Dict, List, Optional

# Konfigurasi Logging Ketat
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("QUANT_SCANNER_CORE")

# Konfigurasi Environment (GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DERIV_APP_ID = os.getenv("DERIV_APP_ID", "1089")

class TelegramNotifier:
    """Modul Notifikasi Anti-Spam (Hanya Kondisi Kritis)"""
    @staticmethod
    def send(message: str):
        if not TELEGRAM_BOT_TOKEN:
            logger.warning("Telegram Token belum dikonfigurasi.")
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                logger.error(f"Gagal mengirim Telegram: {response.text}")
        except Exception as e:
            logger.error(f"Exception Telegram Notifier: {e}")

class KalmanFilter:
    """Penyaringan Noise Harga & Mean Reversion Dinamis"""
    def __init__(self, process_variance: float = 1e-5, measurement_variance: float = 1e-2):
        self.q = process_variance
        self.r = measurement_variance
        self.x = 0.0
        self.p = 1.0
        self.initialized = False

    def update(self, measurement: float) -> float:
        if not self.initialized:
            self.x = measurement
            self.initialized = True
            return self.x
        p_pred = self.p + self.q
        k = p_pred / (p_pred + self.r)
        self.x = self.x + k * (measurement - self.x)
        self.p = (1 - k) * p_pred
        return self.x

class MarketAnalyzer:
    """Analisis Kuantitatif: Kalman, ATR, dan Regime Detection"""
    @staticmethod
    def fetch_deriv_candles(symbol: str = "frxXAUUSD", granularity: int = 300, count: int = 100) -> List[Dict[str, float]]:
        url = f"https://ws.derivws.com/websockets/v3?app_id={DERIV_APP_ID}"
        # Menggunakan HTTP REST/JSON-RPC POST atau koneksi singkat via requests/websocket untuk fetch sekali jalan
        # Untuk kesederhanaan dan kestabilan skrip berkala 5 menit, kita gunakan websocket singkat atau endpoint publik deriv jika tersedia, 
        # namun karena Deriv berbasis WS murni, kita bisa buka koneksi sebentar ambil data lalu tutup.
        import websocket
        
        ws_url = f"wss://ws.derivws.com/websockets/v3?app_id={DERIV_APP_ID}"
        payload = json.dumps({
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "granularity": granularity,
            "style": "candles"
        })
        
        try:
            ws = websocket.create_connection(ws_url, timeout=10)
            ws.send(payload)
            response = ws.recv()
            data = json.loads(response)
            ws.close()
            
            if "candles" in data:
                return [{
                    "time": c.get("epoch"),
                    "open": float(c.get("open")),
                    "high": float(c.get("high")),
                    "low": float(c.get("low")),
                    "close": float(c.get("close"))
                } for c in data["candles"]]
        except Exception as e:
            logger.error(f"Gagal mengambil data dari Deriv WS: {e}")
        return []

    @staticmethod
    def evaluate():
        import json
        candles = MarketAnalyzer.fetch_deriv_candles()
        if not candles or len(candles) < 20:
            logger.error("Data candle tidak mencukupi untuk analisis.")
            return

        df = pd.DataFrame(candles)
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values

        # Kalman Filter Processing
        kf = KalmanFilter()
        filtered_closes = [kf.update(c) for c in closes]
        current_kalman = filtered_closes[-1]
        current_close = closes[-1]

        # Hitung ATR (14)
        tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
        atr = float(np.mean(tr[-14:]))

        # Deteksi Regime Sederhana
        volatility = np.std(np.diff(closes[-20:]) / closes[-21:-1])
        mean_range = np.mean(closes[-20:])
        regime = "TRENDING"
        if volatility > (mean_range * 0.0015):
            regime = "HIGH_VOLATILITY"
        elif abs(closes[-1] - closes[-20]) > (2 * np.mean(highs[-20:] - lows[-20:])):
            regime = "TRENDING"
        else:
            regime = "RANGING"

        if regime == "HIGH_VOLATILITY":
            logger.info("Market regime High Volatility. Sinyal diabaikan.")
            return

        # Evaluasi Sinyal
        signal = None
        if current_close < current_kalman - (1.5 * atr):
            signal = "BUY"
        elif current_close > current_kalman + (1.5 * atr):
            signal = "SELL"

        if signal:
            min_tp_points = 13.0
            tp_dist = max(min_tp_points, atr * 1.5)
            sl_dist = max(4.0, atr * 0.6)

            entry = current_close
            sl = entry - sl_dist if signal == "BUY" else entry + sl_dist
            tp = entry + tp_dist if signal == "BUY" else entry - tp_dist
            rrr = round(abs(tp - entry) / abs(entry - sl), 2)
            tp_points_actual = abs(tp - entry)

            if rrr >= 2.0 and tp_points_actual >= 13.0:
                alert_msg = (
                    f"🎯 *VALID SIGNAL ALERT ({signal})*\n\n"
                    f"• *Symbol:* XAUUSD (M5 Periodic Scan)\n"
                    f"• *Market Regime:* `{regime}`\n"
                    f"• *Entry Price:* `{round(entry, 2)}`\n"
                    f"• *Stop Loss:* `{round(sl, 2)}` (Ultra-Tight)\n"
                    f"• *Take Profit:* `{round(tp, 2)}` (TP Poin: `{tp_points_actual}`)\n"
                    f"• *Risk-to-Reward:* `1:{rrr}`\n"
                    f"• *Kalman Mean:* `{round(current_kalman, 2)}`"
                )
                TelegramNotifier.send(alert_msg)
                logger.info(f"Sinyal Valid Terkirim: {signal} di harga {entry}")
            else:
                logger.info("Sinyal terdeteksi tapi tidak memenuhi kriteria RRR >= 1:2 atau TP >= 13 poin.")
        else:
            logger.info(f"Market stabil. Harga saat ini ({current_close}) berada dalam batas wajar Kalman Mean.")

if __name__ == "__main__":
    logger.info("Memulai pemindaian siklus 5 menit...")
    MarketAnalyzer.evaluate()
