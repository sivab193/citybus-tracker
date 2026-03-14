#!/bin/bash
# Deploy CityBus worker to a Compute Engine VM.
# Usage: ./scripts/deploy_worker_vm.sh <server_ip> [ssh_user]

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

if [ -z "$1" ]; then
    echo -e "${RED}Usage: ./scripts/deploy_worker_vm.sh <server_ip> [ssh_user]${NC}"
    exit 1
fi

SERVER_IP=$1
SSH_USER=${2:-$USER}
REMOTE_DIR="/home/$SSH_USER/citybus"

echo -e "${GREEN}=== Deploying CityBus Worker ===${NC}"
echo "Server: $SERVER_IP"
echo "User:   $SSH_USER"
echo

# Package files
DEPLOY_DIR=$(mktemp -d)
tar -czf "$DEPLOY_DIR/citybus.tar.gz" \
    --exclude='*.pyc' --exclude='__pycache__' --exclude='.git' \
    --exclude='*.pb' --exclude='.DS_Store' --exclude='venv' \
    citybus/ data/ main_worker.py main_bot.py main_api.py \
    requirements.txt .env .env.example

# Upload
scp "$DEPLOY_DIR/citybus.tar.gz" "$SSH_USER@$SERVER_IP:/tmp/"

# Remote install
ssh "$SSH_USER@$SERVER_IP" bash -s <<'REMOTE'
set -e
INSTALL_DIR="$HOME/citybus"
mkdir -p "$INSTALL_DIR" && cd "$INSTALL_DIR"
tar -xzf /tmp/citybus.tar.gz && rm /tmp/citybus.tar.gz

# Python venv
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Worker systemd service
sudo tee /etc/systemd/system/citybus-worker.service > /dev/null <<SERVICE
[Unit]
Description=CityBus Background Worker
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/main_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

# Bot systemd service
sudo tee /etc/systemd/system/citybus-bot.service > /dev/null <<SERVICE
[Unit]
Description=CityBus Telegram Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/main_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable citybus-worker citybus-bot
sudo systemctl restart citybus-worker citybus-bot

echo "Worker and bot deployed and running."
REMOTE

rm -rf "$DEPLOY_DIR"

echo
echo -e "${GREEN}✓ Worker deployed to $SERVER_IP${NC}"
echo "Logs:    ssh $SSH_USER@$SERVER_IP 'sudo journalctl -u citybus-worker -f'"
echo "Bot:     ssh $SSH_USER@$SERVER_IP 'sudo journalctl -u citybus-bot -f'"
