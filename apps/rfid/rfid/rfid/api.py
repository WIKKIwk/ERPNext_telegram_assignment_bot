from __future__ import annotations

import json
import itertools
import hashlib
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import frappe
import secrets
from frappe import _
from frappe.utils import get_datetime, get_link_to_form, now_datetime

from rfid.rfid.services import build_raddec, dispatch_raddec_event

@frappe.whitelist()
def create_print_rfid_se(doc):
    doc = json.loads(doc)
    
    serial_no_list = frappe.db.get_list('Serial No',{'purchase_document_no':doc.get('name')}, ['name','item_code','custom_barcode'])
    if serial_no_list:
        created_numbers = []
        for serial_no in serial_no_list:
            created_numbers.append(serial_no.get('name'))
            rfid_doc = frappe.new_doc('RFID Print Queue')
            rfid_doc.item_code = serial_no.get('item_code')
            rfid_doc.qty = 1
            rfid_doc.status = 'Pending'
            rfid_doc.rfid = serial_no.get('custom_barcode')
            rfid_doc.flags.ignore_permissions = 1
            rfid_doc.save()

        form_links = list(map(lambda d: get_link_to_form("Serial No", d), created_numbers))

        # Setting up tranlated title field for all cases
        singular_title = ("Added RFID in Print Queue")
        multiple_title = ("Added RFIDs in Print Queue")

        if len(form_links) == 1:
            frappe.msgprint(("Serial No {0} Added in RFID Print Queue").format(form_links[0]), singular_title)
        elif len(form_links) > 0:
            message = ("The following RFIDs were added: <br><br> {0}").format(
                get_items_html(form_links, 'RFID')
            )
            frappe.msgprint(message, multiple_title)

@frappe.whitelist()
def create_print_rfid_sn(Serial_no_list):
    doc = json.loads(Serial_no_list)
    
    if doc:
        created_numbers = []
        for item in doc:
            rfid_doc = frappe.new_doc('RFID Print Queue')
            created_numbers.append(item.get('name'))
            if 'asset_name' in list(item.keys()):
                rfid_doc.item_code = frappe.db.get_value('Asset',item.get('name'),'item_code')
            else:
                rfid_doc.item_code = item.get('item_code')
            rfid_doc.qty = 1
            rfid_doc.status = 'Pending'
            if 'asset_name' in list(item.keys()):
                rfid_data = frappe.db.get_value('Asset',item.get('name'),'custom_rfid')
            else:
                rfid_data = frappe.db.get_value('Serial No',item.get('name'),'custom_barcode')
            rfid_doc.rfid = rfid_data
            rfid_doc.flags.ignore_permissions = 1
            rfid_doc.save()
        
        form_links = list(map(lambda d: get_link_to_form("Serial No", d), created_numbers))

        # Setting up tranlated title field for all cases
        singular_title = ("Added RFID in Print Queue")
        multiple_title = ("Added RFIDs in Print Queue")

        if len(form_links) == 1:
            if 'asset_name' in list(doc[0].keys()):
                frappe.msgprint(("Asset {0} Added in RFID Print Queue").format(form_links[0]), singular_title)    
            else:
                frappe.msgprint(("Serial No {0} Added in RFID Print Queue").format(form_links[0]), singular_title)
        elif len(form_links) > 0:
            message = ("The following RFIDs were added: <br><br> {0}").format(
                get_items_html(form_links, 'RFID')
            )
            frappe.msgprint(message, multiple_title)

def get_items_html(serial_nos, item_code):
    body = ", ".join(serial_nos)
    return """<details><summary>
        <b>{0}:</b> {1} RFID Numbers <span class="caret"></span>
    </summary>
    <div class="small">{2}</div></details>
    """.format(
        item_code, len(serial_nos), body
    )

def generate_unique_hex(len):
    return secrets.token_hex(len)
    
@frappe.whitelist()
def create_se(**kwargs):
    body = json.loads(frappe.request.data)
    doc = frappe.new_doc('Stock Entry')
    doc.stock_entry_type = "Material Receipt"
    doc.to_warehouse = body.get("to_warehouse")
    for i in body.get("items"):
        doc.append("items",{"item_code": i.get("item_code"),"qty": i.get("qty"),"basic_rate": i.get("basic_rate")})
    doc.save(ignore_permissions=1)
    doc.submit()
    return doc


