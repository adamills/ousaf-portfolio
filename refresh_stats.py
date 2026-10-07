"""
Refreshes the campaign_stats materialized view.
Run this on a schedule (every 1-5 min) rather than on every call insert —
refreshing per-insert doesn't scale under real call volume.

Local (Termux) cron alternative: run manually or via a simple loop/cron job.
On Render: set this up as a Render Cron Job pointing at this script.
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "dbname=ousaf_calls")


def refresh():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY campaign_stats;")
    conn.commit()
    cur.close()
    conn.close()
    print("campaign_stats refreshed")


if __name__ == "__main__":
    refresh()
