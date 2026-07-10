"""Alert delivery: Slack webhook + email via Resend (ClipHaven pattern).

Each channel gets 3 attempts with backoff; a channel that still fails is
logged (and never takes the evaluator down). Webhook URLs are re-validated
against SSRF at send time (defense in depth — they were validated at rule
creation too); `allow_private_webhooks` exists for dev/test sinks only.
"""

import logging
import time
from collections.abc import Callable

import requests

from oriflux.config import Settings
from oriflux.db.models import AlertCondition, AlertRule
from oriflux.security.ssrf import validate_public_url

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


def _message(rule: AlertRule, kind: str, value: float) -> str:
    symbol = ">" if rule.condition == AlertCondition.gt else "<"
    state = "ALERT" if kind == "firing" else "RESOLVED"
    return (
        f"[oriflux] {state} — {rule.name}: {rule.metric} = {value} "
        f"(threshold {symbol} {rule.threshold}, {rule.window_minutes} min window)"
    )


class AlertNotifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _with_retry(self, send: Callable[[], None], channel: str, rule: AlertRule) -> None:
        for attempt in range(3):
            try:
                send()
                return
            except Exception:  # noqa: BLE001
                if attempt == 2:
                    logger.exception(
                        "%s delivery failed after 3 attempts (rule %s)", channel, rule.id
                    )
                else:
                    time.sleep(2**attempt)

    def notify(self, rule: AlertRule, *, kind: str, value: float) -> None:
        text = _message(rule, kind, value)
        if rule.slack_webhook_url:
            url = rule.slack_webhook_url
            if not self._settings.allow_private_webhooks:
                validate_public_url(url)
            self._with_retry(
                lambda: requests.post(url, json={"text": text}, timeout=5).raise_for_status(),
                "slack",
                rule,
            )
        if rule.email and self._settings.resend_api_key:
            self._with_retry(lambda: self._send_email(rule, text), "email", rule)

    def _send_email(self, rule: AlertRule, text: str) -> None:
        response = requests.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {self._settings.resend_api_key}"},
            json={
                "from": self._settings.alert_email_from,
                "to": [rule.email],
                "subject": text.split("—")[0].strip(),
                "text": text,
            },
            timeout=10,
        )
        response.raise_for_status()
