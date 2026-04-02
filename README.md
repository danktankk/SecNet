<p align="right">
  <img src="https://img.shields.io/badge/status-beta-blue" />
  <img src="https://img.shields.io/badge/docker-compose-orange" />
  <img src="https://img.shields.io/badge/license-AGPL--3.0-blue" />
  <img src="https://img.shields.io/badge/agents-win_linux_mac-8A2BE2" />
</p>

# SecNet

> Not production ready.  While it is mostly read only, you should always review the code and be mindful of upstream dependencies.  Use at your own risk

Real-time security and network operations dashboard for homelabs. One screen to monitor everything: firewall bans, network devices, hypervisor health, endpoint status, and event logs.

SecNet pulls live data from sources you add (CrowdSec, UniFi, Proxmox, Loki, and Prometheus, etc) then presents it in a single tabbed interface. An OpenAI-powered HelpDesk lets you ask relevant questions about your infrastructure without leaving the dashboard.

Every integration is optional. Only have CrowdSec and UniFi? The dashboard shows those tabs and hides the rest. No errors, no empty screens. Add more services later by dropping their credentials into `.env`.

Built with FastAPI and React, packaged as a single Docker container.

## Screenshots

> All screenshots below show demo data, not a real network.

### Security Overview

Live threat level, active ban count, attacker geo-map, 24-hour ban trends, and a full attack breakdown grouped by severity (Critical, High, Medium, Low). Each group expands to show the individual attacker IPs.

<img src="docs/screenshots/mock-01-security.png" width="120%" />

### Infrastructure

Host registry organized by group (Core, Nodes, Tools, Workstations). Each host shows online/offline status with live port checks. Proxmox hypervisors display CPU, RAM, and guest counts. Sensitive operations like port scanning require gate credentials.

<img src="docs/screenshots/mock-02-infrastructure.png" width="100%" />

### Network Health

Three-column layout. Left: gateway and switches with realistic port faceplate graphics (color-coded by link speed, amber borders for PoE). Center: access points with per-radio channel utilization bars and client counts. Right: intelligence panel with bandwidth hogs, weak WiFi clients, firmware alerts, and client distribution by VLAN.

<img src="docs/screenshots/mock-03-network.png" width="100%" />

### Workstations

Cross-platform endpoint monitoring via lightweight agents (Windows, Linux, macOS). Filter by health status (Healthy, Suspicious, Compromised). Expand any workstation to see running processes with flags (credential dump, injection, recon), system utilization, and a security event log with timestamps and event IDs.

<img src="docs/screenshots/mock-04-workstations.png" width="100%" />

### Logs

Four live feeds side by side: CrowdSec active bans (filterable by LOCAL/CAPI), attack origins broken down by country and ISP, UniFi network events, and attack scenario breakdown by type and severity.

<img src="docs/screenshots/mock-05-logs.png" width="100%" />

### HelpDesk (API driven)

A low cost and relatively basic OpenAI-powered assistant [will add additional options if requested] that knows your dashboard context. It will (should) answer general security questions related to security without authentication. Questions about your specific infrastructure (IPs, bans, topology) require gate credentials first. Includes example prompts for both categories.

<img src="docs/screenshots/mock-06-helpdesk.png" width="100%" />

## Features

- **Fullscreen mode** for wall-mounted displays, tablets, or dedicated monitoring screens. Works on desktop and mobile browsers via the Fullscreen API.
- **Dark and light themes** with a one-click toggle
- **Stale-data-first loading** using localStorage caching. The dashboard shows cached data instantly on load, then updates in the background with a subtle indicator. No "Loading..." screens after your first visit.
- **WebSocket live feed** pushes summary updates every 15 seconds without polling
- **Auth gate** with server-side validation, rate limiting (5 attempts/minute), and constant-time comparison
- **Feature flags** to enable/disable any integration via environment variables
- **Workstation agents** for Windows, Linux, and macOS that report as native OS services

### Coming Soon

- **Windows installer (EXE)** for standalone desktop use
- **Android app (APK)** for mobile monitoring

## Quick Start

### Using Docker Compose (recommended)

```bash
git clone https://github.com/danktankk/SecNet.git
cd SecNet

# Set up your configuration
cp .env.example .env
# Edit .env with your service URLs and API keys

# Start the dashboard
docker compose up -d
```

### Building from source

If you prefer to build the image yourself:

```bash
docker compose up -d --build
```

### Seeding the host database (optional)

The Infrastructure tab reads hosts from a SQLite database. To populate it with your own infrastructure:

```bash
cp scripts/init-db.example.py scripts/init-db.py
# Edit scripts/init-db.py with your hosts, IPs, and roles

docker run --rm -v $(pwd)/data:/data -v $(pwd)/scripts:/scripts python:3.12-slim \
  python /scripts/init-db.py
```

