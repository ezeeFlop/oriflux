"""Best-effort ops alerting: log + optional POST to OPS_WEBHOOK_URL.

Same convention as the backup sidecars in deploy/docker-stack.yml — one
webhook (Slack/ntfy/custom), payload {"text": "..."}; failures to deliver
the alert are logged and swallowed (alerting must never take a worker down).
"""

import logging

import requests

from oriflux.config import Settings

logger = logging.getLogger(__name__)


def ops_alert(settings: Settings, message: str) -> None:
    logger.error("[ops-alert] %s", message)
    if not settings.ops_webhook_url:
        return
    try:
        requests.post(settings.ops_webhook_url, json={"text": f"[oriflux] {message}"}, timeout=5)
    except Exception:
        logger.exception("failed to deliver ops alert")
