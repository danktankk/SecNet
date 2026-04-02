from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # All fields default to empty so the app starts without a .env file.
    # Unconfigured services degrade gracefully — their tabs show a
    # "not configured" message in the UI.

    crowdsec_url: str = ""
    crowdsec_api_key: str = ""
    loki_url: str = ""
    prometheus_url: str = ""
    unifi_url: str = ""
    unifi_username: str = ""
    unifi_password: str = ""
    security_gate_code: str = ""
    openai_api_key: str = ""

    # Optional with safe non-sensitive defaults
    geoip_provider: str = "ip-api"
    geoip_rate_limit: int = 45
    poll_interval: int = 15
    openai_model: str = "gpt-4.1-mini"

    # Proxmox nodes — optional (empty string = node not configured)
    pve1_url: str = ""
    pve1_token: str = ""
    pve2_url: str = ""
    pve2_token: str = ""
    pve3_url: str = ""
    pve3_token: str = ""

    # Database path
    secnet_db: str = "/data/secnet.db"

    workstation_agent_key: str = ""
    enable_workstations: bool = True

    # Feature flags — set to false to disable a data source entirely.
    # Disabled services return empty data; their tabs hide in the UI.
    enable_crowdsec: bool = True
    enable_unifi: bool = True
    enable_proxmox: bool = True
    enable_loki: bool = True
    enable_prometheus: bool = True
    enable_openai: bool = True


settings = Settings()
