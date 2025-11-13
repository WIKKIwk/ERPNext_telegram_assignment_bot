from __future__ import annotations

import json
from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import List, Mapping, MutableMapping, Optional, Set

DEFAULT_DB_PATH = Path("assignment_bot.sqlite3")


def _parse_int_set(raw: str) -> Set[int]:
    result: Set[int] = set()
    if not raw:
        return result
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            result.add(int(chunk))
        except ValueError:
            continue
    return result


def _parse_fields(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    value = raw.strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in data if isinstance(item, str)]
    return [part.strip() for part in value.split(",") if part.strip()]

@dataclass(frozen=True)
class AssignmentBotConfig:
    token: str
    admin_ids: Set[int]
    db_path: Path = DEFAULT_DB_PATH
    bot_name: str = "assignment_bot"
    erpnext_base_url: Optional[str] = None
    erpnext_verify_endpoint: str = "/api/method/frappe.auth.get_logged_user"
    report_resource: str = "Lead"
    report_fields: List[str] = field(default_factory=lambda: ["name", "owner", "status", "creation"])
    report_limit: int = 5
    default_customer_group: str = "Commercial"
    default_customer_type: str = "Company"

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_ids


def load_assignment_config(
    env: Optional[Mapping[str, str]] = None,
) -> AssignmentBotConfig:
    """Load bot configuration from environment variables."""

    source: Mapping[str, str]
    if env is None:
        source = os.environ
    else:
        source = env

    token = (
        source.get("ASSIGNMENT_BOT_TOKEN")
        or source.get("TELEGRAM_BOT_TOKEN")
        or source.get("BOT_TOKEN")
    )
    if not token:
        raise RuntimeError("ASSIGNMENT_BOT_TOKEN (or TELEGRAM_BOT_TOKEN) is required.")

    admin_values = (
        source.get("ASSIGNMENT_ADMIN_IDS")
        or source.get("ASSIGNMENT_ADMIN_ID")
        or source.get("TELEGRAM_ADMIN_IDS")
        or source.get("BOT_ADMIN_ID")
        or source.get("ADMIN_USER_ID")
        or ""
    )
    admin_ids = _parse_int_set(admin_values)
    if not admin_ids:
        raise RuntimeError("At least one admin ID is required (set ASSIGNMENT_ADMIN_ID or ASSIGNMENT_ADMIN_IDS).")

    db_path_value = source.get("ASSIGNMENT_BOT_DB_PATH")
    db_path = Path(db_path_value).expanduser() if db_path_value else DEFAULT_DB_PATH

    bot_name = source.get("ASSIGNMENT_BOT_NAME", "assignment_bot").strip() or "assignment_bot"
    erpnext_base = source.get("ERPVERIFY_BASE_URL") or source.get("ERP_NEXT_BASE_URL") or None
    if erpnext_base:
        erpnext_base = erpnext_base.strip().rstrip("/")
    erpnext_endpoint = source.get("ERPVERIFY_ENDPOINT", "/api/method/frappe.auth.get_logged_user")

    report_resource = source.get("REPORT_RESOURCE", "Lead").strip() or "Lead"
    report_fields = _parse_fields(source.get("REPORT_FIELDS"))
    if not report_fields:
        report_fields = ["name", "owner", "status", "creation"]
    report_limit_raw = source.get("REPORT_LIMIT")
    report_limit = 5
    if report_limit_raw:
        try:
            report_limit = max(1, int(report_limit_raw))
        except ValueError:
            pass
    customer_group = source.get("ERP_CUSTOMER_GROUP") or "Commercial"
    customer_type = source.get("ERP_CUSTOMER_TYPE") or "Company"

    return AssignmentBotConfig(
        token=token,
        admin_ids=admin_ids,
        db_path=db_path,
        bot_name=bot_name,
        erpnext_base_url=erpnext_base,
        erpnext_verify_endpoint=erpnext_endpoint.strip() or "/api/method/frappe.auth.get_logged_user",
        report_resource=report_resource,
        report_fields=report_fields,
        report_limit=report_limit,
        default_customer_group=customer_group.strip() or "Commercial",
        default_customer_type=customer_type.strip() or "Company",
    )


def override_env_for_tests(
    env: MutableMapping[str, str],
    *,
    token: str,
    admin_id: int,
    db_path: Optional[str] = None,
) -> None:
    """Helper to patch os.environ inside tests with deterministic values."""

    env["ASSIGNMENT_BOT_TOKEN"] = token
    env["ASSIGNMENT_ADMIN_ID"] = str(admin_id)
    if db_path is not None:
        env["ASSIGNMENT_BOT_DB_PATH"] = db_path
