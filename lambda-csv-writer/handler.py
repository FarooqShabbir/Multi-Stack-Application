"""
Triggered by SNS whenever the backend inserts a new entry. Reads the
FULL current entries table from RDS and writes a fresh CSV snapshot to
S3. This is intentionally simple (rewrite the whole file each time,
not an append) -- correctness over cleverness for a lab demo.
"""

import csv
import io
import os
import boto3
import psycopg2
import psycopg2.extras

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ["DB_PORT"]
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
BUCKET_NAME = os.environ["BUCKET_NAME"]

s3 = boto3.client("s3")


def lambda_handler(event, context):
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=5,
    )
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

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key="entries-snapshot.csv",
        Body=buffer.getvalue().encode("utf-8"),
        ContentType="text/csv",
    )

    return {"statusCode": 200, "rows_exported": len(rows)}
