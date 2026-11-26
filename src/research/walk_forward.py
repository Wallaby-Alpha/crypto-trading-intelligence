"""
Walk-Forward Validation & In-Sample / Out-of-Sample Splitter.
Protects against overfitting by dividing historical data into:
- In-Sample (Training / Parameter Selection)
- Out-of-Sample (Blind Verification)
- Walk-forward rolling windows
"""
from typing import List, Dict, Any, Tuple
from src.core.models import Candle
from src.research.models import BacktestReport
from src.research.backtest_engine import BacktestEngine


class WalkForwardValidator:
    def __init__(self, backtest_engine: BacktestEngine):
        self.engine = backtest_engine

    def split_in_out_of_sample(
        self,
        candles: List[Candle],
        in_sample_ratio: float = 0.70
    ) -> Tuple[List[Candle], List[Candle]]:
        """
        Splits candles temporally into In-Sample (first 70%) and Out-of-Sample (last 30%).
        """
        split_idx = int(len(candles) * in_sample_ratio)
        return candles[:split_idx], candles[split_idx:]

    def run_train_test_validation(
        self,
        symbol: str,
        timeframe: str,
        candles: List[Candle],
        in_sample_ratio: float = 0.70
    ) -> Dict[str, BacktestReport]:
        """
        Runs backtest independently on In-Sample and Out-of-Sample periods.
        """
        in_sample_candles, out_sample_candles = self.split_in_out_of_sample(candles, in_sample_ratio)

        report_in = self.engine.run_backtest(
            symbol=symbol,
            timeframe=timeframe,
            candles=in_sample_candles,
            experiment_name=f"{symbol}_{timeframe}_IN_SAMPLE"
        )

        report_out = self.engine.run_backtest(
            symbol=symbol,
            timeframe=timeframe,
            candles=out_sample_candles,
            experiment_name=f"{symbol}_{timeframe}_OUT_OF_SAMPLE"
        )

        return {
            "in_sample": report_in,
            "out_of_sample": report_out
        }

