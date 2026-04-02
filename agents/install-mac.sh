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

pip3 install --quiet psutil requests 2>/dev/null || pip install --quiet psutil requests

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/secnet-agent-mac.py" ]]; then
  cp "$SCRIPT_DIR/secnet-agent-mac.py" /usr/local/bin/secnet-agent
else
  echo "ERROR: secnet-agent-mac.py not found in $SCRIPT_DIR"
  exit 1
fi
chmod +x /usr/local/bin/secnet-agent

mkdir -p /etc/secnet
cat > /etc/secnet/agent.json << EOF
{"url": "$URL", "key": "$KEY"}
EOF
chmod 600 /etc/secnet/agent.json

cat > /Library/LaunchDaemons/com.secnet.agent.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.secnet.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
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
EOF

launchctl load /Library/LaunchDaemons/com.secnet.agent.plist

echo ""
echo "Done. Service loaded."
echo "Check: launchctl list com.secnet.agent"
echo "Logs:  tail -f /var/log/secnet-agent.log"
