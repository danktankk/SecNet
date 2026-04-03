#!/usr/bin/env bash
set -e

# SecNet Linux Agent Installer
# Usage: sudo bash install-linux.sh --url http://SECNET:8088 --key YOUR_KEY

URL="" KEY=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --url) URL="$2"; shift 2;;
    --key) KEY="$2"; shift 2;;
    *) echo "Unknown: $1"; exit 1;;
  esac
done

if [[ -z "$URL" || -z "$KEY" ]]; then
  echo "Usage: sudo bash install-linux.sh --url http://SECNET:8088 --key YOUR_KEY"
  exit 1
fi

if [[ $EUID -ne 0 ]]; then echo "Run with sudo"; exit 1; fi

echo "Installing SecNet agent..."

# Install deps
# Try apt first (Debian/Ubuntu), fall back to pip with --break-system-packages
if command -v apt-get &>/dev/null; then
  apt-get install -y -q python3-psutil python3-requests 2>/dev/null || \
    pip3 install --quiet --break-system-packages psutil requests
else
  pip3 install --quiet --break-system-packages psutil requests 2>/dev/null || \
    pip install --quiet --break-system-packages psutil requests
fi

# Download agent
AGENT_URL="${URL%/}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/secnet-agent-linux.py" ]]; then
  cp "$SCRIPT_DIR/secnet-agent-linux.py" /usr/local/bin/secnet-agent
else
  echo "ERROR: secnet-agent-linux.py not found in $SCRIPT_DIR"
  exit 1
fi
chmod +x /usr/local/bin/secnet-agent

# Save config
mkdir -p /etc/secnet
cat > /etc/secnet/agent.json << EOF
{"url": "$URL", "key": "$KEY"}
EOF
chmod 600 /etc/secnet/agent.json

# Create systemd unit
cat > /etc/systemd/system/secnet-agent.service << EOF
[Unit]
Description=SecNet Monitoring Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/secnet-agent run
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable secnet-agent
systemctl start secnet-agent

echo ""
echo "Done. Checking status..."
sleep 2
systemctl status secnet-agent --no-pager -l
