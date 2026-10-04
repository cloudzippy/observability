import logging
import os

import psycopg
from flask import Flask, jsonify, request

app = Flask(__name__)
logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL") or psycopg.conninfo.make_conninfo(
    host=os.getenv("DATABASE_HOST", "localhost"),
    port=os.getenv("DATABASE_PORT", "5432"),
    dbname=os.getenv("DATABASE_NAME", "shop"),
    user=os.getenv("DATABASE_USER", "lab"),
    password=os.getenv("DATABASE_PASSWORD", "lab"),
)


def initialize_database():
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS inventory (
                item_id TEXT PRIMARY KEY,
                quantity INTEGER NOT NULL CHECK (quantity >= 0)
            )"""
        )
        connection.execute(
            "INSERT INTO inventory (item_id, quantity) VALUES ('widget', 20) ON CONFLICT (item_id) DO NOTHING"
        )


initialize_database()


@app.get("/health")
def health():
    return jsonify(status="ok", service="inventory")


@app.get("/stock/<item_id>")
def get_stock(item_id):
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute("SELECT quantity FROM inventory WHERE item_id = %s", (item_id,)).fetchone()
    if row is None:
        return jsonify(detail="item not found"), 404
    return jsonify(item_id=item_id, quantity=row[0])


@app.post("/reserve")
def reserve():
    payload = request.get_json(silent=True) or {}
    item_id = payload.get("item_id", "widget")
    quantity = payload.get("quantity", 1)
    if not isinstance(item_id, str) or not item_id or type(quantity) is not int or not 1 <= quantity <= 20:
        return jsonify(detail="item_id must be a non-empty string and quantity must be between 1 and 20"), 422

    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "UPDATE inventory SET quantity = quantity - %s "
            "WHERE item_id = %s AND quantity >= %s RETURNING quantity",
            (quantity, item_id, quantity),
        ).fetchone()
    if row is None:
        logger.warning("inventory reservation rejected", extra={"item_id": item_id})
        return jsonify(detail="item unavailable or insufficient stock"), 409
    logger.info("inventory reserved", extra={"item_id": item_id, "remaining": row[0]})
    return jsonify(item_id=item_id, remaining=row[0])
