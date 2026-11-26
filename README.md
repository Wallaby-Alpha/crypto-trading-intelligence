# Multi-Asset Crypto Liquidity & Derivatives Trading Intelligence System

A quantitative cryptocurrency trading research and intelligence platform continuously monitoring up to 50 perpetual futures markets simultaneously across multiple timeframes (`1m`, `5m`, `15m`, `1h`, `4h`).

Combines institutional order flow concepts:
- **ICT / Smart Money Concepts** (confirmed swing points, equal highs/lows)
- **Liquidity Sweeps & Stop Hunts** (volatility-adjusted ATR penetration, rapid reclaim)
- **Market Structure Shifts** (BOS, CHoCH, MSS with displacement confirmation)
- **Failed Breakouts & Failed Reclaims**
- **Cumulative Volume Delta (CVD)** (aggressor volume, absorption, divergences)
- **Open Interest (OI) Dynamics** (1m, 5m, 15m, 30m, 60m % changes, acceleration, 4-quadrant regimes)
- **Anchored VWAP & Volume Profile** ($\pm 1\sigma, \pm 2\sigma, \pm 3\sigma$ bands, POC, VAH, VAL)
- **0–100 Multi-Factor Confluence Scoring** with strict risk sizing ($1.0\text{R}, 2.0\text{R}, 3.0\text{R}$)
- **Event-Driven Backtesting & Quantitative Research Laboratory**
- **Live Paper Trading Portfolio & Safe WEEX Execution Layer**
- **Streamlit Web Dashboard & Telegram Notifier**

---

## Architecture Overview

```
                      ┌─────────────────────────────────────────┐
                      │        WEEX Exchange Perpetuals         │
                      │       (REST APIs & Market Feeds)        │
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │      Data Ingestion & Integrity Gate     │
                      │  - Non-fabrication & Timestamp Alignment│
                      │  - Multi-Timeframe (1m, 5m, 15m, 1h, 4h)│
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │       Quantitative Metrics Engine       │
                      │  - Aggressor CVD & Divergence           │
                      │  - 4-Quadrant Open Interest Dynamics    │
                      │  - Session VWAP & Value Area (POC/VAH)  │
                      │  - Wilder ATR & Realized Volatility     │
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │     Trading Event Detection Engine      │
                      │  - Zero Look-ahead Swing Points         │
                      │  - Liquidity Sweeps & Failed Breakouts  │
                      │  - Displacement MSS, BOS & CHoCH        │
                      │  - Bullish / Bearish Absorption Scores  │
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │  Strategy Suite & Multi-Factor Scoring  │
                      │  - 6 Modular Independent Strategies     │
                      │  - 0–100 Multi-Factor Confluence Scorer │
                      │  - 1% Account Risk Sizer & Multi-TPs    │
                      │  - Cooldown & MTF Deduplication         │
                      └──────┬──────────────────────┬───────────┘
                             │                      │
                 ┌───────────┴──────────┐ ┌─────────┴──────────┐
                 │  Historical Research │ │  Live Scanner      │
                 │  - Backtest Engine   │ │  - 50-Asset Daemon │
                 │  - Walk-Forward Split│ │  - Telegram Alerts │
                 │  - Hypothesis Testing│ │  - Streamlit Web UI│
                 └──────────────────────┘ └─────────┬──────────┘
                                                    │
                                           ┌────────┴──────────┐
                                           │  Execution Engine │
                                           │  - Paper Trading  │
                                           │  - WEEX Adapter   │
                                           │  - Kill Switch    │
                                           └───────────────────┘
```

---

## 6 Independent Trading Strategies

1. **Strategy 1: Liquidity Sweep Reversal**
   - High/low liquidity sweep $\ge 0.1 \text{ATR}$, reclaim $\le 3$ candles, bullish/bearish displacement MSS, and CVD absorption.
2. **Strategy 2: OI Expansion & Failed Breakout**
   - Price breaks out while OI accelerates, followed by failed acceptance, CVD divergence, and reclaim.
3. **Strategy 3: Failed Reclaim Continuation**
   - Structural support/resistance break, failed retest from below/above, directional continuation.
4. **Strategy 4: CVD Divergence Reversal**
   - Price establishes extreme highs/lows while Cumulative Volume Delta diverges with absorption $\ge 60$.
5. **Strategy 5: Momentum Breakout**
   - Structure break with displacement candle body $\ge 1.2 \text{ATR}$ and volume expansion $\ge 1.5\times$ SMA.
6. **Strategy 6: VWAP & Volume Profile Mean Reversion**
   - Price extends beyond VWAP $\pm 2\sigma$ or Value Area High/Low, then displays exhaustion and reverts towards POC.

---

## 0–100 Multi-Factor Scoring Rubric

