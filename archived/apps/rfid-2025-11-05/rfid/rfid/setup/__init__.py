"""Workspace setup helpers for the ERPNext RFID app."""

from __future__ import annotations

import json
from typing import Dict

import frappe
from frappe.utils import add_days, today

OPERATIONS_SHORTCUTS = [
    {
        "label": "RFID Print Queue",
        "link_to": "RFID Print Queue",
        "type": "DocType",
        "icon": "octicon octicon-radio-tower",
        "color": "#5E64FF",
    },
    {
        "label": "Serial Numbers",
        "link_to": "Serial No",
        "type": "DocType",
        "icon": "octicon octicon-number",
        "color": "#29CD42",
    },
    {
        "label": "Assets",
        "link_to": "Asset",
        "type": "DocType",
        "icon": "octicon octicon-device-desktop",
        "color": "#ffa00a",
    },
    {
        "label": "Stock Entries",
        "link_to": "Stock Entry",
        "type": "DocType",
        "icon": "octicon octicon-package",
        "color": "#ff5858",
    },
]

INTEGRATION_SHORTCUTS = [
    {
        "label": "RFID Tag Event",
        "link_to": "RFID Tag Event",
        "type": "DocType",
        "icon": "octicon octicon-pulse",
        "color": "#6c5ce7",
    },
    {
        "label": "RFID Webhook",
        "link_to": "RFID Webhook",
        "type": "DocType",
        "icon": "octicon octicon-globe",
        "color": "#00cec9",
    },
]

HEADER_HTML = '<span class="h4"><b>RFID Operations</b></span>'
SUBTEXT_HTML = '<span class="text-muted">Jump into the most common RFID tasks using the shortcuts below.</span>'
MONITOR_HEADER = '<span class="h5"><b>Monitoring</b></span>'
INTEGRATION_HEADER = '<span class="h5"><b>Integrations & Logs</b></span>'


def deploy_workspace() -> None:
    """Create or refresh the RFID workspace, shortcuts, and number cards."""

    number_cards = _build_number_cards()
    valid_names = {cfg["name"] for cfg in number_cards}

    for name in frappe.get_all("Number Card", filters={"name": ["like", "RFID %"]}, pluck="name"):
        if name not in valid_names:
            frappe.delete_doc("Number Card", name, ignore_permissions=True)

    card_names = [_ensure_number_card(cfg) for cfg in number_cards]

    ws_name = frappe.db.exists("Workspace", "Rfid")
    ws = frappe.get_doc("Workspace", ws_name) if ws_name else frappe.new_doc("Workspace")

    if not ws_name:
        ws.name = "Rfid"
        ws.sequence_id = 0

    ws.label = "RFID"
    ws.title = "RFID"
    ws.module = "Rfid"
    ws.public = 1
    ws.is_hidden = 0

    ws.shortcuts = []
    for cfg in OPERATIONS_SHORTCUTS + INTEGRATION_SHORTCUTS:
        ws.append("shortcuts", cfg)

    ws.number_cards = []
    for cfg in number_cards:
        ws.append("number_cards", {"number_card_name": cfg["name"], "label": cfg["label"]})

    ws.save(ignore_permissions=True)
    ws = frappe.get_doc("Workspace", "Rfid")

    content = [
        {"id": "header_rfid_operations", "type": "header", "data": {"text": HEADER_HTML, "col": 12}},
        {"id": "subheader_rfid_hint", "type": "header", "data": {"text": SUBTEXT_HTML, "col": 12}},
    ]

    for idx, cfg in enumerate(OPERATIONS_SHORTCUTS):
        content.append(
            {
                "id": f"shortcut_ops_{idx}",
                "type": "shortcut",
                "data": {"shortcut_name": cfg["label"], "col": 3},
            }
        )

    content.append({"id": "header_rfid_monitor", "type": "header", "data": {"text": MONITOR_HEADER, "col": 12}})

    for idx, card_name in enumerate(card_names):
        content.append(
            {
                "id": f"number_card_{idx}",
                "type": "number_card",
                "data": {"number_card_name": card_name, "col": 2},
            }
        )

    content.append({"id": "header_rfid_integrations", "type": "header", "data": {"text": INTEGRATION_HEADER, "col": 12}})

    for idx, cfg in enumerate(INTEGRATION_SHORTCUTS):
        content.append(
            {
                "id": f"shortcut_integration_{idx}",
                "type": "shortcut",
                "data": {"shortcut_name": cfg["label"], "col": 6},
            }
        )

    ws.content = json.dumps(content)
    ws.save(ignore_permissions=True)
    frappe.db.commit()


def _build_number_cards() -> list[Dict[str, object]]:
    today_str = today()
    week_ago = add_days(today_str, -7)
    return [
        {
            "name": "RFID Pending Queue",
            "label": "Pending Queue",
            "doctype": "RFID Print Queue",
            "aggregate_function": "Count",
            "filters": [["RFID Print Queue", "status", "=", "Pending"]],
            "color": "#5E64FF",
            "icon": "octicon octicon-radio-tower",
        },
        {
            "name": "RFIDs Created Today",
            "label": "RFIDs Created Today",
            "doctype": "Serial No",
            "aggregate_function": "Count",
            "filters": [["Serial No", "creation", ">=", today_str]],
            "color": "#29CD42",
            "icon": "octicon octicon-number",
        },
        {
            "name": "RFID Assets Tagged",
            "label": "RFID Assets Tagged",
            "doctype": "Asset",
            "aggregate_function": "Count",
            "filters": [["Asset", "custom_rfid", "is", "set"]],
            "color": "#ffa00a",
            "icon": "octicon octicon-device-desktop",
        },
        {
            "name": "RFID Stock Entries 7d",
            "label": "RFID Stock Entries 7d",
            "doctype": "Stock Entry",
            "aggregate_function": "Count",
            "filters": [["Stock Entry", "creation", ">=", week_ago]],
            "color": "#ff5858",
            "icon": "octicon octicon-package",
        },
        {
            "name": "RFID Printed Today",
            "label": "RFID Printed Today",
            "doctype": "RFID Print Queue",
            "aggregate_function": "Count",
            "filters": [["RFID Print Queue", "status", "=", "Completed"], ["RFID Print Queue", "modified", ">=", today_str]],
            "color": "#7575ff",
            "icon": "octicon octicon-check",
        },
    ]


def _ensure_number_card(cfg: Dict[str, object]) -> str:
    name = cfg["name"]  # type: ignore[index]
    if frappe.db.exists("Number Card", name):
        card = frappe.get_doc("Number Card", name)
    else:
        card = frappe.get_doc(
            {
                "doctype": "Number Card",
                "name": name,
                "label": cfg["label"],
                "document_type": cfg["doctype"],
                "function": cfg["aggregate_function"],
                "filters_json": json.dumps(cfg["filters"]),
                "color": cfg.get("color"),
                "icon": cfg.get("icon"),
                "type": "Document Type",
            }
        )
        card.insert(ignore_permissions=True)

    card.label = cfg["label"]
    card.document_type = cfg["doctype"]
    card.function = cfg["aggregate_function"]
    card.filters_json = json.dumps(cfg["filters"])
    card.color = cfg.get("color")
    card.icon = cfg.get("icon")
    card.type = "Document Type"
    card.save(ignore_permissions=True)

    if card.name != name:
        frappe.model.rename_doc.rename_doc("Number Card", card.name, name, force=True)

    return name
