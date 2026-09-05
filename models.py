import os
import logging
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from hmmlearn import hmm
from filterpy.kalman import KalmanFilter
import joblib

logger = logging.getLogger(__name__)

class ModelManager:
    def __init__(self, config):
        self.config = config
        self.scaler = StandardScaler()
        self.rf_model = None
        self.hmm_model = None
        self._load_models()

    def _load_models(self):
        # Load RandomForest / XGBoost filter
        model_path = os.path.join(self.config.MODEL_DIR, "rf_filter.pkl")
        if os.path.exists(model_path):
            self.rf_model = joblib.load(model_path)
            logger.info("RandomForest filter model loaded")
        else:
            logger.warning("RandomForest model not found. Fallback to rule-based.")

        # Load HMM regime
        hmm_path = os.path.join(self.config.MODEL_DIR, "hmm_regime.pkl")
        if os.path.exists(hmm_path):
            self.hmm_model = joblib.load(hmm_path)
            logger.info("HMM regime model loaded")
        else:
            # HMM fallback sederhana (3 state)
            self.hmm_model = hmm.GaussianHMM(n_components=3, covariance_type="full", n_iter=100)
            # Fit dengan data dummy agar tidak error saat predict
            dummy = np.random.randn(100, 2)
            self.hmm_model.fit(dummy)
            logger.warning("HMM model not found. Using untrained fallback.")

    def rf_filter(self, features: list) -> float:
        """Return probabilitas sinyal valid (0-1)."""
        if self.rf_model is not None:
            X = self.scaler.transform([features])
            prob = self.rf_model.predict_proba(X)[0][1]
            return prob
        else:
            # Rule-based fallback: nilai > 0.7 dianggap valid
            # Fitur terakhir adalah indikator arah (1 jika bullish)
            return 0.7 if features[-1] > 0 else 0.3

    def hmm_regime(self, returns: np.ndarray, volatility: np.ndarray) -> int:
        """Deteksi regime pasar (0=down, 1=range, 2=up)."""
        if self.hmm_model is not None:
            obs = np.column_stack([returns, volatility])
            if len(obs) == 0:
                return 1
            state = self.hmm_model.predict(obs)[-1]
            return state
        else:
            # Fallback: gunakan threshold volatilitas
            avg_vol = np.mean(volatility)
            if avg_vol > 0.5:
                return 2  # high volatility, treat as trending
            else:
                return 1

    def kalman_filter(self, prices: np.ndarray) -> np.ndarray:
        """Kalman filter untuk estimasi mean."""
        kf = KalmanFilter(dim_x=2, dim_z=1)
        kf.x = np.array([prices[0], 0.])
        kf.F = np.array([[1., 1.], [0., 1.]])
        kf.H = np.array([[1., 0.]])
        kf.P *= 1000.
        kf.R = 5
        kf.Q = np.array([[0.1, 0.], [0., 0.01]])
        estimates = []
        for z in prices:
            kf.predict()
            kf.update(z)
            estimates.append(kf.x[0])
        return np.array(estimates)
