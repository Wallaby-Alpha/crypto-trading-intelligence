#!/bin/bash
# ==============================================================================
# Automated 1-Click Deployment Script for DigitalOcean Ubuntu Droplet
# ==============================================================================
set -e

echo "=========================================================="
echo " Starting WEEX Crypto Trading Bot Deployment on Droplet   "
echo "=========================================================="

# 1. Update and install prerequisites
echo "[1/5] Updating system packages..."
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release ufw git

# 2. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "[2/5] Installing Docker Engine..."
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo systemctl enable docker
    sudo systemctl start docker
else
    echo "[2/5] Docker is already installed."
fi

# 3. Configure Basic Security / Firewall
echo "[3/5] Configuring UFW Firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw allow 8501/tcp comment 'Streamlit Dashboard (Optional)'
sudo ufw --force enable

# 4. Environment File Setup
echo "[4/5] Checking environment configuration..."
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  PLEASE EDIT YOUR .env FILE WITH YOUR WEEX API KEYS & TELEGRAM TOKENS:"
    echo "    nano .env"
fi

# 5. Build and Launch Containers
echo "[5/5] Building and launching containers via Docker Compose..."
sudo docker compose build
sudo docker compose up -d

echo "=========================================================="
echo " ✅ DEPLOYMENT COMPLETE! Bot is running in the background."
echo "=========================================================="
echo " Useful Commands:"
echo "   - Check live logs:       sudo docker compose logs -f weex-bot"
echo "   - Restart bot:           sudo docker compose restart weex-bot"
echo "   - Stop bot:              sudo docker compose down"
echo "   - Emergency Kill Switch: sudo docker compose exec weex-bot python run_live_bot.py --kill"
echo "=========================================================="

