import numpy as np

class RiskManager:
    def __init__(self, config):
        self.config = config
        self.min_tp_points = config.MIN_TP_POINTS
        self.min_rrr = config.MIN_RRR

    def calculate_sl_tp(self, direction: str, df) -> tuple:
        """Hitung SL dan TP dinamis berdasarkan ATR dan struktur."""
        latest = df.iloc[-1]
        atr = latest['ATR']
        if np.isnan(atr) or atr == 0:
            return None, None

        entry = latest['close']

        if direction == 'BUY':
            # SL di bawah swing low 10 candle terakhir atau 1.5*ATR
            swing_low = df['low'].tail(10).min()
            sl = min(swing_low, entry - 1.5 * atr)
            tp = entry + max(self.min_tp_points, 2 * atr)
        else:
            swing_high = df['high'].tail(10).max()
            sl = max(swing_high, entry + 1.5 * atr)
            tp = entry - max(self.min_tp_points, 2 * atr)

        # Validasi RRR
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk == 0:
            return None, None

        rrr = reward / risk
        if rrr < self.min_rrr:
            required_risk = reward / self.min_rrr
            if direction == 'BUY':
                sl = entry - required_risk
            else:
                sl = entry + required_risk

        return round(sl, 2), round(tp, 2)
