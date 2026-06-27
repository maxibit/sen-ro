import logging
import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import psycopg2
import requests
import structlog
from tenacity import RetryError, before_sleep_log, retry, stop_after_attempt, wait_exponential

SEN_URL = "https://transelectrica.ro/sen-filter"
SOURCE_TS_FIELD = "row1_HARTASEN_DATA"
SOURCE_TIMEZONE = ZoneInfo("Europe/Bucharest")

SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "60"))
USER_AGENT = os.environ.get("SCRAPER_USER_AGENT", "SEN-Monitor/1.0")
DB_DSN = (
    f"host={os.environ['DB_HOST']} "
    f"port={os.environ.get('DB_PORT', '5432')} "
    f"dbname={os.environ['DB_NAME']} "
    f"user={os.environ['DB_USER']} "
    f"password={os.environ['DB_PASSWORD']}"
)

FIELD_MAP = {
    "PROD": "prod",
    "CONS": "cons",
    "CONS15": "cons15",
    "CONS2": "cons2",
    "SOLD": "sold",
    "PLAN": "plan",
    "EOLIAN": "eolian",
    "EOLIAN15": "eolian15",
    "FOTO": "foto",
    "FOTO15": "foto15",
    "APE": "ape",
    "NUCL": "nucl",
    "NUCL15": "nucl15",
    "GAZE": "gaze",
    "GAZE15": "gaze15",
    "CARB": "carb",
    "CARB15": "carb15",
    "BMASA": "bmasa",
    "BMASA15": "bmasa15",
    "COSE": "cose",
    "DOBR": "dobr",
    "DOBR15": "dobr15",
    "DJER": "djer",
    "DJER15": "djer15",
    "VARN": "varn",
    "VARN15": "varn15",
    "KOZL1": "kozl1",
    "KOZL115": "kozl115",
    "KOZL2": "kozl2",
    "KOZL215": "kozl215",
    "PANCEVO21": "pancevo21",
    "PANCEVO2115": "pancevo2115",
    "PANCEVO22": "pancevo22",
    "PANCEVO2215": "pancevo2215",
    "UNGE": "unge",
    "MUKA": "muka",
    "MUKA15": "muka15",
    "BEKE1": "beke1",
    "BEKE115": "beke115",
    "SAND": "sand",
    "SAND15": "sand15",
    "IS": "is_line",
    "IAS2": "ias2",
    "IAS215": "ias215",
    "PARO": "paro",
    "PARO15": "paro15",
    "CIOA": "cioa",
    "CHEF": "chef",
    "CHEF15": "chef15",
    "CHEA": "chea",
    "CHEA15": "chea15",
    "GOTE": "gote",
    "MINT": "mint",
    "MINT15": "mint15",
    "KIKI": "kiki",
    "S110": "s110",
    "SIP_": "sip",
    "KUSJ": "kusj",
    "ISPOZ": "ispoz",
    "VULC": "vulc",
    "PROG": "prog",
    "Prot1TMS": "prot1tms",
}

logging.basicConfig(level=logging.INFO)
retry_logger = logging.getLogger("sen_scraper.retry")
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()


@retry(
    wait=wait_exponential(multiplier=2, min=10, max=120),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(retry_logger, logging.WARNING),
)
def fetch_data() -> list[dict[str, str]]:
    response = requests.get(
        SEN_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Unexpected response payload; expected a JSON list")
    return payload


def flatten_payload(raw: list[dict[str, str]]) -> dict[str, str]:
    flat = {}
    for item in raw:
        if isinstance(item, dict):
            flat.update(item)
    return flat


def to_float(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def parse_source_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        local_dt = datetime.strptime(value.strip(), "%y/%m/%d %H:%M:%S")
        return local_dt.replace(tzinfo=SOURCE_TIMEZONE).astimezone(timezone.utc)
    except ValueError:
        log.warning("source_timestamp_parse_failed", value=value)
        return None


def get_connection():
    return psycopg2.connect(DB_DSN)


def insert_reading(conn, collected_at: datetime, source_ts: datetime | None, flat: dict[str, str]) -> None:
    metric_columns = list(FIELD_MAP.values())
    columns = ["collected_at", "source_ts"] + metric_columns
    values = [collected_at, source_ts] + [to_float(flat.get(api_field)) for api_field in FIELD_MAP]
    placeholders = ", ".join(["%s"] * len(values))
    sql = f"INSERT INTO sen_readings ({', '.join(columns)}) VALUES ({placeholders})"
    with conn.cursor() as cursor:
        cursor.execute(sql, values)
    conn.commit()


def main() -> None:
    log.info("scraper_started", interval_seconds=SCRAPE_INTERVAL, url=SEN_URL)
    conn = None

    while True:
        loop_started = time.monotonic()
        try:
            if conn is None or conn.closed:
                log.info("database_connecting")
                conn = get_connection()

            raw = fetch_data()
            flat = flatten_payload(raw)
            unknown_fields = sorted(set(flat) - set(FIELD_MAP) - {SOURCE_TS_FIELD})
            if unknown_fields:
                log.warning("unknown_source_fields", fields=unknown_fields)

            collected_at = datetime.now(timezone.utc)
            source_ts = parse_source_timestamp(flat.get(SOURCE_TS_FIELD))
            insert_reading(conn, collected_at, source_ts, flat)
            log.info(
                "reading_inserted",
                collected_at=collected_at.isoformat(),
                source_ts=source_ts.isoformat() if source_ts else None,
                prod_mw=flat.get("PROD"),
                cons_mw=flat.get("CONS"),
                sold_mw=flat.get("SOLD"),
            )
        except RetryError as error:
            log.error("fetch_failed_after_retries", error=str(error))
        except psycopg2.Error as error:
            log.error("database_error", error=str(error))
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            conn = None
        except Exception as error:
            log.error("scrape_cycle_failed", error=str(error))

        elapsed = time.monotonic() - loop_started
        time.sleep(max(0, SCRAPE_INTERVAL - elapsed))


if __name__ == "__main__":
    main()
