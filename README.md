# SecNet

A self-hosted security dashboard for homelabs. Pulls data from CrowdSec, UniFi, Proxmox, Loki, Prometheus, and OpenAI into a single real-time view. FastAPI backend, React frontend, single Docker container.

All integrations are optional. If a service is not configured, its tab hides automatically and the dashboard runs with whatever you have.

---

## Screenshots

### Security Overview
Threat level, active bans, attacker geo-map, ban trends, attack breakdown by type and severity.

![Security Tab](docs/screenshots/secnet-01-security.png)

### Infrastructure
Host registry with live port checks, grouped by role. Proxmox hypervisor stats with CPU/RAM and guest counts. Gate-locked for sensitive operations.

![Infrastructure Tab](docs/screenshots/secnet-02-infrastructure.png)

### Network Health
Three-column layout: switches with port faceplate graphics, APs with radio utilization and client counts, intelligence panel with bandwidth hogs, weak WiFi signals, firmware alerts, and VLAN distribution.

![Network Tab](docs/screenshots/secnet-03-network.png)

Expand a switch to see the full port table with names, link speeds, and PoE wattage per port.

![Network Expanded](docs/screenshots/secnet-03b-network-expanded.png)

### Workstations
Windows endpoint monitoring with process lists, event logs, and security alerts. Ships with mock data by default -- wire to WinRM or an agent for live feeds.

![Workstations Tab](docs/screenshots/secnet-04-workstations.png)

Expand a workstation to see system details, running processes with flags, and the event log timeline.

![Workstations Expanded](docs/screenshots/secnet-04b-workstations-expanded.png)

### Logs
Four-panel feed: CrowdSec active bans, attack origins by country/ISP, UniFi events, and attack scenario breakdown.

![Logs Tab](docs/screenshots/secnet-05-logs.png)

### AI HelpDesk
OpenAI-powered security assistant. General questions work without auth. Sensitive data (IPs, bans, topology) requires gate credentials. Example prompts included.

![HelpDesk](docs/screenshots/secnet-06-helpdesk.png)

---

## Quick Start

```bash
# Clone
git clone https://github.com/danktankk/SecNet.git
cd SecNet

# Configure
cp .env.example .env
# Edit .env with your service URLs and API keys

# Seed the database (optional -- customize with your hosts first)
cp scripts/init-db.example.py scripts/init-db.py
# Edit scripts/init-db.py with your infrastructure
docker run --rm -v $(pwd)/data:/data -v $(pwd)/scripts:/scripts python:3.12-slim \
  python /scripts/init-db.py

# Run
docker compose up -d --build
```

Open `http://localhost:8088` (or your host IP on port 8088).

## Configuration

All configuration is via environment variables in `.env`. See `.env.example` for the full list.

### Required for each integration

| Integration | Variables | What it provides |
|------------|-----------|-----------------|
| CrowdSec | `CROWDSEC_URL`, `CROWDSEC_API_KEY` | Ban tracking, threat intel, attacker geo-mapping |
| UniFi | `UNIFI_URL`, `UNIFI_USERNAME`, `UNIFI_PASSWORD` | Network health, AP stats, client monitoring, switch ports |
| Proxmox | `PVE1_URL`, `PVE1_TOKEN` (up to 3 nodes) | Hypervisor stats, VM/CT inventory |
| Loki | `LOKI_URL` | Log aggregation, event feeds |
| Prometheus | `PROMETHEUS_URL` | Metrics, alerting data |
| OpenAI | `OPENAI_API_KEY` | AI security assistant (HelpDesk) |

None of these are required. The dashboard starts and runs with whatever you configure.

### Feature Flags

Disable any integration explicitly by setting its flag to `false` in `.env`:

```bash
ENABLE_CROWDSEC=false
ENABLE_UNIFI=false
ENABLE_PROXMOX=false
ENABLE_LOKI=false
ENABLE_PROMETHEUS=false
ENABLE_OPENAI=false
```

### Auth Gate

Set `SECURITY_GATE_CODE` in `.env` to protect sensitive operations (network scans, AI chat with infrastructure context). The gate is server-side validated with rate limiting (5 attempts per minute) and constant-time comparison.

### Host Registry

The Infrastructure tab reads from a SQLite database. Copy and edit the example seed script:

```bash
cp scripts/init-db.example.py scripts/init-db.py
# Add your hosts, IPs, roles, and services
```

The database is stored in `./data/secnet.db` (bind-mounted into the container).

## Architecture

```
SecNet/
  backend/
    config.py          # Pydantic settings, feature flags
    main.py            # FastAPI app, lifespan, static serving
    db.py              # SQLite connection, schema init
    routers/
      api.py           # REST endpoints, auth gate, rate limiting
      ws.py            # WebSocket live feed
    services/
      aggregator.py    # Data aggregation, threat level logic
      chat.py          # OpenAI chat with gate enforcement
      data_layer.py    # CrowdSec, Loki, Prometheus clients
      hosts.py         # Host registry from SQLite
      network.py       # Proxmox inventory, nmap scanning
      unifi.py         # UniFi clients, devices, health
  frontend/
    src/
      App.jsx          # Tab layout, feature-aware routing
      hooks/useApi.js  # Polling with localStorage cache, stale-data-first UX
      components/      # One component per tab/feature
      styles/global.css
  docker-compose.yml
  Dockerfile           # Multi-stage: Node build + Python runtime
```

Single container. Frontend is built at image build time and served as static files by FastAPI. WebSocket provides real-time updates; HTTP polling with localStorage caching provides stale-data-first loading so the dashboard feels instant on refresh.

## Security Notes

- Gate authentication is server-side only. The frontend sends a token header; the backend validates it.
- Rate limiting on gate-check: 5 attempts per 60 seconds per IP.
- Gate comparison uses `hmac.compare_digest` (constant-time).
- nmap scan input is validated with `ipaddress.ip_address()` before execution.
- All secrets live in `.env` (gitignored). The repo ships with no credentials.
- A pre-push secret scanner is included (`scripts/check-secrets.py`).

## License

MIT