@frappe.whitelist()
def get_raddec_events(limit: int = 100, since: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return recent raddec payloads stored from RFID tag events."""

    filters: Dict[str, Any] = {}
    if since:
        filters["read_time"] = (">=", get_datetime(since))

    rows = frappe.get_all(
        "RFID Tag Event",
        filters=filters,
        fields=["name", "raddec", "read_time"],
        order_by="read_time desc",
        limit=limit,
    )

    results: List[Dict[str, Any]] = []
    for row in rows:
        raddec_data = row.get("raddec")
        if not raddec_data:
            continue

        try:
            raddec_json = json.loads(raddec_data)
        except json.JSONDecodeError:
            continue

        read_time = row.get("read_time")
        if read_time and "timestamp" not in raddec_json:
            raddec_json["timestamp"] = int(read_time.timestamp() * 1000)

        raddec_json.setdefault("_docname", row.get("name"))
        results.append(raddec_json)

    return results


def _iter_impinj_nodes(payload: Any) -> Iterable[Dict[str, Any]]:
    """Yield potential event dictionaries out of a nested payload structure."""

    if isinstance(payload, list):
        for element in payload:
            yield from _iter_impinj_nodes(element)
        return

    if not isinstance(payload, dict):
        return

    # Common keys containing collections of events.
    for key in (
        "notifications",
        "Notification",
        "events",
        "items",
        "records",
        "tagReport",
        "tagReportData",
        "tag_reads",
        "tags",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            for element in value:
                yield from _iter_impinj_nodes(element)
            return

    for key in ("data", "eventData"):
        value = payload.get(key)
        if isinstance(value, (dict, list)):
            yield from _iter_impinj_nodes(value)
            return

    yield payload


def _extract_epc(data: Dict[str, Any]) -> Optional[str]:
    candidates = [
        data.get("epc"),
        data.get("epcHex"),
        data.get("epcStr"),
        data.get("tag"),
        data.get("id"),
    ]

    epc_data = data.get("epcData") or data.get("epc_data")
    if isinstance(epc_data, dict):
        candidates.extend([
            epc_data.get("epc"),
            epc_data.get("epcHex"),
            epc_data.get("epcStr"),
        ])

    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip().upper()

    return None


def _extract_timestamp(entry: Dict[str, Any], body: Dict[str, Any]) -> Optional[datetime]:
    for container in (body, entry):
        for key in (
            "timestamp",
            "readTime",
            "eventTime",
            "firstSeenTimestamp",
            "lastSeenTimestamp",
            "modified",
            "observedAt",
        ):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                try:
                    return get_datetime(value)
                except Exception:
                    continue

    return None


def _extract_rssi(body: Dict[str, Any]) -> Optional[float]:
    for key in ("peakRssiCdbm", "rssi", "peakRssi", "rssiDbm"):
        value = body.get(key)
        if value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue

        # peakRssiCdbm is expressed in centi-dBm.
        if key == "peakRssiCdbm":
            numeric = numeric / 100.0
        return numeric

    return None


def _extract_reader(entry: Dict[str, Any], body: Dict[str, Any]) -> Optional[str]:
    for container in (body, entry):
        value = container.get("reader")
        if isinstance(value, dict):
            for key in ("name", "hostname", "id"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _compute_event_name(rfid_value: str, read_time: datetime) -> str:
    key = f"{rfid_value.upper()}-{read_time.isoformat()}"
    return frappe.generate_hash(key, 16)


def _get_serial_info(rfid_value: str, cache: Dict[str, Optional[Dict[str, str]]]) -> Optional[Dict[str, str]]:
    if rfid_value in cache:
        return cache[rfid_value]

    serial_info = frappe.db.get_value(
        "Serial No",
        {"custom_barcode": rfid_value},
        ["name", "item_code"],
        as_dict=True,
    )
    cache[rfid_value] = serial_info
    if serial_info:
        return serial_info

    # fallback to Asset custom RFID
    asset_info = frappe.db.get_value(
        "Asset",
        {"custom_rfid": rfid_value},
        ["name", "item_code"],
        as_dict=True,
    )
    cache[rfid_value] = asset_info
    return asset_info


@frappe.whitelist(allow_guest=True)
def ingest_impinj_events() -> Dict[str, Any]:
    """
    Accept tag read notifications coming from Impinj R700.

    The reader should authenticate using an API key/secret pair so that
    `frappe.session.user` is not Guest.
    """

    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required."), frappe.AuthenticationError)

    payload = frappe.request.get_json(silent=True)
    if not payload:
        frappe.throw(_("Request body must contain valid JSON payload."))

    serial_cache: Dict[str, Optional[Dict[str, str]]] = {}
    processed: List[str] = []
    duplicates: List[str] = []
    ignored: List[str] = []

    for node in _iter_impinj_nodes(payload):
        body = node

        if isinstance(node, dict):
            data_section = node.get("data")
            if isinstance(data_section, dict):
                body = data_section

        if not isinstance(body, dict):
            continue

        epc = _extract_epc(body)
        if not epc:
            continue

        read_time = _extract_timestamp(node if isinstance(node, dict) else {}, body)
        if not read_time:
            read_time = now_datetime()

        event_name = _compute_event_name(epc, read_time)
        if frappe.db.exists("RFID Tag Event", event_name):
            duplicates.append(epc)
            continue

        reader_name = _extract_reader(node if isinstance(node, dict) else {}, body)
        antenna_port = body.get("antennaPort") or body.get("antenna") or body.get("antenna_port")
        try:
            antenna_port = int(antenna_port) if antenna_port is not None else None
        except (TypeError, ValueError):
            antenna_port = None

        rssi = _extract_rssi(body)

        serial_info = _get_serial_info(epc, serial_cache)

        base_event = {
            "doctype": "RFID Tag Event",
            "name": event_name,
            "rfid": epc,
            "reader": reader_name,
            "antenna_port": antenna_port,
            "read_time": read_time,
            "rssi": rssi,
            "raw_payload": frappe.as_json(node),
        }

        raddec_payload = build_raddec(base_event)
        if raddec_payload:
            base_event["raddec"] = frappe.as_json(raddec_payload)

        doc = frappe.get_doc(base_event)

        if serial_info:
            doc.serial_no = serial_info.get("name")
            doc.item_code = serial_info.get("item_code")

        try:
            doc.insert(ignore_permissions=True)
            processed.append(doc.name)

            if raddec_payload:
                dispatch_raddec_event(
                    raddec_payload,
                    {
                        "docname": doc.name,
                        "reader": reader_name,
                        "rfid": epc,
                        "source": "impinj",
                    },
                )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "RFID Impinj ingest failure")
            ignored.append(epc)

    if processed:
        frappe.db.commit()

    return {
        "processed": len(processed),
        "duplicates": len(duplicates),
        "errors": len(ignored),
        "processed_names": processed,
        "duplicate_tags": duplicates,
        "error_tags": ignored,
    }
