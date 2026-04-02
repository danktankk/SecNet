# SecNet

Real-time security and network operations dashboard for homelabs. One screen to monitor everything: firewall bans, network devices, hypervisor health, endpoint status, and event logs.

SecNet pulls live data from CrowdSec, UniFi, Proxmox, Loki, and Prometheus, then presents it in a single tabbed interface. An OpenAI-powered HelpDesk lets you ask questions about your infrastructure without leaving the dashboard.

Every integration is optional. Only have CrowdSec and UniFi? The dashboard shows those tabs and hides the rest. No errors, no empty screens. Add more services later by dropping their credentials into `.env`.

Built with FastAPI and React, packaged as a single Docker container.

## Screenshots

> All screenshots below show demo data, not a real network.

### Security Overview

Live threat level, active ban count, attacker geo-map, 24-hour ban trends, and a full attack breakdown grouped by severity (Critical, High, Medium, Low). Each group expands to show the individual attacker IPs.

<img src="docs/screenshots/mock-1-security.png" width="100%" />

### Infrastructure

Host registry organized by group (Core, Nodes, Tools, Workstations). Each host shows online/offline status with live port checks. Proxmox hypervisors display CPU, RAM, and guest counts. Sensitive operations like port scanning require gate credentials.

<img src="docs/screenshots/mock-02-infrastructure.png" width="100%" />

### Network Health

Three-column layout. Left: gateway and switches with realistic port faceplate graphics (color-coded by link speed, amber borders for PoE). Center: access points with per-radio channel utilization bars and client counts. Right: intelligence panel with bandwidth hogs, weak WiFi clients, firmware alerts, and client distribution by VLAN.

<img src="docs/screenshots/mock-03-network.png" width="100%" />

### Workstations

Windows endpoint monitoring. Filter by health status (Healthy, Suspicious, Compromised). Expand any workstation to see running processes with flags (credential dump, injection, recon), system utilization, and a security event log with timestamps and Windows event IDs. Ships with demo data. Wire to WinRM or an agent for live feeds.

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

### Feature Flags

Explicitly disable any integration by setting its flag to `false`:

```bash
ENABLE_CROWDSEC=false
ENABLE_UNIFI=false
ENABLE_PROXMOX=false
ENABLE_LOKI=false
ENABLE_PROMETHEUS=false
ENABLE_OPENAI=false
```

Disabled integrations hide their tabs from the UI entirely.

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
  frontend/
    src/
      App.jsx          # Tab layout, feature-aware routing
      hooks/useApi.js  # Polling with localStorage cache
      components/      # One component per tab
      styles/global.css
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
- A pre-push secret scanner is included at `scripts/check-secrets.py`.

## License

AGPL-3.0. See [LICENSE](LICENSE) for details.