Each trade signal is independently scored from 0 to 100 based on quantifiable objective evidence:

| Component Factor | Max Points | Evaluation Criteria |
| :--- | :---: | :--- |
| **Liquidity Quality** | **15** | Sweep penetration $\ge 0.1 \text{ATR}$, fast reclaim, clean wick ratio |
| **Market Structure** | **15** | Displacement MSS/BOS candle $\ge 1.2 \text{ATR}$, confirmed swings |
| **Open Interest Behavior**| **15** | Favorable 4-quadrant regime, short-squeeze or trap unwinding |
| **CVD Divergence** | **15** | Quantified aggressor absorption score (0–100) |
| **Volume & Displacement**| **10** | Breakout candle volume $\ge 1.5\times$ 20-period moving average |
| **VWAP Alignment** | **10** | Favorable positioning relative to session VWAP and $\pm 1\sigma, \pm 2\sigma$ bands |
| **Higher Timeframe Bias**| **10** | 15-minute / 1-hour trend and structure confluence |
| **Funding Context** | **5** | Extreme positive/negative funding positioning exhaustion |
| **Risk-to-Reward Quality**| **5** | Minimum $1 : 2.0$ ratio to Take Profit 2 |
| **TOTAL** | **100** | **$\ge 90$: Exceptional, 80–89: Strong, 65–79: Qualified, 50–64: Watchlist** |

---

## Quickstart & CLI Commands

### 1. Run Automated Unit Test Suite (35/35 Passing):
```powershell
python -m pytest tests -v
```

### 2. Run Historical Backtesting & Quantitative Research Lab:
```powershell
python main.py backtest
```
*Outputs win rate, profit factor, expectancy R, score tier predictive power, ATR sensitivity, and out-of-sample walk-forward validation.*

### 3. Run Live 50-Asset Intelligence Scanner Daemon:
```powershell
# Continuous 60-second scanning loop
python main.py scan

# Or run a single cycle and exit
python main.py scan --single
```

### 4. Launch Interactive Streamlit Dashboard:
```powershell
python main.py dashboard
# Opens at http://localhost:8501
```

### 5. Emergency Execution Kill-Switch:
```powershell
python main.py kill
```

---

## Telegram Notifications Format (Section 12 Compliant)

When a signal exceeds the qualification threshold ($\ge 65.0$), an alert is dispatched:

```
🟢 [STRONG] LONG SETUP DETECTED
Asset: BTC/USDT | Timeframe: 5m
Strategy: LiquiditySweepReversal
Confluence Score: 84.0 / 100

🎯 EXECUTION LEVELS:
• Entry: $96,000.0000
• Stop Loss: $95,200.0000 (0.83%)
• Take Profit 1: $96,800.0000 (1.0R - 33% exit)
• Take Profit 2: $97,600.0000 (2.0R - 33% exit)
• Take Profit 3: $98,400.0000 (3.0R - 34% runner)
• Risk-to-Reward: 1 : 2.0
• Recommended Pos: $12,500 (1% account risk)

🔍 CONFIRMATION FACTORS:
• Liquidity Sweep: 14.0/15
• Market Structure: 13.5/15
• Open Interest: 12.0/15
• Cumulative Delta: 13.0/15
• Volume & VWAP: 15.0/20
• HTF Confluence: 8.0/10

⚡ KEY TRIGGERS:
  ✓ Low sweep at $95,300
  ✓ Bullish MSS confirmed
  ✓ Bullish CVD absorption
```

---

## DigitalOcean Ubuntu Deployment

Systemd service templates are available in `systemd/`:

1. Copy repository to `/home/ubuntu/crypto_trading_intelligence`
2. Create python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy environment configuration:
   ```bash
   cp .env.example .env
   # Edit .env with your Telegram bot token and credentials
   ```
4. Install systemd services:
   ```bash
   sudo cp systemd/crypto-scanner.service /etc/systemd/system/
   sudo cp systemd/crypto-dashboard.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now crypto-scanner.service
   sudo systemctl enable --now crypto-dashboard.service
   ```
5. Monitor logs:
   ```bash
   journalctl -u crypto-scanner.service -f
   ```

---

## Safety Guarantees & Non-Negotiables

1. **Zero Look-Ahead Bias:** Swing points at candle $i$ with $R$ right confirmation bars are only registered at candle $i + R$.
2. **Data Integrity:** Incomplete candles are flagged with `is_closed=False` and excluded from signal generation. Missing data is never silently substituted with zeros.
3. **Real-Money Isolation:** Real trading on WEEX is strictly disabled by default (`ENABLE_LIVE_TRADING=false`). Live execution requires explicit API credentials and authorization.
4. **Protective Stops:** Every order placed contains automated Stop-Loss and Take-Profit brackets. Trailing stops automatically lock in breakeven upon Take Profit 1.