Open `http://localhost:8088` (or your host IP on port 8088).

## Workstation Agents

Lightweight agents report system stats, top processes, and security events to the Workstations tab every 30 seconds. Each platform agent runs as a native OS service -- no terminal windows to keep open.

### Prerequisites (all platforms)

```bash
pip install psutil requests
```

Set `WORKSTATION_AGENT_KEY` in your SecNet `.env` and `ENABLE_WORKSTATIONS=true` (default).

---

### Windows

**Requirements:** Python 3.10+, `pywin32` (`pip install pywin32`)

**What it collects:** CPU, RAM, disk, top 40 processes, Windows Security Event Log (logon, logon failures, privilege escalation, service installs), AD domain.

```powershell
# 1. Install dependencies
pip install psutil requests pywin32

# 2. Configure (run as Administrator)
python agents\secnet-agent.py setup --url http://YOUR_SECNET:8088 --key YOUR_AGENT_KEY

# 3. Install as Windows service (run as Administrator)
python agents\secnet-agent.py install

# 4. Start the service
python agents\secnet-agent.py start
```

**Management commands:**

| Command | Description |
|---------|-------------|
| `secnet-agent.py setup --url URL --key KEY` | Create/update config at `C:\ProgramData\SecNet\agent.json` |
| `secnet-agent.py install` | Install Windows service (requires admin) |
| `secnet-agent.py start` | Start the service |
| `secnet-agent.py stop` | Stop the service |
| `secnet-agent.py remove` | Uninstall the service |
| `secnet-agent.py run` | Run in foreground (console mode, for testing) |
| `secnet-agent.py status` | Show config, connection, and service status |

**Config file:** `C:\ProgramData\SecNet\agent.json`
**Service log:** `C:\ProgramData\SecNet\agent.log`
**Service name:** `SecNetAgent` (visible in `services.msc`)

**Troubleshooting:**
- "Access denied" on install/start -> run PowerShell as Administrator
- Service won't start -> check `C:\ProgramData\SecNet\agent.log` and run `secnet-agent.py status`
- `pywin32` not found -> run `python Scripts/pywin32_postinstall.py -install` after pip install

---

### Linux

**What it collects:** CPU, RAM, disk, top 40 processes, SSH auth events (journalctl or `/var/log/auth.log` fallback), distro info.

```bash
# 1. Install dependencies
pip3 install psutil requests

# 2. Configure
sudo python3 agents/secnet-agent-linux.py setup --url http://YOUR_SECNET:8088 --key YOUR_AGENT_KEY

# 3. Install as systemd service
sudo python3 agents/secnet-agent-linux.py install

# 4. Start
sudo systemctl start secnet-agent
```

**Management commands:**

| Command | Description |
|---------|-------------|
| `setup --url URL --key KEY` | Create config at `/etc/secnet/agent.json` |
| `install` | Copy to `/usr/local/bin/secnet-agent`, create systemd unit, enable service |
| `run` | Run in foreground (for testing) |
| `status` | Show config and `systemctl` status |

**Config file:** `/etc/secnet/agent.json` (mode 0600)
**Service unit:** `/etc/systemd/system/secnet-agent.service`
**Logs:** `journalctl -u secnet-agent -f`

**After install:**
```bash
sudo systemctl start secnet-agent    # start now
sudo systemctl status secnet-agent   # check it's running
journalctl -u secnet-agent -f        # tail logs
```

---

### macOS

**What it collects:** CPU, RAM, disk, top 40 processes, Unified Log security events (securityd, sshd, authentication), macOS version.

```bash
# 1. Install dependencies
pip3 install psutil requests

# 2. Configure
sudo python3 agents/secnet-agent-mac.py setup --url http://YOUR_SECNET:8088 --key YOUR_AGENT_KEY

# 3. Install as launchd service
sudo python3 agents/secnet-agent-mac.py install

# 4. Load the service
sudo launchctl load /Library/LaunchDaemons/com.secnet.agent.plist
```

**Management commands:**

| Command | Description |
|---------|-------------|
| `setup --url URL --key KEY` | Create config at `/etc/secnet/agent.json` |
| `install` | Copy to `/usr/local/bin/secnet-agent`, create launchd plist |
| `run` | Run in foreground (for testing) |
| `status` | Show config and launchd status |

**Config file:** `/etc/secnet/agent.json` (mode 0600)
**Plist:** `/Library/LaunchDaemons/com.secnet.agent.plist`
**Log file:** `/var/log/secnet-agent.log`

**After install:**
```bash
sudo launchctl load /Library/LaunchDaemons/com.secnet.agent.plist     # start
sudo launchctl unload /Library/LaunchDaemons/com.secnet.agent.plist   # stop
tail -f /var/log/secnet-agent.log                                      # logs
```

---

### Agent Architecture

All three agents share the same design:

