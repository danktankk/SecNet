"""High-level aggregation — combines data sources into dashboard views."""

from __future__ import annotations
import re
import time
import asyncio
from typing import Any
from cachetools import TTLCache
from services import data_layer as dl

_summary_cache: TTLCache = TTLCache(maxsize=1, ttl=12)
_breakdown_cache: TTLCache = TTLCache(maxsize=1, ttl=300)

_PRIVATE_RE = re.compile(r"^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.)")


def _is_public(ip: str) -> bool:
    return not _PRIVATE_RE.match(ip)


async def get_summary() -> dict[str, Any]:
    if "summary" in _summary_cache:
        return _summary_cache["summary"]

    (decisions, ssh_count, unifi_count,
     prom_active, prom_cf, prom_alerts,
     prom_lapi, prom_buckets, prom_parsers) = await asyncio.gather(
        dl.get_decisions(),
        dl.loki_count('{job=~".*logs.*"} |~ "Failed password|Invalid user"', 86400),
        dl.loki_count('{job="unifi"}', 3600),
        dl.prom_query("sum(cs_active_decisions)"),
        dl.prom_query("sum(crowdsec_cloudflare_worker_bouncer_active_decisions)"),
        dl.prom_query("sum(cs_alerts)"),
        dl.prom_query("sum(cs_lapi_bouncer_requests_total)"),
        dl.prom_query("sum(cs_bucket_poured_total)"),
        dl.prom_query("sum(cs_parser_hits_total)"),
    )

    def _prom_int(result):
        try:
            return int(float(result[0]["value"][1]))
        except (IndexError, KeyError, ValueError, TypeError):
            return 0

    active_bans = max(len(decisions), _prom_int(prom_active))
    cf_blocks = _prom_int(prom_cf)
    alert_count = _prom_int(prom_alerts)
    lapi_requests = _prom_int(prom_lapi)
    bucket_events = _prom_int(prom_buckets)
    parser_hits = _prom_int(prom_parsers)

    unique_ips = len({d.get("value", "") for d in decisions if _is_public(d.get("value", ""))})

    # Threat level based on locally detected attacks only, not community blocklist noise
    local_decisions = [d for d in decisions if d.get("origin") not in ("CAPI", "lists", "cscli")]


    local_unique_ips = len({d.get("value", "") for d in local_decisions} - {""})

    # Blocked = handled. Status reflects whether you need to DO something.
    level = "nominal"
    level_reasons: list[str] = []
    if local_unique_ips:
        level = "monitoring"
        level_reasons.append(f"{local_unique_ips} IP(s) probing perimeter — all blocked")
    if ssh_count > 500:
        level = "elevated"
        level_reasons.append(f"{ssh_count:,} SSH failures in 24h — check auth logs")
    if ssh_count > 2000:
        level = "critical"
        level_reasons = [f"{ssh_count:,} SSH failures — active brute-force overwhelming detection"]

    result = {
        "active_bans": active_bans,
        "cf_blocks": cf_blocks,
        "unique_ips": unique_ips,
        "ssh_failures": ssh_count,
        "unifi_rate": unifi_count,
        "alerts": alert_count,
        "lapi_requests": lapi_requests,
        "bucket_events": bucket_events,
        "parser_hits": parser_hits,
        "threat_level": level,
        "threat_reasons": level_reasons,
        "community_blocks": sum(1 for d in decisions if d.get("origin") in ("CAPI", "lists", "cscli")),
        "local_detections": len(local_decisions),
        "timestamp": int(time.time()),
    }
    _summary_cache["summary"] = result
    return result


async def get_decisions_with_geo() -> list[dict]:
    decisions = await dl.get_decisions()
    ips = [d.get("value", "") for d in decisions if _is_public(d.get("value", ""))]
    geo = await dl.geoip_batch(ips[:200])

    results = []
    for d in decisions:
        ip = d.get("value", "")
        entry = {
            "ip": ip,
            "reason": d.get("scenario", d.get("reason", "unknown")),
            "action": d.get("type", "ban"),
            "origin": d.get("origin", ""),
            "duration": d.get("duration", ""),
            "created_at": d.get("created_at", ""),
            "severity": "mitigated",
        }
        g = geo.get(ip)
        if g:
            entry.update({
                "country": g.get("country", ""),
                "country_code": g.get("countryCode", ""),
                "city": g.get("city", ""),
                "lat": g.get("lat"),
                "lon": g.get("lon"),
                "isp": g.get("isp", ""),
                "as": g.get("as", ""),
            })
        results.append(entry)
    return results


