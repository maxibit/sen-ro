import os
import sys
from datetime import datetime, timedelta, timezone

import psycopg2

DB_DSN = (
    f"host={os.environ['DB_HOST']} "
    f"port={os.environ.get('DB_PORT', '5432')} "
    f"dbname={os.environ['DB_NAME']} "
    f"user={os.environ['DB_USER']} "
    f"password={os.environ['DB_PASSWORD']}"
)

try:
    conn = psycopg2.connect(DB_DSN, connect_timeout=5)
    with conn.cursor() as cursor:
        cursor.execute("SELECT collected_at FROM sen_readings ORDER BY collected_at DESC LIMIT 1")
        row = cursor.fetchone()

    if row is None:
        print("No readings inserted yet")
        sys.exit(1)

    age = datetime.now(timezone.utc) - row[0]
    if age > timedelta(minutes=5):
        print(f"Last reading is too old: {age}")
        sys.exit(1)

    print(f"OK: last reading {int(age.total_seconds())} seconds ago")
    sys.exit(0)
except Exception as error:
    print(f"Healthcheck failed: {error}")
    sys.exit(1)
