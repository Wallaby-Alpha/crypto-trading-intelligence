# DigitalOcean Droplet Deployment Guide: WEEX Autonomous Trading Bot

This guide walks you through deploying the cryptocurrency trading bot 24/7 on a **$4–$6/month DigitalOcean Ubuntu Droplet** to trade on WEEX with **de minimis amounts** ($10–$25 margin per trade).

---

## 1. Prerequisites Checklist

1. **DigitalOcean Account**: Sign up at [digitalocean.com](https://www.digitalocean.com).
2. **WEEX Account & API Keys**:
   - Log in to WEEX -> Account Settings -> **API Management**.
   - Create API Key with permissions: **Futures / Contract Trading** (Read & Trade).
   - ⚠️ **DO NOT enable Withdrawals** (never needed for trading).
   - Save your:
     * `API Key`
     * `Secret Key`
     * `Passphrase`
3. **Telegram Bot (For real-time trade telemetry)**:
   - Message `@BotFather` on Telegram -> `/newbot` -> name your bot -> copy the `HTTP API Token`.
   - Message `@userinfobot` on Telegram -> copy your numeric `Id` (this is your `CHAT_ID`).

---

## 2. Launching Your DigitalOcean Droplet

1. Click **Create** -> **Droplets**.
2. **Region**: Choose a region close to exchange servers (e.g., **Singapore**, **Frankfurt**, or **New York**).
3. **OS**: **Ubuntu 24.04 (LTS) x64**.
4. **Droplet Size**: **Basic Droplet** -> **Regular CPU** ($4–$6/month with 1GB RAM / 1 vCPU / 25GB NVMe SSD is plenty).
5. **Authentication**: Select **SSH Key** (recommended) or set a secure root password.
6. Click **Create Droplet**. Note the assigned public IP address (e.g., `159.65.120.45`).

---

## 3. Connecting to Your Droplet & Setup

Open your terminal or PowerShell and connect to your droplet:
```bash
ssh root@YOUR_DROPLET_IP
```

### Option A: 1-Click Automated Setup (Recommended)

1. Upload the bot directory to your droplet via `rsync` or `scp` from your local machine:
```bash
# Run this on your local machine:
rsync -avz --exclude='.git' --exclude='__pycache__' ./ root@YOUR_DROPLET_IP:/root/crypto_trading_intelligence
```

2. SSH into your droplet and run the installer:
```bash
cd /root/crypto_trading_intelligence
chmod +x deploy_droplet.sh
./deploy_droplet.sh
```

---

## 4. Configuring Your Environment (`.env`)

Edit your `.env` file directly on the droplet:
```bash
nano .env
```

Ensure your configuration matches your de minimis testing goals:
```ini
# WEEX API Credentials
WEEX_API_KEY=your_actual_weex_api_key
WEEX_SECRET=your_actual_weex_api_secret
WEEX_PASSPHRASE=your_actual_weex_passphrase

# MASTER SWITCH: Set to true when ready for real-money execution
ENABLE_LIVE_TRADING=true

# DE MINIMIS RISK CONTROLS
TRADE_AMOUNT_USD=15.0            # $15 margin allocation per trade
DEFAULT_LEVERAGE=2               # Conservative 2x isolated margin
MAX_CONCURRENT_POSITIONS=2       # Maximum 2 concurrent open positions across universe
MAX_DAILY_LOSS_USD=25.0          # Daily circuit breaker: halts trading if loss hits $25

# TELEGRAM ALERTS
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=123456789
```
*Press `CTRL+O` then `ENTER` to save, and `CTRL+X` to exit.*

---

## 5. Starting the Autonomous Bot

Launch the Docker containers in the background:
```bash
sudo docker compose up -d
```

### Checking Live Status & Logs
Watch real-time market scans, candle calculations, and trade entries:
```bash
sudo docker compose logs -f weex-bot
```

### Checking Bot Process Health
```bash
sudo docker compose ps
```

---

## 6. How the Bot Protects Your Capital

1. **Strict 1H Trend Alignment**:
   - In macro bull trends, it buys only discount liquidity sweeps.
   - In macro bear trends, it sells only premium liquidity sweeps.
   - It **never** counter-trend shorts or knife-catches runaway cascades.
2. **De Minimis Sizing**:
   - Every trade risks only **$10–$15 margin** at **2x isolated leverage** (~$30 notional).
   - Even in worst-case slippage, no single trade can damage account equity.
3. **Automated Breakeven Trailing**:
   - When a trade reaches **TP1 ($1.0\text{R}$)**, the bot immediately cancels the original stop and moves the Stop Loss to **Breakeven**. The trade becomes risk-free.
4. **Emergency Kill Switch**:
   - If you ever need to halt everything immediately, cancel all open orders, and market-close all positions, run:
```bash
sudo docker compose exec weex-bot python run_live_bot.py --kill
```

---

## 7. Accessing the Visual Dashboard (Optional)

If you enabled port 8501 in the firewall, you can view your live Streamlit dashboard in any browser:
```
http://YOUR_DROPLET_IP:8501
```

