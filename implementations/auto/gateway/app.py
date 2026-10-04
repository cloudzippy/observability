import logging
import os

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
logger = logging.getLogger(__name__)
ORDERS_URL = os.getenv("ORDERS_URL", "http://localhost:8001")


@app.get("/health")
def health():
    return jsonify(status="ok", service="checkout-gateway")


@app.post("/checkout")
def checkout():
    payload = request.get_json(silent=True) or {}
    item_id = payload.get("item_id", "widget")
    quantity = payload.get("quantity", 1)
    if not isinstance(item_id, str) or not item_id or type(quantity) is not int or not 1 <= quantity <= 20:
        return jsonify(detail="item_id must be a non-empty string and quantity must be between 1 and 20"), 422

    logger.info("checkout requested", extra={"item_id": item_id, "quantity": quantity})
    try:
        response = requests.post(
            f"{ORDERS_URL}/orders",
            json={"item_id": item_id, "quantity": quantity},
            timeout=3,
        )
    except requests.RequestException:
        logger.exception("orders service is unavailable")
        return jsonify(detail="orders service unavailable"), 502

    if response.status_code >= 400:
        return jsonify(detail=response.json().get("detail", "order failed")), response.status_code

    result = response.json()
    logger.info("checkout completed", extra={"order_id": result["order_id"]})
    return jsonify(result), 201
