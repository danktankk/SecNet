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
# Try apt first (Debian/Ubuntu), fall back to python3 -m pip
if command -v apt-get &>/dev/null; then
  apt-get install -y -q python3-psutil python3-requests 2>/dev/null || \
    python3 -m pip install --quiet --break-system-packages psutil requests
else
  python3 -m pip install --quiet --break-system-packages psutil requests 2>/dev/null || \
    python3 -m pip install --quiet psutil requests
fi

# Download agent
AGENT_URL="${URL%/}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_PY="$SCRIPT_DIR/secnet-agent-linux.py"
if [[ ! -f "$AGENT_PY" ]]; then
  echo "Downloading agent from GitHub..."
  curl -fsSL "https://raw.githubusercontent.com/danktankk/SecNet/main/agents/secnet-agent-linux.py" \
    -o /tmp/secnet-agent-linux.py || { echo "ERROR: download failed"; exit 1; }
  AGENT_PY="/tmp/secnet-agent-linux.py"
fi
cp "$AGENT_PY" /usr/local/bin/secnet-agent
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
