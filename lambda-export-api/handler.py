"""
Invoked directly by API Gateway (HTTP API, AWS_PROXY integration) on
GET /export. Reads entries from RDS and returns them as CSV -- this is
the fully serverless equivalent of a hypothetical GET /api/entries.csv
endpoint on the containerized FastAPI backend. No ECS, no containers,
no EC2 involved in serving this request at all.
"""

import csv
import io
import os
import json
import psycopg2
import psycopg2.extras

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ["DB_PORT"]
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]


def lambda_handler(event, context):
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=5,
        )
    except psycopg2.OperationalError as exc:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": f"database connection failed: {exc}"}),
        }

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, text_data, created_at FROM entries ORDER BY created_at DESC;"
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "text", "created_at"])
    for row in rows:
        writer.writerow([row["id"], row["text_data"], row["created_at"].isoformat()])

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/csv",
            "Content-Disposition": "attachment; filename=entries.csv",
        },
        "body": buffer.getvalue(),
    }
