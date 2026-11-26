"""
Abstract Base Class for Trading Strategies.
Each strategy is independently configured, enabled/disabled, evaluated, and backtested.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from src.events.models import MarketEventBundle
from src.strategies.models import TradeSignal, SignalDirection
from src.strategies.scoring import SignalScorer
from src.strategies.risk_sizer import RiskSizer


class BaseStrategy(ABC):
    def __init__(self, name: str, is_enabled: bool = True, parameters: Optional[Dict[str, Any]] = None):
        self.name = name
        self.is_enabled = is_enabled
        self.parameters = parameters or {}
        self.scorer = SignalScorer()
        self.risk_sizer = RiskSizer()

    @abstractmethod
    def evaluate(
        self,
        bundle: MarketEventBundle,
        current_price: float,
        atr_value: float,
        funding_rate: Optional[float] = None,
        htf_aligned: bool = False,
        htf_trend: str = "NEUTRAL"
    ) -> Optional[TradeSignal]:
        """
        Evaluates the market event bundle and returns a TradeSignal if conditions are satisfied.
        """
        pass

