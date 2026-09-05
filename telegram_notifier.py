import requests
import logging

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_message(self, text, parse_mode='HTML'):
        if not self.token or not self.chat_id:
            logger.error("Telegram token/chat_id belum diatur")
            return
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            r = requests.post(url, data=payload, timeout=10)
            if r.status_code != 200:
                logger.error(f"Telegram send failed: {r.text}")
        except Exception as e:
            logger.exception(f"Telegram exception: {e}")

    def send_startup(self):
        text = (
            "✅ <b>Bot XAUUSD Monitoring Aktif</b>\n"
            "Terhubung ke Deriv API.\n"
            "Mode: Batch monitoring (setiap 5 menit).\n"
            "Jam aktif: Senin 05:00 - Sabtu 05:00 WIB"
        )
        self.send_message(text)

    def send_signal(self, signal):
        direction_emoji = "🟢 BUY" if signal['direction'] == 'BUY' else "🔴 SELL"
        text = (
            f"<b>🚨 {direction_emoji} Signal Valid ({signal['timeframe']})</b>\n"
            f"⏰ Waktu: {signal['time']}\n"
            f"💰 Entry: {signal['entry']:.2f}\n"
            f"🛑 Stop Loss: {signal['sl']:.2f}\n"
            f"🎯 Take Profit: {signal['tp']:.2f}\n"
            f"📊 RRR: {signal['rrr']:.2f}"
        )
        self.send_message(text)

    def send_error(self, error_msg):
        text = f"⚠️ <b>System Error</b>\n{error_msg}"
        self.send_message(text)
