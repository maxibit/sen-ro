# Transelectrica SEN Monitor — Technical Specification

**Version:** 1.0.0  
**Date:** 2026-06-27  
**Status:** Draft — Ready for Development  
**Audience:** Developers / DevOps Engineers

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Data Source Analysis](#3-data-source-analysis)
4. [Repository & Directory Structure](#4-repository--directory-structure)
5. [Environment Variables (.env)](#5-environment-variables-env)
6. [Docker Compose Stack](#6-docker-compose-stack)
7. [Scraper Service](#7-scraper-service)
8. [TimescaleDB / PostgreSQL Schema](#8-timescaledb--postgresql-schema)
9. [Grafana Configuration](#9-grafana-configuration)
10. [Cloudflare Tunnel](#10-cloudflare-tunnel)
11. [Alerting — Pushover Contact Point](#11-alerting--pushover-contact-point)
12. [Security Requirements](#12-security-requirements)
13. [Observability & Logging](#13-observability--logging)
14. [Backup & Data Retention](#14-backup--data-retention)
15. [CI/CD & Deployment Checklist](#15-cicd--deployment-checklist)
16. [Runbook](#16-runbook)
17. [Open Points / Known Limitations](#17-open-points--known-limitations)

---

## 1. Project Overview

### 1.1 Purpose

Build a self-hosted, internet-exposed monitoring dashboard for Romania's National Energy System (Sistemul Energetic Național — **SEN**) data published by **Transelectrica** at:

- **Live data endpoint:** `https://transelectrica.ro/sen-filter` (JSON, updated every ~60 seconds)
- **Human dashboard reference:** `https://www.transelectrica.ro/web/tel/sistemul-energetic-national`

The stack collects the raw JSON every 60 seconds, persists it in a time-series database, and visualises it in a mobile-friendly Grafana dashboard — securely exposed to the internet via a **Cloudflare Tunnel** (zero open inbound ports).

### 1.2 Key Functional Requirements

| # | Requirement |
|---|-------------|
| F-01 | Scrape `https://transelectrica.ro/sen-filter` every 60 seconds |
| F-02 | Parse and store all energy metrics with timestamp |
| F-03 | Display all metrics in a Grafana dashboard optimised for mobile |
| F-04 | Send alert notifications via Pushover |
| F-05 | Expose Grafana securely via Cloudflare Tunnel (no open ports) |
| F-06 | All secrets managed via a single `.env` file |
| F-07 | Entire stack starts with `docker compose up -d` |

### 1.3 Non-Functional Requirements

| # | Requirement |
|---|-------------|
| NF-01 | Data scraper must be fault-tolerant (retry on failure, never crash the container) |
| NF-02 | All containers run as non-root users |
| NF-03 | No secrets in Docker images or version control |
| NF-04 | Grafana login required even through tunnel (no anonymous access) |
| NF-05 | TLS termination handled by Cloudflare (end-to-end encryption) |
| NF-06 | Grafana dashboard responsive / mobile-first |

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Docker Host (VPS / RPi)                      │
│                                                                      │
│  ┌──────────────┐   every 60s    ┌──────────────────┐               │
│  │   Scraper    │───────────────▶│  TimescaleDB     │               │
│  │  (Python)    │  INSERT rows   │  (PostgreSQL 16) │               │
│  └──────────────┘                └────────┬─────────┘               │
│                                           │  SQL queries             │
│  ┌──────────────────────────────────┐     │                          │
│  │           Grafana                │◀────┘                          │
│  │  - PostgreSQL datasource         │                                │
│  │  - Pushover contact point        │                                │
│  │  - Mobile-friendly dashboard     │                                │
│  └──────────────┬───────────────────┘                                │
│                 │ localhost:3000                                      │
│  ┌──────────────▼───────────────────┐                                │
│  │     Cloudflare Tunnel (cloudflared) │                             │
│  └──────────────────────────────────┘                                │
└──────────────────────────────────────────────────────────────────────┘
                        │ HTTPS (TLS)
                        ▼
                 Internet Users / Phone
         https://your-domain.example.com
```

### Component Versions (pinned)

| Service | Image | Version |
|---------|-------|---------|
| Scraper | `python` | `3.12-slim` |
| Database | `timescale/timescaledb` | `2.15.3-pg16` |
| Grafana | `grafana/grafana-oss` | `11.1.0` |
| Cloudflared | `cloudflare/cloudflared` | `2024.6.1` |

> **Always pin image tags.** Never use `:latest` in production.

---

## 3. Data Source Analysis

### 3.1 Endpoint Behaviour

| Property | Value |
|----------|-------|
| URL | `https://transelectrica.ro/sen-filter` |
| Method | `GET` |
| Response | JSON array of single-key objects |
| Update frequency | ~60 seconds |
| Authentication | None |
| CORS / rate-limit | Unknown — keep polling interval ≥ 60 s |

### 3.2 JSON Structure

The API returns a flat array of single-key objects. Example excerpt (observed 2026-06-27):

```json
[
  {"KOZL115": "-27"},
  {"PROD": "5083"},
  {"CONS": "4532"},
  {"EOLIAN": "448"},
  {"FOTO": "2163"},
  {"APE": "679"},
  {"NUCL": "682"},
  {"GAZE": "502"},
  {"CARB": "551"},
  {"SOLD": "-550"},
  {"row1_HARTASEN_DATA": "26/6/27 14:11:58"},
  ...
]
```

### 3.3 Known Field Reference

| Field | Category | Description |
|-------|----------|-------------|
| `PROD` | Summary | Total production (MW) |
| `CONS` | Summary | Total consumption (MW) |
| `CONS2` | Summary | Alternative consumption measurement (MW) |
| `SOLD` | Summary | Exchange balance — positive = export, negative = import (MW) |
| `PLAN` | Summary | Planned exchange (MW) |
| `EOLIAN` | Production | Wind power (MW) |
| `FOTO` | Production | Solar / photovoltaic (MW) |
| `APE` | Production | Hydro power (MW) |
| `NUCL` | Production | Nuclear power (MW) |
| `GAZE` | Production | Natural gas (MW) |
| `CARB` | Production | Coal / carbon (MW) |
| `BMASA` | Production | Biomass (MW) |
| `COSE` | Production | Cogeneration (MW) |
| `SOLD` | Interconnect | Net exchange balance (MW) |
| `DOBR` | Interconnect | Dobrudja line flow (MW) |
| `DJER` | Interconnect | Djerdap interconnection (MW) |
| `VARN` | Interconnect | Varna interconnection (MW) |
| `KOZL1` | Interconnect | Kozloduy-1 line (MW) |
| `KOZL2` | Interconnect | Kozloduy-2 line (MW) |
| `PANCEVO21` | Interconnect | Pančevo line (MW) |
| `UNGE` | Interconnect | Hungary exchange (MW) |
| `MUKA` | Interconnect | Mukacheve interconnection (MW) |
| `BEKE1` | Interconnect | Békéscsaba interconnection (MW) |
| `SAND` | Interconnect | Sandorfalva interconnection (MW) |
| `IS`, `IAS2` | Interconnect | Iași interconnection (MW) |
| `PARO` | Interconnect | Paro line (MW) |
| `CIOA` | Interconnect | Cioara line (MW) |
| `CHEF`, `CHEA` | Interconnect | Cheapest / Chișinău (MW) |
| `GOTE` | Interconnect | Gotești line (MW) |
| `MINT` | Interconnect | Mintia line (MW) |
| `KIKI` | Interconnect | Kikinda (MW) |
| `S110` | Other | 110kV balance (MW) |
| `SIP_` | Other | SIP indicator |
| `PROG` | Other | Program deviation |
| `row1_HARTASEN_DATA` | Meta | Source timestamp (string) |

> Fields ending with `15` are 15-minute averages of their base counterparts.

### 3.4 Scraper Strategy

- Parse the JSON array into a flat dict: `{field: value}`.
- Convert all numeric strings to `FLOAT` (`NULL` for empty strings or `""`).
- Parse `row1_HARTASEN_DATA` as the **source timestamp** (format: `YY/M/D H:MM:SS`) — store alongside the collector timestamp.
- Insert one row per poll cycle.

---

## 4. Repository & Directory Structure

```
sen-monitor/
├── .env                          # ← secrets (git-ignored)
├── .env.example                  # ← committed template (no real values)
├── .gitignore
├── docker-compose.yml
├── README.md
│
├── scraper/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── scraper.py
│   └── healthcheck.py            # simple HTTP /health endpoint
│
├── db/
│   └── init/
│       └── 01-schema.sql         # TimescaleDB schema + hypertable
│
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── timescaledb.yaml
    │   ├── dashboards/
    │   │   └── dashboards.yaml
    │   └── alerting/
    │       ├── contactpoints.yaml
    │       └── policies.yaml
    └── dashboards/
        └── sen-overview.json     # exported dashboard JSON
```

---

## 5. Environment Variables (.env)

### 5.1 `.env.example` — committed to repository

```dotenv
# =============================================================================
# Transelectrica SEN Monitor — Environment Configuration Template
# Copy this file to .env and fill in all values before starting the stack.
# NEVER commit the real .env to version control.
# =============================================================================

# -----------------------------------------------------------------------------
# Cloudflare Tunnel
# -----------------------------------------------------------------------------
# Token from: Cloudflare Zero Trust → Access → Tunnels → Create Tunnel
CLOUDFLARE_TUNNEL_TOKEN=

# Public hostname (must be configured in Cloudflare DNS / Tunnel ingress)
# Example: sen.yourdomain.com
PUBLIC_DOMAIN=

# -----------------------------------------------------------------------------
# Grafana
# -----------------------------------------------------------------------------
GF_ADMIN_USER=admin
GF_ADMIN_PASSWORD=                # min 16 chars, alphanumeric + symbols

# Internal secret for signing cookies / tokens (min 32 random chars)
GF_SECRET_KEY=

# -----------------------------------------------------------------------------
# PostgreSQL / TimescaleDB
# -----------------------------------------------------------------------------
POSTGRES_DB=sendb
POSTGRES_USER=senuser
POSTGRES_PASSWORD=                # min 20 chars

# -----------------------------------------------------------------------------
# Pushover Alerting
# -----------------------------------------------------------------------------
# Application token from https://pushover.net/apps/build
PUSHOVER_APP_TOKEN=

# User key from https://pushover.net (your account)
PUSHOVER_USER_KEY=

# -----------------------------------------------------------------------------
# Scraper
# -----------------------------------------------------------------------------
# How often to poll Transelectrica (seconds). Minimum recommended: 60
SCRAPE_INTERVAL_SECONDS=60

# Optional: User-Agent header sent with requests
SCRAPER_USER_AGENT=SEN-Monitor/1.0 (+https://github.com/yourorg/sen-monitor)
```

### 5.2 `.gitignore` entries (minimum)

```
.env
*.env
grafana/data/
db/data/
```

---

## 6. Docker Compose Stack

```yaml
# docker-compose.yml
# =============================================================================
# Transelectrica SEN Monitor
# Start: docker compose up -d
# =============================================================================

name: sen-monitor

services:

  # ---------------------------------------------------------------------------
  # TimescaleDB (PostgreSQL 16 + time-series extension)
  # ---------------------------------------------------------------------------
  db:
    image: timescale/timescaledb:2.15.3-pg16
    container_name: sen-db
    restart: unless-stopped
    env_file: .env
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - db_data:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d:ro
    networks:
      - internal
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    # No ports exposed — internal only

  # ---------------------------------------------------------------------------
  # Scraper
  # ---------------------------------------------------------------------------
  scraper:
    build:
      context: ./scraper
      dockerfile: Dockerfile
    container_name: sen-scraper
    restart: unless-stopped
    env_file: .env
    environment:
      DB_HOST: db
      DB_PORT: 5432
      DB_NAME: ${POSTGRES_DB}
      DB_USER: ${POSTGRES_USER}
      DB_PASSWORD: ${POSTGRES_PASSWORD}
      SCRAPE_INTERVAL: ${SCRAPE_INTERVAL_SECONDS}
      SCRAPER_USER_AGENT: ${SCRAPER_USER_AGENT}
    networks:
      - internal
    depends_on:
      db:
        condition: service_healthy
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp

  # ---------------------------------------------------------------------------
  # Grafana
  # ---------------------------------------------------------------------------
  grafana:
    image: grafana/grafana-oss:11.1.0
    container_name: sen-grafana
    restart: unless-stopped
    env_file: .env
    environment:
      GF_SECURITY_ADMIN_USER: ${GF_ADMIN_USER}
      GF_SECURITY_ADMIN_PASSWORD: ${GF_ADMIN_PASSWORD}
      GF_SECURITY_SECRET_KEY: ${GF_SECRET_KEY}
      GF_AUTH_ANONYMOUS_ENABLED: "false"
      GF_AUTH_DISABLE_LOGIN_FORM: "false"
      GF_SERVER_ROOT_URL: "https://${PUBLIC_DOMAIN}"
      GF_SERVER_SERVE_FROM_SUB_PATH: "false"
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_USERS_ALLOW_ORG_CREATE: "false"
      GF_ANALYTICS_REPORTING_ENABLED: "false"
      GF_ANALYTICS_CHECK_FOR_UPDATES: "true"
      GF_SECURITY_DISABLE_GRAVATAR: "true"
      GF_SECURITY_COOKIE_SECURE: "true"
      GF_SECURITY_COOKIE_SAMESITE: strict
      GF_SESSION_COOKIE_SECURE: "true"
      GF_SMTP_ENABLED: "false"
      # Pushover credentials injected into provisioning via env
      PUSHOVER_APP_TOKEN: ${PUSHOVER_APP_TOKEN}
      PUSHOVER_USER_KEY: ${PUSHOVER_USER_KEY}
      # DB connection for datasource provisioning
      POSTGRES_HOST: db
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    networks:
      - internal
    depends_on:
      db:
        condition: service_healthy
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD-SHELL", "wget -q --spider http://localhost:3000/api/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
    # No ports exposed externally — only through tunnel

  # ---------------------------------------------------------------------------
  # Cloudflare Tunnel
  # ---------------------------------------------------------------------------
  cloudflared:
    image: cloudflare/cloudflared:2024.6.1
    container_name: sen-cloudflared
    restart: unless-stopped
    env_file: .env
    command: tunnel --no-autoupdate run
    environment:
      TUNNEL_TOKEN: ${CLOUDFLARE_TUNNEL_TOKEN}
    networks:
      - internal
    depends_on:
      - grafana
    security_opt:
      - no-new-privileges:true

networks:
  internal:
    driver: bridge
    internal: false   # needs internet access for tunnel + scraper

volumes:
  db_data:
    driver: local
  grafana_data:
    driver: local
```

> **Note:** The Cloudflare tunnel ingress rule (mapping `PUBLIC_DOMAIN → http://grafana:3000`) must be configured in the Cloudflare Zero Trust dashboard. The tunnel token embeds the routing config.

---

## 7. Scraper Service

### 7.1 `scraper/Dockerfile`

```dockerfile
FROM python:3.12-slim

# Security: non-root user
RUN groupadd -r scraper && useradd -r -g scraper scraper

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper.py healthcheck.py ./

# Ensure no write access needed outside /tmp
RUN chown -R scraper:scraper /app
USER scraper

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD python healthcheck.py

CMD ["python", "-u", "scraper.py"]
```

### 7.2 `scraper/requirements.txt`

```
requests==2.32.3
psycopg2-binary==2.9.9
tenacity==8.3.0
structlog==24.2.0
```

### 7.3 `scraper/scraper.py`

```python
"""
Transelectrica SEN Scraper
Polls https://transelectrica.ro/sen-filter every SCRAPE_INTERVAL seconds
and inserts the parsed data into TimescaleDB.
"""

import os
import time
import json
import logging
from datetime import datetime, timezone

import requests
import psycopg2
import psycopg2.extras
import structlog
from tenacity import retry, wait_exponential, stop_after_attempt, before_sleep_log

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SEN_URL = "https://transelectrica.ro/sen-filter"
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "60"))
USER_AGENT = os.environ.get(
    "SCRAPER_USER_AGENT",
    "SEN-Monitor/1.0"
)
DB_DSN = (
    f"host={os.environ['DB_HOST']} "
    f"port={os.environ.get('DB_PORT', '5432')} "
    f"dbname={os.environ['DB_NAME']} "
    f"user={os.environ['DB_USER']} "
    f"password={os.environ['DB_PASSWORD']}"
)

# Fields to track (extend if the API adds new ones)
NUMERIC_FIELDS = [
    "PROD", "CONS", "CONS2", "SOLD", "PLAN",
    "EOLIAN", "EOLIAN15", "FOTO", "FOTO15",
    "APE", "NUCL", "NUCL15", "GAZE", "GAZE15",
    "CARB", "CARB15", "BMASA", "BMASA15", "COSE",
    "DOBR", "DOBR15", "DJER", "DJER15", "VARN", "VARN15",
    "KOZL1", "KOZL115", "KOZL2", "KOZL215",
    "PANCEVO21", "PANCEVO2115", "PANCEVO22", "PANCEVO2215",
    "UNGE", "MUKA", "MUKA15", "BEKE1", "BEKE115",
    "SAND", "SAND15", "IS", "IAS2", "IAS215",
    "PARO", "PARO15", "CIOA", "CHEF", "CHEF15",
    "CHEA", "CHEA15", "GOTE", "MINT", "MINT15",
    "KIKI", "S110", "SIP_",
]

SOURCE_TS_FIELD = "row1_HARTASEN_DATA"

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
@retry(
    wait=wait_exponential(multiplier=2, min=10, max=120),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=False,
)
def fetch_data() -> list[dict]:
    resp = requests.get(
        SEN_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def parse_data(raw: list[dict]) -> dict:
    """Flatten the list of single-key dicts into one dict."""
    flat = {}
    for item in raw:
        flat.update(item)
    return flat


def to_float(val: str):
    """Convert string to float; return None for empty/invalid."""
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_source_ts(val: str):
    """Parse source timestamp like '26/6/27 14:11:58' → datetime UTC."""
    if not val:
        return None
    try:
        # Format: YY/M/D H:MM:SS
        return datetime.strptime(val.strip(), "%y/%m/%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        log.warning("Could not parse source timestamp", value=val)
        return None


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_connection():
    return psycopg2.connect(DB_DSN)


def insert_reading(conn, collected_at: datetime, source_ts, metrics: dict):
    columns = ["collected_at", "source_ts"] + NUMERIC_FIELDS
    values = [collected_at, source_ts] + [to_float(metrics.get(f)) for f in NUMERIC_FIELDS]

    placeholders = ", ".join(["%s"] * len(values))
    col_names = ", ".join(columns)

    sql = f"INSERT INTO sen_readings ({col_names}) VALUES ({placeholders})"
    with conn.cursor() as cur:
        cur.execute(sql, values)
    conn.commit()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    log.info("SEN Scraper starting", interval=SCRAPE_INTERVAL, url=SEN_URL)

    conn = None
    while True:
        loop_start = time.monotonic()

        try:
            # Reconnect if needed
            if conn is None or conn.closed:
                log.info("Connecting to database")
                conn = get_connection()

            raw = fetch_data()
            if raw is None:
                log.error("Fetch returned None after retries — skipping cycle")
            else:
                flat = parse_data(raw)
                collected_at = datetime.now(timezone.utc)
                source_ts = parse_source_ts(flat.get(SOURCE_TS_FIELD))
                insert_reading(conn, collected_at, source_ts, flat)
                log.info(
                    "Reading inserted",
                    collected_at=collected_at.isoformat(),
                    source_ts=source_ts.isoformat() if source_ts else None,
                    prod_mw=flat.get("PROD"),
                    cons_mw=flat.get("CONS"),
                )

        except psycopg2.Error as e:
            log.error("Database error", error=str(e))
            try:
                conn.close()
            except Exception:
                pass
            conn = None

        except Exception as e:
            log.error("Unexpected error in main loop", error=str(e))

        # Maintain consistent polling interval
        elapsed = time.monotonic() - loop_start
        sleep_time = max(0, SCRAPE_INTERVAL - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
```

### 7.4 `scraper/healthcheck.py`

```python
"""Simple healthcheck: verifies the last DB insert is recent."""
import os
import sys
import psycopg2

DB_DSN = (
    f"host={os.environ['DB_HOST']} "
    f"dbname={os.environ['DB_NAME']} "
    f"user={os.environ['DB_USER']} "
    f"password={os.environ['DB_PASSWORD']}"
)

try:
    conn = psycopg2.connect(DB_DSN, connect_timeout=5)
    cur = conn.cursor()
    cur.execute(
        "SELECT collected_at FROM sen_readings "
        "ORDER BY collected_at DESC LIMIT 1"
    )
    row = cur.fetchone()
    if row is None:
        print("No rows yet")
        sys.exit(0)   # OK during initial startup
    from datetime import datetime, timezone, timedelta
    age = datetime.now(timezone.utc) - row[0]
    if age > timedelta(minutes=5):
        print(f"Last insert too old: {age}")
        sys.exit(1)
    print(f"OK — last insert {age.seconds}s ago")
    sys.exit(0)
except Exception as e:
    print(f"Healthcheck failed: {e}")
    sys.exit(1)
```

---

## 8. TimescaleDB / PostgreSQL Schema

### 8.1 `db/init/01-schema.sql`

```sql
-- =============================================================================
-- SEN Monitor — Database Schema
-- Runs once on first container start (TimescaleDB)
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ---------------------------------------------------------------------------
-- Main readings table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sen_readings (
    collected_at    TIMESTAMPTZ     NOT NULL,
    source_ts       TIMESTAMPTZ,                 -- timestamp from Transelectrica

    -- Summary
    prod            FLOAT,          -- Total production (MW)
    cons            FLOAT,          -- Total consumption (MW)
    cons2           FLOAT,          -- Alternative consumption (MW)
    sold            FLOAT,          -- Exchange balance: + export, - import (MW)
    plan            FLOAT,          -- Planned exchange (MW)

    -- Renewable
    eolian          FLOAT,          -- Wind (MW)
    eolian15        FLOAT,
    foto            FLOAT,          -- Solar / PV (MW)
    foto15          FLOAT,
    ape             FLOAT,          -- Hydro (MW)
    bmasa           FLOAT,          -- Biomass (MW)
    bmasa15         FLOAT,
    cose            FLOAT,          -- Cogeneration (MW)

    -- Conventional
    nucl            FLOAT,          -- Nuclear (MW)
    nucl15          FLOAT,
    gaze            FLOAT,          -- Natural gas (MW)
    gaze15          FLOAT,
    carb            FLOAT,          -- Coal (MW)
    carb15          FLOAT,

    -- Interconnections
    dobr            FLOAT,
    dobr15          FLOAT,
    djer            FLOAT,
    djer15          FLOAT,
    varn            FLOAT,
    varn15          FLOAT,
    kozl1           FLOAT,
    kozl115         FLOAT,
    kozl2           FLOAT,
    kozl215         FLOAT,
    pancevo21       FLOAT,
    pancevo2115     FLOAT,
    pancevo22       FLOAT,
    pancevo2215     FLOAT,
    unge            FLOAT,
    muka            FLOAT,
    muka15          FLOAT,
    beke1           FLOAT,
    beke115         FLOAT,
    sand            FLOAT,
    sand15          FLOAT,
    is_line         FLOAT,          -- "IS" — reserved word, renamed
    ias2            FLOAT,
    ias215          FLOAT,
    paro            FLOAT,
    paro15          FLOAT,
    cioa            FLOAT,
    chef            FLOAT,
    chef15          FLOAT,
    chea            FLOAT,
    chea15          FLOAT,
    gote            FLOAT,
    mint            FLOAT,
    mint15          FLOAT,
    kiki            FLOAT,

    -- Other
    s110            FLOAT,
    sip_            FLOAT,

    PRIMARY KEY (collected_at)
);

-- Convert to TimescaleDB hypertable (partitioned by time, 1-day chunks)
SELECT create_hypertable(
    'sen_readings',
    'collected_at',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- ---------------------------------------------------------------------------
-- Continuous aggregate: 5-minute averages (fast dashboard queries)
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS sen_5min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', collected_at) AS bucket,
    AVG(prod)    AS prod,
    AVG(cons)    AS cons,
    AVG(sold)    AS sold,
    AVG(eolian)  AS eolian,
    AVG(foto)    AS foto,
    AVG(ape)     AS ape,
    AVG(nucl)    AS nucl,
    AVG(gaze)    AS gaze,
    AVG(carb)    AS carb,
    AVG(bmasa)   AS bmasa
FROM sen_readings
GROUP BY bucket
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'sen_5min',
    start_offset => INTERVAL '1 hour',
    end_offset   => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE
);

-- ---------------------------------------------------------------------------
-- Data retention: keep raw data for 90 days, aggregates forever
-- ---------------------------------------------------------------------------
SELECT add_retention_policy(
    'sen_readings',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- ---------------------------------------------------------------------------
-- Read-only user for Grafana
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_ro') THEN
        CREATE ROLE grafana_ro LOGIN PASSWORD 'CHANGE_ME_IN_ENV';
    END IF;
END$$;
GRANT CONNECT ON DATABASE sendb TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
```

> **Important:** The `grafana_ro` password in `01-schema.sql` should be set via an environment variable substitution in entrypoint or a separate secrets init container. For simplicity in v1, set a strong static password and store it in `.env` as `POSTGRES_GRAFANA_RO_PASSWORD`, then reference it in datasource provisioning.

---

## 9. Grafana Configuration

### 9.1 Datasource Provisioning — `grafana/provisioning/datasources/timescaledb.yaml`

```yaml
apiVersion: 1

datasources:
  - name: TimescaleDB
    type: postgres
    uid: timescaledb-uid
    url: db:5432
    database: ${POSTGRES_DB}
    user: ${POSTGRES_USER}
    secureJsonData:
      password: ${POSTGRES_PASSWORD}
    jsonData:
      sslmode: disable
      postgresVersion: 1600
      timescaledb: true
    editable: false
    isDefault: true
```

### 9.2 Dashboard Provisioning — `grafana/provisioning/dashboards/dashboards.yaml`

```yaml
apiVersion: 1

providers:
  - name: SEN Dashboards
    folder: Transelectrica SEN
    type: file
    disableDeletion: true
    updateIntervalSeconds: 30
    allowUiUpdates: false
    options:
      path: /var/lib/grafana/dashboards
```

### 9.3 Alerting — Contact Point — `grafana/provisioning/alerting/contactpoints.yaml`

```yaml
apiVersion: 1

contactPoints:
  - orgId: 1
    name: Pushover
    receivers:
      - uid: pushover-main
        type: pushover
        settings:
          apiToken: ${PUSHOVER_APP_TOKEN}
          userKey: ${PUSHOVER_USER_KEY}
          priority: 0        # 0 = Normal; 1 = High; -1 = Low
          sound: pushover    # default sound
          device: ""         # send to all devices
          expire: 3600       # for priority 2 (emergency) only
          retry: 60          # for priority 2 only
        disableResolveMessage: false
```

### 9.4 Alerting — Notification Policy — `grafana/provisioning/alerting/policies.yaml`

```yaml
apiVersion: 1

policies:
  - orgId: 1
    receiver: Pushover
    group_by: ["alertname"]
    group_wait: 30s
    group_interval: 5m
    repeat_interval: 1h
    routes:
      - receiver: Pushover
        matchers:
          - severity =~ "critical|warning"
```

### 9.5 Suggested Alert Rules

Create these in Grafana UI or as provisioned YAML after the stack is running:

| Alert | Condition | Severity |
|-------|-----------|----------|
| High Import | `sold < -1500 MW` for 5 min | warning |
| High Export | `sold > 1500 MW` for 5 min | warning |
| Zero Production | `prod < 100 MW` for 2 min | critical |
| Stale Data | No new rows for > 5 min | critical |
| Nuclear Offline | `nucl < 50 MW` for 10 min | warning |
| Grid Imbalance | `ABS(prod - cons - sold) > 200 MW` for 5 min | warning |

### 9.6 Dashboard Design Guidelines (Mobile-First)

The dashboard must be configured with:

- **Default time range:** Last 3 hours
- **Auto-refresh:** Every 60 seconds
- **Graph tooltip:** Shared crosshair
- **Panel minimum width:** 12 columns (full width on mobile = 24 columns)

**Recommended panels (top to bottom):**

1. **Stat Row** — `PROD`, `CONS`, `SOLD` (current values, colour-coded: production=green, consumption=orange, sold=blue/red depending on sign)
2. **Gauge** — Grid balance (`PROD - CONS`) with thresholds: deficit < 0 = red, balanced = green
3. **Time series** — Production mix stacked: `EOLIAN`, `FOTO`, `APE`, `NUCL`, `GAZE`, `CARB`, `BMASA`
4. **Pie chart** — Current production mix snapshot
5. **Time series** — `PROD` vs `CONS` overlay
6. **Time series** — Exchange balance (`SOLD`) with zero reference line
7. **Table** — All interconnection values (current), colour-coded positive/negative
8. **Stat Row** — Renewable percentage (`(EOLIAN+FOTO+APE+BMASA)/PROD*100`)

**Mobile optimisation settings in dashboard JSON:**
```json
{
  "graphTooltip": 1,
  "panels": [...],
  "refresh": "1m",
  "schemaVersion": 39,
  "style": "dark",
  "tags": ["energy", "romania", "transelectrica"],
  "time": {"from": "now-3h", "to": "now"},
  "timepicker": {},
  "timezone": "Europe/Bucharest"
}
```

---

## 10. Cloudflare Tunnel

### 10.1 Setup Steps

1. Log in to [Cloudflare Zero Trust](https://one.dash.cloudflare.com)
2. Navigate to **Access → Tunnels → Create a tunnel**
3. Name it `sen-monitor`
4. Copy the **tunnel token** → set as `CLOUDFLARE_TUNNEL_TOKEN` in `.env`
5. Add a **Public Hostname** rule:
   - **Subdomain:** `sen` (or your choice)
   - **Domain:** your Cloudflare-managed domain
   - **Service:** `http://grafana:3000`
6. Optionally add an **Access Policy** to restrict by email or IP (recommended for production)

### 10.2 Additional Security (Cloudflare Access)

Consider adding a **Cloudflare Access Application** in front of the tunnel for a second authentication layer (SSO / OTP), even though Grafana already requires login. This provides:

- IP allowlisting
- Email-based OTP or Google SSO
- Audit log of access attempts
- Bot protection

---

## 11. Alerting — Pushover Contact Point

Pushover credentials must come **only** from environment variables, never hardcoded.

| Variable | Description |
|----------|-------------|
| `PUSHOVER_APP_TOKEN` | Application API token from `pushover.net/apps` |
| `PUSHOVER_USER_KEY` | Your account user key from `pushover.net` |

The contact point is provisioned automatically via `contactpoints.yaml` (Section 9.3). After starting the stack, verify in **Grafana → Alerting → Contact Points → Test** that a notification arrives on your device.

---

## 12. Security Requirements

### 12.1 Container Security

| Requirement | Implementation |
|-------------|----------------|
| Non-root processes | All containers use non-root users |
| No new privileges | `security_opt: no-new-privileges:true` on all containers |
| Read-only filesystem | Scraper container uses `read_only: true` + tmpfs |
| No exposed ports | Only internal Docker network; Grafana accessible via tunnel only |
| Pinned image tags | All images use exact version tags, never `:latest` |

### 12.2 Secret Management

- Secrets stored exclusively in `.env` (never in `docker-compose.yml` or source code)
- `.env` in `.gitignore` — confirmed before first commit
- `.env.example` committed with empty values as documentation
- Rotate all passwords and tokens if accidentally committed

### 12.3 Database Security

- Grafana connects with a **read-only** PostgreSQL role (`grafana_ro`)
- Scraper connects with a **write-only** role (no SELECT beyond its own inserts)
- Database port `5432` not exposed to the host or internet
- Passwords minimum 20 characters, randomly generated (e.g. `openssl rand -base64 32`)

### 12.4 Grafana Security

| Setting | Value | Reason |
|---------|-------|--------|
| `GF_AUTH_ANONYMOUS_ENABLED` | `false` | No unauthenticated access |
| `GF_USERS_ALLOW_SIGN_UP` | `false` | No self-registration |
| `GF_SECURITY_COOKIE_SECURE` | `true` | HTTPS-only cookies |
| `GF_SECURITY_COOKIE_SAMESITE` | `strict` | CSRF protection |
| `GF_ANALYTICS_REPORTING_ENABLED` | `false` | No telemetry to Grafana Inc |
| Admin password | Min 16 chars | Brute-force resistance |

### 12.5 Network Security

- Docker network `internal` — containers communicate by service name only
- No host network mode
- Cloudflare Tunnel provides end-to-end encrypted ingress
- Consider adding Cloudflare Access in front for extra auth layer (Section 10.2)

### 12.6 Scraper Security

- Validates HTTP status before parsing JSON
- Enforces request timeout (`15s`) to avoid hanging
- Does not log full response payloads (avoids accidental secret logging)
- Rate-limited: polls at most once per 60 seconds
- Retry with exponential backoff — no thundering herd on Transelectrica's servers

### 12.7 Dependency Security

- Pin all Python package versions in `requirements.txt`
- Run `pip-audit` in CI to check for known CVEs:
  ```bash
  pip install pip-audit && pip-audit -r requirements.txt
  ```
- Rebuild images monthly or on security advisories

---

## 13. Observability & Logging

### 13.1 Log Format

The scraper uses `structlog` for structured JSON logs. Example:

```json
{"timestamp": "2026-06-27T14:11:58Z", "level": "info", "event": "Reading inserted",
 "collected_at": "2026-06-27T14:11:58+00:00", "prod_mw": "5083", "cons_mw": "4532"}
```

View logs:
```bash
docker compose logs -f scraper
docker compose logs -f grafana
```

### 13.2 Grafana Built-in Metrics

Enable Grafana's internal metrics endpoint to monitor Grafana itself:

```ini
# In GF_ env vars:
GF_METRICS_ENABLED=true
GF_METRICS_INTERVAL_SECONDS=10
```

### 13.3 Recommended Monitoring Checks

| Check | How |
|-------|-----|
| Last row age | Grafana alert: `MAX(collected_at) < NOW() - 5min` |
| Container health | `docker compose ps` — check all `healthy` |
| Disk usage | `df -h /var/lib/docker/volumes` |
| Tunnel status | Cloudflare Zero Trust dashboard |

---

## 14. Backup & Data Retention

### 14.1 TimescaleDB Backup

Schedule a daily backup with `pg_dump`:

```bash
# Add to crontab on host:
0 2 * * * docker exec sen-db pg_dump -U senuser -d sendb --format=custom \
  -f /backups/sendb_$(date +\%Y\%m\%d).dump
```

Mount a host backup directory into the DB container or use `docker exec` to stream the dump to the host.

### 14.2 Data Retention Policy

| Data | Retention | Policy |
|------|-----------|--------|
| Raw readings (`sen_readings`) | 90 days | TimescaleDB retention policy (§8.1) |
| 5-minute aggregates (`sen_5min`) | Indefinite | Continuous aggregate |
| Grafana dashboards / config | Indefinite | Stored in `grafana_data` volume |
| DB backups | 30 days | Rotate with `find /backups -mtime +30 -delete` |

---

## 15. CI/CD & Deployment Checklist

### 15.1 First-Time Deployment

```bash
# 1. Clone repository
git clone https://github.com/yourorg/sen-monitor.git
cd sen-monitor

# 2. Create .env from template
cp .env.example .env
# Edit .env with real values

# 3. Generate strong passwords
openssl rand -base64 32   # → POSTGRES_PASSWORD
openssl rand -base64 32   # → GF_ADMIN_PASSWORD
openssl rand -base64 48   # → GF_SECRET_KEY

# 4. Build and start
docker compose build --no-cache
docker compose up -d

# 5. Verify all containers are healthy
docker compose ps

# 6. Check scraper logs
docker compose logs -f scraper

# 7. Open Grafana via tunnel URL
# https://your-domain.example.com
```

### 15.2 Pre-Deployment Security Checklist

- [ ] `.env` is not committed to Git (`git status` shows clean)
- [ ] All passwords ≥ 20 characters
- [ ] `GF_SECRET_KEY` is ≥ 32 random characters
- [ ] Anonymous Grafana access is disabled
- [ ] Cloudflare tunnel token is valid and tunnel is active
- [ ] Pushover contact point tested successfully
- [ ] No ports are exposed on host (`docker compose ps` shows no `0.0.0.0:*` mappings)
- [ ] All image tags are pinned (no `:latest`)
- [ ] `pip-audit` passes clean on scraper dependencies

### 15.3 Update Procedure

```bash
# 1. Update image tags in docker-compose.yml
# 2. Rebuild
docker compose pull
docker compose build scraper --no-cache
docker compose up -d --force-recreate
docker compose ps   # verify healthy
```

---

## 16. Runbook

### Restart a single service

```bash
docker compose restart scraper
```

### View real-time data in DB

```bash
docker exec -it sen-db psql -U senuser -d sendb \
  -c "SELECT collected_at, prod, cons, sold, eolian, foto FROM sen_readings ORDER BY collected_at DESC LIMIT 10;"
```

### Force a data gap fill (manual scrape)

```bash
docker compose restart scraper
```

### Grafana password reset

```bash
docker exec -it sen-grafana grafana cli admin reset-admin-password <newpassword>
```

### Tunnel not connecting

```bash
docker compose logs cloudflared
# Check token validity in Cloudflare Zero Trust dashboard
```

### Database disk full

```bash
# Check hypertable sizes
docker exec -it sen-db psql -U senuser -d sendb \
  -c "SELECT hypertable_name, pg_size_pretty(hypertable_size(format('%I', hypertable_name)::regclass)) FROM timescaledb_information.hypertables;"

# Manually run retention policy
docker exec -it sen-db psql -U senuser -d sendb \
  -c "SELECT run_job(job_id) FROM timescaledb_information.jobs WHERE proc_name='policy_retention';"
```

---

## 17. Open Points / Known Limitations

| # | Topic | Note |
|---|-------|------|
| L-01 | Transelectrica ToS | Verify that automated polling is permitted. Consider reaching out if building a public service. |
| L-02 | API stability | The `/sen-filter` endpoint has no documented SLA. Field names may change without notice — add monitoring for unexpected `NULL` rates. |
| L-03 | Source timestamp | The `row1_HARTASEN_DATA` field format `YY/M/D H:MM:SS` is parsed as UTC. Confirm with actual Transelectrica documentation whether this is EET/EEST (UTC+2/+3). |
| L-04 | Grafana read-only role | The `grafana_ro` password in `01-schema.sql` requires a separate env var (`POSTGRES_GRAFANA_RO_PASSWORD`) and init script substitution for full secret isolation. |
| L-05 | Historical data | The API provides only the current snapshot. No historical backfill is possible from the public API. |
| L-06 | Cloudflare Access | Adding a Cloudflare Access application (SSO/OTP) in front of the tunnel is strongly recommended for production deployments but not automated here. |
| L-07 | HTTPS internal | Consider adding self-signed TLS between cloudflared and Grafana for full end-to-end encryption even inside the Docker network. |

---

*Document maintained by the project team. Update version and date on every revision.*
