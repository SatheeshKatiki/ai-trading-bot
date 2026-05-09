"""AI Trade Filter — ML model for scoring trade confidence.

Uses a Random Forest classifier (with optional XGBoost) to predict whether a
trade signal is likely to be profitable. The model outputs:

* buy_probability
* sell_probability
* confidence_score (max of the two)

Low-confidence signals are automatically rejected.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

logger = logging.getLogger(__name__)

# Default path for the persisted model
_MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
_MODEL_PATH = _MODEL_DIR / "trade_filter_rf.pkl"


class TradeFilterModel:
    """ML-based trade confidence scorer.

    The model classifies each bar into one of three classes:
        1 = profitable long, -1 = profitable short, 0 = no-trade

    Usage::

        model = TradeFilterModel()
        model.train(features_df, labels_series)
        pred = model.predict(features_df)
        # pred -> DataFrame with columns: prediction, buy_prob, sell_prob, confidence
    """

    def __init__(self, min_confidence: float = 0.55):
        """
        Parameters
        ----------
        min_confidence : float
            Minimum confidence threshold (0-1). Predictions below this are
            downgraded to 0 (no-trade).
        """
        self.min_confidence = min_confidence
        self.model: Optional[RandomForestClassifier] = None
        self.feature_names: list[str] = []
        self._load_if_exists()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_if_exists(self) -> None:
        """Load a previously trained model from disk if available."""
        if _MODEL_PATH.is_file():
            try:
                with open(_MODEL_PATH, "rb") as f:
                    data = pickle.load(f)
                self.model = data["model"]
                self.feature_names = data["feature_names"]
                logger.info("Loaded trade filter model from %s", _MODEL_PATH)
            except Exception as exc:
                logger.warning("Could not load model: %s", exc)

    def save(self) -> None:
        """Persist the trained model to disk."""
        _MODEL_DIR.mkdir(parents=True, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({
                "model": self.model,
                "feature_names": self.feature_names,
            }, f)
        logger.info("Model saved to %s", _MODEL_PATH)

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def _generate_labels(self, df: pd.DataFrame, forward_returns_col: str = "close",
                         horizon: int = 5, threshold: float = 0.002) -> pd.Series:
        """Generate training labels from forward returns.

        Parameters
        ----------
        df : DataFrame
            Must contain the ``forward_returns_col`` column.
        horizon : int
            Number of bars to look ahead for the return.
        threshold : float
            Minimum return to count as a profitable trade (e.g. 0.002 = 0.2%).

        Returns
        -------
        pandas.Series
            1 = profitable long, -1 = profitable short, 0 = neutral.
        """
        fwd = df[forward_returns_col].shift(-horizon)
        ret = (fwd - df[forward_returns_col]) / df[forward_returns_col]
        labels = pd.Series(0, index=df.index, dtype=int)
        labels[ret > threshold] = 1
        labels[ret < -threshold] = -1
        return labels

    def train(
        self,
        features: pd.DataFrame,
        labels: Optional[pd.Series] = None,
        ohlcv_df: Optional[pd.DataFrame] = None,
        test_size: float = 0.2,
        n_estimators: int = 200,
        use_xgboost: bool = False,
    ) -> dict:
        """Train the trade filter model.

        Parameters
        ----------
        features : DataFrame
            Feature matrix (from ``compute_features``).
        labels : Series, optional
            Pre-computed labels. If None, labels are auto-generated from
            ``ohlcv_df`` using forward returns.
        ohlcv_df : DataFrame, optional
            Original OHLCV data (needed for auto-label generation).
        test_size : float
            Fraction of data for validation.
        n_estimators : int
            Number of trees in the forest.
        use_xgboost : bool
            If True, use XGBClassifier instead of RandomForest.

        Returns
        -------
        dict
            Training report with accuracy, classification report, etc.
        """
        if labels is None:
            if ohlcv_df is None:
                raise ValueError("Either labels or ohlcv_df must be provided")
            labels = self._generate_labels(ohlcv_df)
            # Align features and labels
            common_idx = features.index.intersection(labels.dropna().index)
            features = features.loc[common_idx]
            labels = labels.loc[common_idx]

        # Drop any remaining NaNs
        mask = features.notna().all(axis=1) & labels.notna()
        features = features[mask]
        labels = labels[mask]

        self.feature_names = list(features.columns)

        X_train, X_test, y_train, y_test = train_test_split(
            features, labels, test_size=test_size, shuffle=False
        )

        if use_xgboost:
            try:
                from xgboost import XGBClassifier
                self.model = XGBClassifier(
                    n_estimators=n_estimators,
                    max_depth=6,
                    learning_rate=0.1,
                    use_label_encoder=False,
                    eval_metric="mlogloss",
                )
            except ImportError:
                logger.warning("XGBoost not installed, falling back to RandomForest")
                self.model = RandomForestClassifier(
                    n_estimators=n_estimators, max_depth=10, random_state=42
                )
        else:
            self.model = RandomForestClassifier(
                n_estimators=n_estimators, max_depth=10, random_state=42, n_jobs=-1
            )

        self.model.fit(X_train, y_train)
        self.save()

        y_pred = self.model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

        logger.info("Model trained. Test accuracy: %.2f%%", acc * 100)
        return {"accuracy": acc, "report": report, "train_size": len(X_train), "test_size": len(X_test)}

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        """Score trade signals using the trained model.

        Parameters
        ----------
        features : DataFrame
            Feature matrix (must have the same columns as training data).

        Returns
        -------
        DataFrame with columns:
            prediction : int (1, -1, or 0)
            buy_prob   : float (probability of profitable long)
            sell_prob   : float (probability of profitable short)
            confidence : float (max probability)
        """
        if self.model is None:
            logger.warning("No trained model available - returning neutral predictions")
            return pd.DataFrame({
                "prediction": 0,
                "buy_prob": 0.33,
                "sell_prob": 0.33,
                "confidence": 0.33,
            }, index=features.index)

        # Ensure feature alignment
        X = features[self.feature_names] if self.feature_names else features

        preds = self.model.predict(X)
        proba = self.model.predict_proba(X)

        # Map class probabilities
        classes = list(self.model.classes_)
        buy_idx = classes.index(1) if 1 in classes else None
        sell_idx = classes.index(-1) if -1 in classes else None

        buy_prob = proba[:, buy_idx] if buy_idx is not None else np.zeros(len(X))
        sell_prob = proba[:, sell_idx] if sell_idx is not None else np.zeros(len(X))
        confidence = np.maximum(buy_prob, sell_prob)

        # Apply confidence threshold
        filtered_preds = np.where(confidence >= self.min_confidence, preds, 0)

        return pd.DataFrame({
            "prediction": filtered_preds,
            "buy_prob": np.round(buy_prob, 4),
            "sell_prob": np.round(sell_prob, 4),
            "confidence": np.round(confidence, 4),
        }, index=features.index)

    @property
    def is_trained(self) -> bool:
        return self.model is not None

    def feature_importance(self) -> pd.Series:
        """Return feature importance scores (only after training)."""
        if not self.is_trained or not self.feature_names:
            return pd.Series(dtype=float)
        return pd.Series(
            self.model.feature_importances_,
            index=self.feature_names,
        ).sort_values(ascending=False)
