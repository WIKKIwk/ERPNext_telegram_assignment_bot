"""Webhook dispatch helpers for RFID raddec events."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict

import frappe
import requests

DEFAULT_TIMEOUT = 10
EVENT_HEADER = "X-RFID-Event"
SIGNATURE_HEADER = "X-RFID-Signature"


def dispatch_raddec_event(raddec: Dict[str, Any], metadata: Dict[str, Any]) -> None:
	"""Enqueue asynchronous webhook delivery for the given raddec payload."""

	if not raddec:
		return

	frappe.enqueue(
		"rfid.rfid.services.webhook._dispatch_async",
		raddec=raddec,
		metadata=metadata,
		queue="short",
		job_description=f"Dispatch RFID raddec {metadata.get('docname', '')}",
	)


def _dispatch_async(raddec: Dict[str, Any], metadata: Dict[str, Any]) -> None:
	webhooks = frappe.get_all(
		"RFID Webhook",
		filters={"enabled": 1},
		fields=["name", "webhook_url", "secret", "timeout"],
	)

	if not webhooks:
		return

	payload = {
		"event": "rfid.raddec",
		"data": raddec,
		"meta": metadata,
	}

	for hook in webhooks:
		url = hook.get("webhook_url")
		if not url:
			continue

		headers = {
			"Content-Type": "application/json",
			EVENT_HEADER: "rfid.raddec",
		}

		secret = hook.get("secret")
		encoded_payload = json.dumps(payload, default=str).encode("utf-8")

		if secret:
			signature = hmac.new(secret.encode("utf-8"), encoded_payload, hashlib.sha256).hexdigest()
			headers[SIGNATURE_HEADER] = signature

		timeout = hook.get("timeout") or DEFAULT_TIMEOUT

		try:
			requests.post(url, data=encoded_payload, headers=headers, timeout=timeout)
		except Exception:
			title = f"RFID Webhook failed: {hook.get('name')}"
			frappe.log_error(frappe.get_traceback(), title)
