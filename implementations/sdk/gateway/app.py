import logging
import os

from flask import Flask, jsonify, request
from opentelemetry.trace import Status, StatusCode

from telemetry import configure_telemetry, traced_post

app = Flask(__name__)
logger = logging.getLogger(__name__)
tracer, meter = configure_telemetry(app, "checkout-gateway")
checkout_requests = meter.create_counter("checkout_requests")
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
        checkout_requests.add(1, {"outcome": "rejected"})
        return jsonify(detail="item_id must be a non-empty string and quantity must be between 1 and 20"), 422

    logger.info("checkout requested", extra={"item_id": item_id, "quantity": quantity})
    with tracer.start_as_current_span("checkout.place_order") as span:
        try:
            response = traced_post(
                tracer,
                f"{ORDERS_URL}/orders",
                {"item_id": item_id, "quantity": quantity},
            )
        except Exception:
            checkout_requests.add(1, {"outcome": "unavailable"})
            span.set_status(Status(StatusCode.ERROR))
            logger.exception("orders service is unavailable")
            return jsonify(detail="orders service unavailable"), 502

        if response.status_code >= 400:
            checkout_requests.add(1, {"outcome": "rejected"})
            return jsonify(detail=response.json().get("detail", "order failed")), response.status_code

        checkout_requests.add(1, {"outcome": "succeeded"})
        result = response.json()
        span.set_attribute("order.id", result["order_id"])
        logger.info("checkout completed", extra={"order_id": result["order_id"]})
        return jsonify(result), 201
