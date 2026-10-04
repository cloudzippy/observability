import logging
import os
from uuid import uuid4

import psycopg
import requests
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
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8002")


def initialize_database():
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )"""
        )


initialize_database()


@app.get("/health")
def health():
    return jsonify(status="ok", service="orders")


@app.post("/orders")
def create_order():
    payload = request.get_json(silent=True) or {}
    item_id = payload.get("item_id", "widget")
    quantity = payload.get("quantity", 1)
    if not isinstance(item_id, str) or not item_id or type(quantity) is not int or not 1 <= quantity <= 20:
        return jsonify(detail="item_id must be a non-empty string and quantity must be between 1 and 20"), 422

    try:
        response = requests.post(
            f"{INVENTORY_URL}/reserve",
            json={"item_id": item_id, "quantity": quantity},
            timeout=3,
        )
    except requests.RequestException:
        logger.exception("inventory service is unavailable")
        return jsonify(detail="inventory service unavailable"), 502

    if response.status_code >= 400:
        return jsonify(detail=response.json().get("detail", "reservation failed")), response.status_code

    order_id = str(uuid4())
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO orders (order_id, item_id, quantity) VALUES (%s, %s, %s)",
            (order_id, item_id, quantity),
        )

    logger.info("order created", extra={"order_id": order_id, "item_id": item_id})
    return jsonify(order_id=order_id, item_id=item_id, quantity=quantity, status="created"), 201


@app.get("/orders/<order_id>")
def get_order(order_id):
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT order_id, item_id, quantity, created_at FROM orders WHERE order_id = %s",
            (order_id,),
        ).fetchone()
    if row is None:
        return jsonify(detail="order not found"), 404
    return jsonify(order_id=row[0], item_id=row[1], quantity=row[2], created_at=row[3].isoformat())
