# Transelectrica SEN Monitor

Self-hosted monitoring for Romania's National Energy System data from Transelectrica.

The stack polls `https://transelectrica.ro/sen-filter` every 60 seconds, stores readings in TimescaleDB, and exposes a Grafana dashboard through Cloudflare Tunnel.

## Services

- `db`: TimescaleDB / PostgreSQL 16
- `scraper`: Python scraper for Transelectrica live data
- `grafana`: Grafana OSS dashboard and alerting
- `cloudflared`: Cloudflare Tunnel connector

Containers intentionally run with their image defaults in v1. This keeps deployment simple. Network exposure is still restricted: there are no host port mappings in `docker-compose.yml`.

## Setup

Prerequisites:

- Docker Engine
- Docker Compose v2
- A Cloudflare-managed domain
- A Cloudflare Tunnel token

Create the local environment file:

```bash
cp .env.example .env
```

Generate secrets:

```bash
openssl rand -base64 32
openssl rand -base64 48
```

Fill these values in `.env`:

- `GF_ADMIN_PASSWORD`
- `GF_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `POSTGRES_SCRAPER_PASSWORD`
- `POSTGRES_GRAFANA_PASSWORD`
- `CLOUDFLARE_TUNNEL_TOKEN`
- `PUBLIC_DOMAIN`
- `PUSHOVER_APP_TOKEN`
- `PUSHOVER_USER_KEY`

Use a tunnel token only, not the full Cloudflare install command. Correct:

```dotenv
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoi...
```

Incorrect:

```dotenv
CLOUDFLARE_TUNNEL_TOKEN=sudo cloudflared service install eyJhIjoi...
```

Start the stack:

```bash
docker compose up -d --build
```

Check service status:

```bash
docker compose ps
docker compose logs -f scraper
```

## Cloudflare Tunnel

Create a tunnel in Cloudflare Zero Trust and add or update the public hostname:

```text
sen.example.com -> http://grafana:3000
```

Set the tunnel token in `.env` as `CLOUDFLARE_TUNNEL_TOKEN`. Grafana is not exposed on a host port; it is reachable only by the `cloudflared` container inside the Docker network.

Use a dedicated tunnel token for this stack. Do not reuse the same token on another server or desktop, because Cloudflare may route requests to a connector that cannot resolve Docker service names such as `grafana`.

## Database Roles

The database init scripts create two application roles:

- `POSTGRES_SCRAPER_USER`: can insert readings and read `collected_at` for healthchecks
- `POSTGRES_GRAFANA_USER`: read-only access for dashboards and alerts

The admin `POSTGRES_USER` is used only for database initialization and maintenance.

## Useful Commands

View the latest readings:

```bash
docker exec -it sen-db sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT collected_at, source_ts, prod, cons, sold FROM sen_readings ORDER BY collected_at DESC LIMIT 10;"'
```

Restart the scraper:

```bash
docker compose restart scraper
```

Reset the Grafana admin password:

```bash
docker exec -it sen-grafana \
  /usr/share/grafana/bin/grafana cli admin reset-admin-password '<new-password>'
```

If Grafana temporarily blocks login after failed attempts, clear the lockout:

```bash
docker run --rm -v sen-monitor_grafana_data:/data python:3.12-slim \
  python -c "import sqlite3; con=sqlite3.connect('/data/grafana.db'); con.execute('delete from login_attempt'); con.commit()"
```

Synchronize database role passwords after changing `.env` on an existing volume:

```bash
docker exec sen-db bash -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER ROLE \"$POSTGRES_SCRAPER_USER\" WITH PASSWORD '\''$POSTGRES_SCRAPER_PASSWORD'\'';"'

docker exec sen-db bash -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER ROLE \"$POSTGRES_GRAFANA_USER\" WITH PASSWORD '\''$POSTGRES_GRAFANA_PASSWORD'\'';"'
```

## Public Dashboard Sharing

The dashboard can be shared without a Grafana user/password through Grafana public dashboards.

Create a public dashboard link:

```bash
set -a
source .env
set +a

docker run --rm --network sen-monitor_internal curlimages/curl:8.8.0 \
  -fsS \
  -u "${GF_ADMIN_USER}:${GF_ADMIN_PASSWORD}" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"isEnabled":true,"annotationsEnabled":false,"timeSelectionEnabled":true}' \
  http://grafana:3000/api/dashboards/uid/sen-overview/public-dashboards
```

The response includes:

- `accessToken`: public URL token
- `uid`: public dashboard UID used for revocation

The public URL format is:

```text
https://${PUBLIC_DOMAIN}/public-dashboards/<accessToken>
```

To revoke a public dashboard link, set `PUBLIC_DASHBOARD_UID` in `.env`, then run:

```bash
scripts/revoke-public-dashboard.sh
```

For temporary sharing, run a detached timer container:

```bash
set -a
source .env
set +a

docker run -d --name sen-public-dashboard-expiry \
  --network sen-monitor_internal \
  --env-file .env \
  curlimages/curl:8.8.0 \
  sh -c 'sleep 86400; curl -fsS -u "$GF_ADMIN_USER:$GF_ADMIN_PASSWORD" -H "Content-Type: application/json" -X PATCH -d "{\"isEnabled\":false}" http://grafana:3000/api/dashboards/uid/sen-overview/public-dashboards/$PUBLIC_DASHBOARD_UID'
```

## Deployment Checklist

Before pushing to GitHub:

- `.env` is not committed
- no tunnel token or real password is present in tracked files
- generated files such as `__pycache__`, logs, and PID files are not committed
- `PUBLIC_DOMAIN` in `.env` matches the Cloudflare public hostname
- the Cloudflare public hostname points to `http://grafana:3000`
- the Cloudflare tunnel token is used only by this deployment

Fresh deployment:

```bash
git clone <repo-url>
cd sen-monitor
cp .env.example .env
# edit .env
docker compose up -d --build
docker compose ps
docker compose logs -f scraper
```

Verify:

```bash
set -a
source .env
set +a

curl -I "https://${PUBLIC_DOMAIN}"
docker exec sen-db sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT collected_at, prod, cons, sold FROM sen_readings ORDER BY collected_at DESC LIMIT 5;"'
```

## Troubleshooting

If Grafana shows `No data`, verify that the read-only database password matches `.env`:

```bash
docker exec sen-db bash -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER ROLE \"$POSTGRES_GRAFANA_USER\" WITH PASSWORD '\''$POSTGRES_GRAFANA_PASSWORD'\'';"'
```

If Cloudflare returns `502`, check:

- `cloudflared` is connected: `docker compose logs cloudflared`
- the public hostname points to `http://grafana:3000`
- the same tunnel token is not running on another machine

If the browser says `Server not found`, check DNS propagation:

```bash
dig +short "$PUBLIC_DOMAIN" @1.1.1.1
dig +short "$PUBLIC_DOMAIN" @8.8.8.8
```

## Notes

- Transelectrica may reject requests without a realistic User-Agent. The default `SCRAPER_USER_AGENT` is set accordingly in `.env.example`.
- `row1_HARTASEN_DATA` is parsed as `Europe/Bucharest` local time and stored as UTC.
- Raw readings are retained for 90 days. The `sen_5min` continuous aggregate is retained indefinitely.
- Transelectrica uses `SOLD > 0` as net import and `SOLD < 0` as net export. Individual interconnection fields are line flows and should not be relabeled as country-level import/export without confirming each line's sign convention.
