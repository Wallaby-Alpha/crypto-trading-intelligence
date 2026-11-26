"""
Volume Profile Engine:
- Discretizes price range into bins to construct Volume Profile.
- Computes Point of Control (POC) - highest traded volume node.
- Computes Value Area High (VAH) and Value Area Low (VAL) - 70% of total traded volume.
- Identifies High Volume Nodes (HVN) and Low Volume Nodes (LVN).
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import numpy as np
from src.core.models import Candle


class VolumeProfileResult(BaseModel):
    poc_price: float
    vah_price: float
    val_price: float
    total_volume: float
    value_area_volume: float
    hvn_levels: List[float]
    lvn_levels: List[float]
    price_bins: List[float]
    volume_bins: List[float]


class VolumeProfileEngine:
    def __init__(self, num_bins: int = 50, value_area_pct: float = 0.70):
        self.num_bins = num_bins
        self.value_area_pct = value_area_pct

    def compute_profile(self, candles: List[Candle]) -> Optional[VolumeProfileResult]:
        if not candles:
            return None

        min_price = min(c.low for c in candles)
        max_price = max(c.high for c in candles)

        if min_price >= max_price:
            return None

        # Create uniform price bins
        bin_edges = np.linspace(min_price, max_price, self.num_bins + 1)
        bin_volumes = np.zeros(self.num_bins)

        # Distribute volume across bins proportional to candle range overlap
        for c in candles:
            c_high = c.high
            c_low = c.low
            vol = max(c.volume, 0.0)

            if vol == 0:
                continue

            c_range = max(c_high - c_low, 1e-6)

            # Find overlapping bins
            for b in range(self.num_bins):
                b_low = bin_edges[b]
                b_high = bin_edges[b + 1]

                # Check overlap
                overlap_low = max(c_low, b_low)
                overlap_high = min(c_high, b_high)

                if overlap_high > overlap_low:
                    fraction = (overlap_high - overlap_low) / c_range
                    bin_volumes[b] += vol * fraction

        total_volume = float(np.sum(bin_volumes))
        if total_volume <= 0:
            return None

        # Midpoint of each bin
        bin_mids = 0.5 * (bin_edges[:-1] + bin_edges[1:])

        # Point of Control (POC): bin with maximum volume
        poc_idx = int(np.argmax(bin_volumes))
        poc_price = float(bin_mids[poc_idx])

        # Value Area (70% total volume around POC)
        target_va_vol = total_volume * self.value_area_pct
        current_va_vol = bin_volumes[poc_idx]
        up_idx = poc_idx
        down_idx = poc_idx

        while current_va_vol < target_va_vol and (up_idx < self.num_bins - 1 or down_idx > 0):
            next_up_vol = bin_volumes[up_idx + 1] if up_idx + 1 < self.num_bins else 0.0
            next_down_vol = bin_volumes[down_idx - 1] if down_idx - 1 >= 0 else 0.0

            if next_up_vol >= next_down_vol and up_idx + 1 < self.num_bins:
                up_idx += 1
                current_va_vol += next_up_vol
            elif down_idx - 1 >= 0:
                down_idx -= 1
                current_va_vol += next_down_vol
            elif up_idx + 1 < self.num_bins:
                up_idx += 1
                current_va_vol += next_up_vol
            else:
                break

        val_price = float(bin_mids[down_idx])
        vah_price = float(bin_mids[up_idx])

        # High Volume Nodes (peaks in bin volume) and Low Volume Nodes (troughs)
        hvn_levels: List[float] = []
        lvn_levels: List[float] = []
        mean_bin_vol = float(np.mean(bin_volumes))

        for i in range(1, self.num_bins - 1):
            if bin_volumes[i] > bin_volumes[i - 1] and bin_volumes[i] > bin_volumes[i + 1] and bin_volumes[i] > 1.2 * mean_bin_vol:
                hvn_levels.append(float(bin_mids[i]))
            elif bin_volumes[i] < bin_volumes[i - 1] and bin_volumes[i] < bin_volumes[i + 1] and bin_volumes[i] < 0.6 * mean_bin_vol:
                lvn_levels.append(float(bin_mids[i]))

        return VolumeProfileResult(
            poc_price=poc_price,
            vah_price=vah_price,
            val_price=val_price,
            total_volume=total_volume,
            value_area_volume=float(current_va_vol),
            hvn_levels=hvn_levels[:5],
            lvn_levels=lvn_levels[:5],
            price_bins=[float(x) for x in bin_mids],
            volume_bins=[float(x) for x in bin_volumes]
        )

