"""Utilities to transform RFID Tag Event data into raddec JSON."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

import frappe
from frappe.utils import cstr

TRANSMITTER_TYPE_UNKNOWN = 0
TRANSMITTER_TYPE_EPC96 = 5
TRANSMITTER_TYPE_TID96 = 7
RECEIVER_TYPE_EUI48 = 2


def build_raddec(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
	"""Return a raddec-style payload for the given tag event data."""

	rfid_value = cstr(event.get("rfid")).strip()
	read_time = event.get("read_time")

	if not rfid_value or not read_time:
		return None

	transmitter_id = _normalise_transmitter_id(rfid_value)
	transmitter_type = _guess_transmitter_type(transmitter_id)

	if not transmitter_id:
		return None

	timestamp = int(read_time.timestamp() * 1000)

	receiver_id = _derive_receiver_id(event.get("reader"))
	receiver_antenna = event.get("antenna_port")
	rssi = event.get("rssi")

	rssi_signature = []
	if receiver_id and rssi is not None:
		try:
			rssi_value = float(rssi)
		except (TypeError, ValueError):
			rssi_value = None
		else:
			rssi_signature.append(
				{
					"receiverId": receiver_id,
					"receiverIdType": RECEIVER_TYPE_EUI48,
					"receiverAntenna": receiver_antenna,
					"rssi": round(rssi_value),
					"numberOfDecodings": 1,
				}
			)

	raddec = {
		"transmitterId": transmitter_id,
		"transmitterIdType": transmitter_type,
		"timestamp": timestamp,
	}

	if rssi_signature:
		raddec["rssiSignature"] = rssi_signature

	if receiver_id and receiver_antenna is not None:
		raddec["receivers"] = [
			{
				"receiverId": receiver_id,
				"receiverIdType": RECEIVER_TYPE_EUI48,
				"antenna": receiver_antenna,
			}
		]

	return raddec


def _normalise_transmitter_id(rfid_value: str) -> str:
	clean_hex = "".join(ch for ch in rfid_value if ch.isalnum()).lower()
	return clean_hex


def _guess_transmitter_type(transmitter_id: str) -> int:
	length = len(transmitter_id)
	if length == 24:
		return TRANSMITTER_TYPE_EPC96
	if length == 32:
		return TRANSMITTER_TYPE_TID96
	return TRANSMITTER_TYPE_UNKNOWN


def _derive_receiver_id(reader: Optional[str]) -> Optional[str]:
	if not reader:
		return None

	sanitised = "".join(ch for ch in reader.lower() if ch in "0123456789abcdef")
	if len(sanitised) >= 12:
		return sanitised[:12]

	digest = hashlib.md5(reader.encode("utf-8")).hexdigest()
	return digest[:12]