1. **Config file** (`agent.json`) stores the dashboard URL and API key. Created once with `setup`, read on every start. No command-line args needed after setup.
2. **Native service** (Windows Service / systemd / launchd) starts automatically on boot, restarts on failure, logs to the OS logging system.
3. **30-second loop** collects system stats, top processes, and platform-specific security events, then POSTs to `/api/workstations/report`.
4. **Graceful shutdown** responds to OS stop signals (SIGTERM, service stop) within 1 second.
5. **Legacy mode** still supported: `python agent.py --url URL --key KEY` works for quick testing without setup/install.

```
  Workstation                          SecNet Server
  +-----------+     POST /api/         +-------------+
  |  Agent    | ---> workstations/ --> |  Dashboard   |
  |  (service)|     report             |  :8088       |
  +-----------+     every 30s          +-------------+
       |                                     |
  OS events,                           Workstations tab
  processes,                           shows live data
  CPU/RAM/disk
```

## Configuration

All configuration lives in `.env`. See `.env.example` for the full list with comments.

### Integrations

Every integration is optional. Configure only what you have.

| Integration | Required Variables | What You Get |
|------------|-------------------|--------------|
| CrowdSec | `CROWDSEC_URL`, `CROWDSEC_API_KEY` | Ban tracking, attacker geo-mapping, threat intel, attack breakdown |
| UniFi | `UNIFI_URL`, `UNIFI_USERNAME`, `UNIFI_PASSWORD` | AP health, switch port status, client monitoring, VLAN distribution |
| Proxmox | `PVE1_URL`, `PVE1_TOKEN` (supports up to 3 nodes) | Hypervisor CPU/RAM, VM and container inventory |
| Loki | `LOKI_URL` | Log aggregation, Traefik and CrowdSec event feeds |
| Prometheus | `PROMETHEUS_URL` | Metrics and alerting data |
| OpenAI | `OPENAI_API_KEY` | AI security assistant (HelpDesk tab) |
| Workstations | `WORKSTATION_AGENT_KEY` | Endpoint monitoring via platform agents |

### Feature Flags

Explicitly disable any integration by setting its flag to `false`:

```bash
ENABLE_CROWDSEC=false
ENABLE_UNIFI=false
ENABLE_PROXMOX=false
ENABLE_LOKI=false
ENABLE_PROMETHEUS=false
ENABLE_OPENAI=false
ENABLE_WORKSTATIONS=false
```

Disabled integrations return empty data from their API endpoints. The frontend hides tabs and sections that have no active data source. The Security tab is always visible since it aggregates from multiple sources and degrades gracefully.

### Auth Gate

Set `SECURITY_GATE_CODE` to protect sensitive operations (network scans, AI chat with infrastructure context). The gate uses server-side validation with rate limiting and constant-time string comparison.

## Architecture

```
SecNet/
  backend/
    config.py          # Pydantic settings, feature flags
    main.py            # FastAPI app, lifespan, static file serving
    db.py              # SQLite connection, schema init
    routers/
      api.py           # REST endpoints, auth gate, rate limiting
      ws.py            # WebSocket live feed
    services/
      aggregator.py    # Data aggregation, threat level calculation
      chat.py          # OpenAI chat with gate enforcement
      data_layer.py    # CrowdSec, Loki, Prometheus API clients
      hosts.py         # Host registry from SQLite
      network.py       # Proxmox inventory, nmap port scanning
      unifi.py         # UniFi clients, devices, health
      workstations.py  # In-memory workstation store
  frontend/
    src/
      App.jsx          # Tab layout, feature-aware routing
      hooks/useApi.js  # Polling with localStorage cache
      components/      # One component per tab
  agents/
    secnet-agent.py         # Windows agent (service + console)
    secnet-agent-linux.py   # Linux agent (systemd + console)
    secnet-agent-mac.py     # macOS agent (launchd + console)
  docker-compose.yml
  Dockerfile           # Multi-stage build: Node frontend + Python backend
```

The frontend is compiled at image build time and served as static files by FastAPI. A WebSocket connection pushes live summary updates. HTTP polling with localStorage caching means the dashboard loads instantly on return visits, showing cached data while fresh data arrives in the background.

## Security

- Auth gate is validated server-side only. The frontend sends a token header; the backend checks it.
- Gate-check endpoint is rate-limited: 5 attempts per 60 seconds per IP.
- Gate code comparison uses `hmac.compare_digest` to prevent timing attacks.
- nmap scan input is validated with `ipaddress.ip_address()` before execution.
- All secrets live in `.env` (gitignored). The repository ships with zero credentials.
- Agent config files are stored with restricted permissions (0600 on Linux/macOS).
- A pre-push secret scanner is included at `scripts/check-secrets.py`.

## License

AGPL-3.0. See [LICENSE](LICENSE) for details.
