# -*- coding: utf-8 -*-
"""Lightweight helpers for interacting with the Telegram Bot HTTP API."""

from __future__ import annotations

import requests

import frappe
from frappe import _
from frappe.utils import cstr


API_URL_TEMPLATE = "https://api.telegram.org/bot{token}/{method}"  # cSpell:disable-line


def send_message(token: str, chat_id: str | int, text: str) -> None:
	"""Send a plain text message via the Telegram Bot API."""
	_call_telegram_api(
		token,
		"sendMessage",
		http_method="post",
		payload={"chat_id": chat_id, "text": text},
	)


def get_updates(token: str, limit: int = 100):
	"""Return the latest updates for the bot."""
	return _call_telegram_api(
		token,
		"getUpdates",
		payload={"limit": limit},
	)


def _call_telegram_api(token: str, method: str, http_method: str = "get", payload: dict | None = None):
	url = API_URL_TEMPLATE.format(token=token, method=method)

	try:
		if http_method.lower() == "post":
			response = requests.post(url, data=payload, timeout=15)
		else:
			response = requests.get(url, params=payload, timeout=15)
		response.raise_for_status()
	except requests.RequestException as exc:
		raise frappe.ValidationError(
			_("Telegram API request failed: {0}").format(cstr(exc))
		) from exc

	data = response.json()
	if not data.get("ok"):
		raise frappe.ValidationError(
			_("Telegram API responded with an error: {0}").format(data.get("description", data))
		)

	return data.get("result", [])
