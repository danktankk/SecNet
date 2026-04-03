#!/usr/bin/env bash
set -e

# SecNet macOS Agent Installer
# Usage: sudo bash install-mac.sh --url http://SECNET:8088 --key YOUR_KEY

URL="" KEY=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --url) URL="$2"; shift 2;;
    --key) KEY="$2"; shift 2;;
    *) echo "Unknown: $1"; exit 1;;
  esac
done

if [[ -z "$URL" || -z "$KEY" ]]; then
  echo "Usage: sudo bash install-mac.sh --url http://SECNET:8088 --key YOUR_KEY"
  exit 1
fi

if [[ $EUID -ne 0 ]]; then echo "Run with sudo"; exit 1; fi

echo "Installing SecNet agent..."

# Find python3
PYTHON3=$(command -v python3 || command -v python || true)
if [[ -z "$PYTHON3" ]]; then
  echo "ERROR: python3 not found. Install it with: brew install python3"
  exit 1
fi

# Install deps via python3 -m pip (works regardless of pip3 PATH)
"$PYTHON3" -m pip install --quiet --break-system-packages psutil requests 2>/dev/null || \
  "$PYTHON3" -m pip install --quiet psutil requests

# Download or copy agent
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_PY="$SCRIPT_DIR/secnet-agent-mac.py"
if [[ ! -f "$AGENT_PY" ]]; then
  echo "Downloading agent from GitHub..."
  curl -fsSL "https://raw.githubusercontent.com/danktankk/SecNet/main/agents/secnet-agent-mac.py" \
    -o /tmp/secnet-agent-mac.py || { echo "ERROR: download failed"; exit 1; }
  AGENT_PY="/tmp/secnet-agent-mac.py"
fi
cp "$AGENT_PY" /usr/local/bin/secnet-agent
chmod +x /usr/local/bin/secnet-agent

mkdir -p /etc/secnet
cat > /etc/secnet/agent.json << CONF
{"url": "$URL", "key": "$KEY"}
CONF
chmod 600 /etc/secnet/agent.json

cat > /Library/LaunchDaemons/com.secnet.agent.plist << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.secnet.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3</string>
        <string>/usr/local/bin/secnet-agent</string>
        <string>run</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/var/log/secnet-agent.log</string>
    <key>StandardErrorPath</key><string>/var/log/secnet-agent.log</string>
    <key>ThrottleInterval</key><integer>10</integer>
</dict>
</plist>
PLIST

launchctl load /Library/LaunchDaemons/com.secnet.agent.plist

echo ""
echo "Done. Service loaded."
echo "Check: launchctl list com.secnet.agent"
echo "Logs:  tail -f /var/log/secnet-agent.log"
