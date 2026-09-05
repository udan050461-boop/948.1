import numpy as np
import pandas as pd
import logging
from datetime import datetime, timedelta
import json
import os

from indicators import calculate_indicators
from risk_management import RiskManager
from models import ModelManager

logger = logging.getLogger(__name__)

class StrategyEngine:
    def __init__(self, config, models, risk_manager):
        self.config = config
        self.models = models
        self.risk_manager = risk_manager
        self.last_signal_time = self._load_last_signal_time()

    def _load_last_signal_time(self):
        """Muat timestamp sinyal terakhir dari state file."""
        if os.path.exists(self.config.STATE_FILE):
            with open(self.config.STATE_FILE, 'r') as f:
                state = json.load(f)
                return datetime.fromisoformat(state.get('last_signal_time', '2000-01-01T00:00:00'))
        return datetime.min

    def _save_last_signal_time(self, dt):
        """Simpan timestamp sinyal terakhir ke state file."""
        state = {'last_signal_time': dt.isoformat()}
        with open(self.config.STATE_FILE, 'w') as f:
            json.dump(state, f)

    def is_cooldown_elapsed(self):
        """Cek apakah cooldown sudah lewat."""
        if self.last_signal_time == datetime.min:
            return True
        elapsed = datetime.now() - self.last_signal_time
        return elapsed.total_seconds() >= self.config.SIGNAL_COOLDOWN_MINUTES * 60

    def process_dataframe(self, df: pd.DataFrame) -> dict:
        """Evaluasi sinyal pada DataFrame yang sudah berisi indikator."""
        if len(df) < 50:
            return None

        if not self.is_cooldown_elapsed():
            logger.debug("Cooldown aktif, skip sinyal")
            return None

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. Regime pasar (HMM)
        returns = df['close'].pct_change().dropna().tail(50).values
        volatility = df['ATR'].tail(50).values
        regime = self.models.hmm_regime(returns, volatility)
        if regime == 1:  # ranging
            logger.debug("Ranging market, skip")
            return None

        # 2. Deteksi likuiditas sweep
        sweep_detected = False
        direction = None
        if latest['low'] < latest['support'] and latest['close'] > latest['support']:
            sweep_detected = True
            direction = 'BUY'
        elif latest['high'] > latest['resistance'] and latest['close'] < latest['resistance']:
            sweep_detected = True
            direction = 'SELL'

        if not sweep_detected:
            logger.debug("No liquidity sweep")
            return None

        # 3. Konfirmasi indikator klasik
        if direction == 'BUY':
            ma_bullish = latest['MA_fast'] > latest['MA_slow']
            macd_bullish = latest['MACD'] > latest['MACD_signal']
            rsi_ok = 40 < latest['RSI'] < 70
            if not (ma_bullish and macd_bullish and rsi_ok):
                logger.debug("Indikator klasik tidak setuju untuk BUY")
                return None
        else:
            ma_bearish = latest['MA_fast'] < latest['MA_slow']
            macd_bearish = latest['MACD'] < latest['MACD_signal']
            rsi_ok = 30 < latest['RSI'] < 60
            if not (ma_bearish and macd_bearish and rsi_ok):
                logger.debug("Indikator klasik tidak setuju untuk SELL")
                return None

        # 4. Filter RandomForest (atau fallback)
        features = self.extract_features(df)
        prob_valid = self.models.rf_filter(features)
        if prob_valid < 0.6:
            logger.debug(f"Probabilitas sinyal valid rendah: {prob_valid:.2f}")
            return None

        # 5. Placeholder LSTM (selalu setuju)
        # Jika model LSTM tersedia, integrasikan di sini

        # 6. Hitung SL/TP
        entry = latest['close']
        sl, tp = self.risk_manager.calculate_sl_tp(direction, df)
        if sl is None or tp is None:
            logger.warning("Perhitungan risiko gagal")
            return None

        # 7. Buat sinyal
        rrr = (tp - entry) / (entry - sl) if direction == 'BUY' else (entry - tp) / (sl - entry)
        signal = {
            'direction': direction,
            'entry': round(entry, 2),
            'sl': sl,
            'tp': tp,
            'rrr': round(rrr, 2),
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'timeframe': self.timeframe  # ditentukan di luar
        }

        # Update cooldown state
        self.last_signal_time = datetime.now()
        self._save_last_signal_time(self.last_signal_time)

        return signal

    def extract_features(self, df):
        latest = df.iloc[-1]
        features = [
            latest['RSI'],
            latest['MACD'],
            latest['MACD_hist'],
            latest['MA_fast'] - latest['MA_slow'],
            latest['ATR'],
            (latest['close'] - latest['BB_lower']) / (latest['BB_upper'] - latest['BB_lower']),
            1 if latest['close'] > latest['MA_slow'] else -1
        ]
        return features