async def get_breakdown() -> dict:
    """Aggregate top countries, scenarios, and ISPs from active decisions. Cached 5 min."""
    if "breakdown" in _breakdown_cache:
        return _breakdown_cache["breakdown"]

    decisions = await dl.get_decisions()
    # Geo-lookup up to 1000 unique public IPs
    all_ips = list({d.get("value", "") for d in decisions if _is_public(d.get("value", ""))})
    geo = await dl.geoip_batch(all_ips[:1000])

    countries: dict = {}
    scenarios: dict = {}
    isps: dict = {}
    origins: dict = {}
    ungeolocated = 0

    for d in decisions:
        ip = d.get("value", "")
        g = geo.get(ip, {}) if _is_public(ip) else {}

        # Country
        cc = g.get("countryCode", "") or ""
        cn = g.get("country", "") or ""
        if cc and cn and cc != "XX":
            if cc not in countries:
                countries[cc] = {"code": cc, "country": cn, "count": 0}
            countries[cc]["count"] += 1
        else:
            ungeolocated += 1

        # Scenario
        sc = d.get("scenario", d.get("reason", "unknown")) or "unknown"
        scenarios[sc] = scenarios.get(sc, 0) + 1

        # ISP
        isp = g.get("isp", "") or g.get("org", "") or ""
        if isp:
            if len(isp) > 40:
                isp = isp[:40] + "…"
            isps[isp] = isps.get(isp, 0) + 1

        # Origin
        org = d.get("origin", "unknown") or "unknown"
        origins[org] = origins.get(org, 0) + 1

    top_countries = sorted(countries.values(), key=lambda x: x["count"], reverse=True)[:12]
    top_scenarios = [{"scenario": k, "count": v} for k, v in sorted(scenarios.items(), key=lambda x: x[1], reverse=True)[:10]]
    top_isps = [{"isp": k, "count": v} for k, v in sorted(isps.items(), key=lambda x: x[1], reverse=True)[:10]]
    origin_list = [{"origin": k, "count": v} for k, v in sorted(origins.items(), key=lambda x: x[1], reverse=True)]

    result = {
        "countries": top_countries,
        "scenarios": top_scenarios,
        "isps": top_isps,
        "origins": origin_list,
        "total": len(decisions),
        "ungeolocated": ungeolocated,
        "geolocated": len(all_ips[:1000]),
    }
    _breakdown_cache["breakdown"] = result
    return result


_ATTACK_TYPES = [
    # More specific rules first — prevents keyword overlap misclassification
    ("WordPress Scan",   ["wordpress"],                                                         "low"),
    ("CVE Probing",      ["cve-probing"],                                                       "high"),
    ("Admin Probing",    ["admin-interface", "admin-probing"],                                  "medium"),
    ("Bad User-Agent",   ["bad-user-agent"],                                                   "low"),
    ("Web Crawling",     ["crawl", "http-probing", "probing"],                                 "low"),
    ("Web Scanning",     ["scan"],                                                              "low"),
    # Broader critical patterns after specific ones
    ("Exploit Attempt",  ["cve", "exploit", "backdoor", "log4j", "shellshock", "rce"],         "critical"),
    ("Brute Force",      ["ssh-bf", "ftp-bf", "-bf",  "brute", "credential", "rdp", "telnet"], "critical"),
]


def _classify_attack(scenario: str) -> tuple[str, str]:
    """Returns (label, severity) for a scenario string."""
    s = scenario.lower()
    for label, keywords, severity in _ATTACK_TYPES:
        if any(k in s for k in keywords):
            return label, severity
    return "Other", "low"


async def get_threat_intel() -> dict:
    """Return structured threat intelligence: community shield vs locally detected."""
    decisions = await dl.get_decisions()

    community_blocks = 0
    local_detections: list[dict] = []

    for d in decisions:
        origin = d.get("origin", "")
        if origin in ("CAPI", "lists", "cscli"):
            community_blocks += 1
        else:
            local_detections.append(d)

    # Group local detections by attack type
    groups: dict[str, dict] = {}
    for d in local_detections:
        label, severity = _classify_attack(d.get("scenario", d.get("reason", "")))
        if label not in groups:
            groups[label] = {"type": label, "severity": severity, "count": 0, "ips": []}
        groups[label]["count"] += 1
        ip = d.get("value", "")
        if ip and len(groups[label]["ips"]) < 20:
            groups[label]["ips"].append(ip)

    # Sort by severity then count
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_groups = sorted(
        groups.values(),
        key=lambda g: (sev_order.get(g["severity"], 9), -g["count"])
    )

    has_brute_force = any(g["severity"] == "critical" for g in sorted_groups)
    has_high = any(g["severity"] in ("critical", "high") for g in sorted_groups)

    return {
        "community_blocks": community_blocks,
        "local_total": len(local_detections),
        "groups": sorted_groups,
        "has_brute_force": has_brute_force,
        "has_high_severity": has_high,
    }


async def get_timeline(range_hours: int = 24) -> list[dict]:
    end = int(time.time())
    start = end - range_hours * 3600
    step = "600" if range_hours <= 24 else "3600"

    results = await asyncio.gather(
        dl.prom_query_range("sum(cs_active_decisions)", start, end, step),
        dl.prom_query_range(f"sum(rate(cs_bucket_poured_total[10m]))*600", start, end, step),
        dl.prom_query_range(f"sum(rate(cs_parser_hits_total[10m]))*600", start, end, step),
    )

    points = {}
    keys = ["bans", "bucket_events", "parser_hits"]
    for series_list, key in zip(results, keys):
        for series in series_list:
            for ts, val in series.get("values", []):
                t = int(float(ts))
                if t not in points:
                    points[t] = {"timestamp": t, "bans": 0, "bucket_events": 0, "parser_hits": 0}
                points[t][key] = round(float(val), 1)

    return sorted(points.values(), key=lambda x: x["timestamp"])


async def get_unifi_logs(limit: int = 50) -> list[dict]:
    entries = await dl.loki_query('{job="unifi"}', limit=limit)
    return [{"timestamp": e["timestamp"], "message": e["line"]} for e in entries]


async def get_traefik_logs(limit: int = 50) -> list[dict]:
    entries = await dl.loki_query('{service_name="traefik-log-dashboard"}', limit=limit)
    return [{"timestamp": e["timestamp"], "message": e["line"]} for e in entries]


async def get_crowdsec_alerts(limit: int = 50) -> list[dict]:
    raw = await dl.get_alerts(since="24h")
    results = []
    if isinstance(raw, list):
        for a in raw[:limit]:
            src = a.get("source", {})
            ip = src.get("ip", src.get("value", ""))
            scenario = a.get("scenario", "unknown")
            created = a.get("created_at", "")
            results.append({
                "timestamp": created,
                "message": f"{scenario} -- {ip}" if ip else scenario,
            })
    return results
