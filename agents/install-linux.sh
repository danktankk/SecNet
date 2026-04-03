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

# Ensure python3-venv is available (required on Debian/Ubuntu)
if command -v apt-get &>/dev/null; then
  apt-get install -y -q python3-venv python3-full 2>/dev/null || true
fi

# Create venv — avoids all system pip / PEP 668 issues
VENV=/opt/secnet-venv
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet psutil requests

# Download or copy agent
SCRIPT_SRC="${BASH_SOURCE[0]:-}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SRC")" 2>/dev/null && pwd || echo '')"
AGENT_PY="$SCRIPT_DIR/secnet-agent-linux.py"
if [[ ! -f "$AGENT_PY" ]]; then
  echo "Downloading agent from GitHub..."
  curl -fsSL "https://raw.githubusercontent.com/danktankk/SecNet/main/agents/secnet-agent-linux.py" \
    -o /tmp/secnet-agent-linux.py || { echo "ERROR: download failed"; exit 1; }
  AGENT_PY="/tmp/secnet-agent-linux.py"
fi
cp "$AGENT_PY" /usr/local/bin/secnet-agent
chmod +x /usr/local/bin/secnet-agent

mkdir -p /etc/secnet
cat > /etc/secnet/agent.json << CONF
{"url": "$URL", "key": "$KEY"}
CONF
chmod 600 /etc/secnet/agent.json

cat > /etc/systemd/system/secnet-agent.service << UNIT
[Unit]
Description=SecNet Monitoring Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/secnet-venv/bin/python /usr/local/bin/secnet-agent run
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable secnet-agent
systemctl start secnet-agent

echo ""
echo "Done. Checking status..."
sleep 2
systemctl status secnet-agent --no-pager -l
