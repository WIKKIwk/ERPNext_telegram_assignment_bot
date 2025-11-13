from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import quote

import requests
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ChatType
from telegram.error import Forbidden
from telegram.ext import (
    AIORateLimiter,
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from .config import AssignmentBotConfig
from .storage import AssignmentError, AssignmentStorage, Candidate

logger = logging.getLogger(__name__)

CHOICE_PAGE_SIZE = 6
CHOICE_COLUMNS = 2
CHOICE_CONFIG = {
    "item_group": {
        "choices_key": "item_groups",
        "prompt": "3-qadam: Item Group tanlang (tugmani bosing yoki nomini yozing).",
    },
    "uom": {
        "choices_key": "uoms",
        "prompt": "4-qadam: O'lchov birligini tanlang (tugmani bosing yoki nomini yozing).",
    },
}

def _chunk(items: Iterable[Candidate], size: int) -> Iterable[list[Candidate]]:
    batch: list[Candidate] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


class AssignmentBot:
    """Bot that allows an admin to assign a single sales manager per group."""

    def __init__(
        self,
        config: AssignmentBotConfig,
        storage: Optional[AssignmentStorage] = None,
    ):
        self.config = config
        self.storage = storage or AssignmentStorage(config.db_path)
        self.application = (
            Application.builder()
            .token(config.token)
            .rate_limiter(AIORateLimiter())
            .post_init(self._post_init)
            .build()
        )
        self._register_handlers()
        self._bot_username: Optional[str] = None

    async def _post_init(self, application: Application) -> None:
        me = await application.bot.get_me()
        self._bot_username = me.username
        logger.info("Assignment bot connected as %s (@%s)", me.full_name, me.username)

    def _register_handlers(self) -> None:
        app = self.application
        app.add_handler(CommandHandler("start", self.handle_start))
        app.add_handler(CommandHandler("help", self.handle_help))
        app.add_handler(CommandHandler("assign_manager", self.handle_assign_command))
        app.add_handler(CommandHandler("assign_sales_manager", self.handle_assign_command))
        app.add_handler(CommandHandler("report", self.handle_report))
        app.add_handler(CommandHandler("new", self.handle_new_item))
        app.add_handler(CommandHandler("status", self.handle_status))
        app.add_handler(CommandHandler("reset_api", self.handle_reset_api))
        app.add_handler(CommandHandler("clear", self.handle_clear_assignments))
        app.add_handler(
            MessageHandler(
                filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND),
                self.handle_private_message,
            )
        )
        app.add_handler(CallbackQueryHandler(self.handle_assign_callback, pattern=r"^assign_sm:"))
        app.add_handler(
            CallbackQueryHandler(
                self.handle_choice_callback, pattern=r"^(pick|page)_(item_group|uom):"
            )
        )
        app.add_handler(InlineQueryHandler(self.handle_inline_query))

        app.add_handler(
            MessageHandler(
                filters.ChatType.GROUPS & (~filters.COMMAND),
                self.handle_group_activity,
            )
        )

        app.add_error_handler(self.handle_error)

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _validate_api_key(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Fa-f0-9]{15}", value))

    @staticmethod
    def _validate_api_secret(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Fa-f0-9]{15,16}", value))

    @staticmethod
    def _format_assignment_label(assignment: Dict[str, Optional[str]]) -> str:
        parts = [assignment.get("first_name"), assignment.get("last_name")]
        label = " ".join(part for part in parts if part)
        if not label and assignment.get("username"):
            label = f"@{assignment['username']}"
        if not label:
            label = str(assignment.get("user_id"))
        return label

    async def _verify_credentials(self, api_key: str, api_secret: str) -> Tuple[bool, Optional[str]]:
        base_url = self.config.erpnext_base_url
        if not base_url:
            logger.info("ERPNext bazasi ko'rsatilmagan, credential tekshiruvi o'tkazib yuborildi.")
            return True, None
        if not api_key or not api_secret:
            return False, "API kalit yoki secret topilmadi."

        endpoint = self.config.erpnext_verify_endpoint.lstrip("/")
        url = f"{base_url}/{endpoint}" if endpoint else base_url

        def _request() -> Tuple[bool, Optional[str]]:
            headers = {
                "Authorization": f"token {api_key}:{api_secret}",
                "Accept": "application/json",
            }
            response = requests.get(url, headers=headers, timeout=10)
            if 200 <= response.status_code < 300:
                return True, None
            try:
                payload = response.json()
                detail = payload.get("message") or payload.get("exception") or str(payload)
            except ValueError:
                detail = response.text
            return False, f"HTTP {response.status_code}: {detail}"

        try:
            return await asyncio.to_thread(_request)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ERPNext credential tekshiruvi muvaffaqiyatsiz: %s", exc)
            return False, str(exc)

    async def _fetch_report_data(
        self,
        api_key: str,
        api_secret: str,
    ) -> Tuple[bool, Optional[str], list[Dict[str, Any]]]:
        base_url = self.config.erpnext_base_url
        if not base_url:
            return False, "ERPNext URL sozlanmagan.", []

        resource = self.config.report_resource.strip("/")
        endpoint = f"{base_url}/api/resource/{resource}"
        params = {
            "fields": json.dumps(self.config.report_fields),
            "limit_page_length": str(self.config.report_limit),
            "order_by": "modified desc",
        }

        def _request() -> Tuple[bool, Optional[str], list[Dict[str, Any]]]:
            headers = {
                "Authorization": f"token {api_key}:{api_secret}",
                "Accept": "application/json",
            }
            response = requests.get(endpoint, headers=headers, params=params, timeout=10)
            if response.status_code >= 400:
                try:
                    payload = response.json()
                    detail = payload.get("message") or payload.get("exception") or str(payload)
                except ValueError:
                    detail = response.text
                return False, f"HTTP {response.status_code}: {detail}", []
            try:
                payload = response.json()
            except ValueError:
                return False, "ERPNext javobini JSON formatida o'qib bo'lmadi.", []

            data = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(data, list):
                if isinstance(data, dict):
                    data = [data]
                elif data is None:
                    data = []
                else:
                    data = [payload]
            return True, None, data  # type: ignore[list-item]

        try:
            return await asyncio.to_thread(_request)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ERPNext hisobotini olishda xatolik: %s", exc)
            return False, str(exc), []

    async def _fetch_resource_names(
        self,
        api_key: str,
        api_secret: str,
        doctype: str,
        *,
        limit: int = 50,
    ) -> Tuple[bool, Optional[str], list[str]]:
        base_url = self.config.erpnext_base_url
        if not base_url:
            return False, "ERPNext URL sozlanmagan.", []
        endpoint = f"{base_url}/api/resource/{quote(doctype, safe='')}"
        params = {
            "fields": json.dumps(["name"]),
            "limit_page_length": str(limit),
            "order_by": "name asc",
        }

        def _request() -> Tuple[bool, Optional[str], list[str]]:
            headers = {
                "Authorization": f"token {api_key}:{api_secret}",
                "Accept": "application/json",
            }
            response = requests.get(endpoint, headers=headers, params=params, timeout=10)
            if response.status_code >= 400:
                try:
                    payload = response.json()
                    detail = payload.get("message") or payload.get("exception") or str(payload)
                except ValueError:
                    detail = response.text
                return False, f"HTTP {response.status_code}: {detail}", []
            try:
                payload = response.json()
            except ValueError:
                return False, "ERPNext javobini JSON formatida o'qib bo'lmadi.", []

            rows = payload.get("data") if isinstance(payload, dict) else payload
            names = []
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and row.get("name"):
                        names.append(str(row["name"]))
            return True, None, names

        try:
            return await asyncio.to_thread(_request)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ERPNext ma'lumotlarini olishda xatolik: %s", exc)
            return False, str(exc), []

    async def _create_item(
        self,
        api_key: str,
        api_secret: str,
        *,
        item_code: str,
        item_name: str,
        item_group: str,
        uom: str,
    ) -> Tuple[bool, Optional[str]]:
        base_url = self.config.erpnext_base_url
        if not base_url:
            return False, "ERPNext URL sozlanmagan."
        endpoint = f"{base_url}/api/resource/Item"
        payload = {
            "item_code": item_code,
            "item_name": item_name,
            "item_group": item_group,
            "stock_uom": uom,
        }

        def _request() -> Tuple[bool, Optional[str]]:
            headers = {
                "Authorization": f"token {api_key}:{api_secret}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            response = requests.post(endpoint, headers=headers, json=payload, timeout=15)
            if response.status_code >= 400:
                try:
                    body = response.json()
                    detail = (
                        body.get("message")
                        or body.get("exception")
                        or body.get("_server_messages")
                        or str(body)
                    )
                except ValueError:
                    detail = response.text
                return False, f"HTTP {response.status_code}: {detail}"
            return True, None

        try:
            return await asyncio.to_thread(_request)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ERPNext item yaratishda xatolik: %s", exc)
            return False, str(exc)

    def _derive_customer_name(self, title: Optional[str], chat_id: int) -> str:
        if title:
            parts = title.split()
            if len(parts) > 2:
                candidate = " ".join(parts[2:])
            else:
                candidate = title
            candidate = candidate.strip()
            if candidate:
                return candidate
        return f"Auto Customer {chat_id}"

    async def _ensure_customer_exists(
        self,
        assignment: Dict[str, Optional[str]],
        api_key: Optional[str],
        api_secret: Optional[str],
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if assignment.get("customer_docname"):
            return
        if not api_key or not api_secret:
            return
        if not self.config.erpnext_base_url:
            return

        customer_name = self._derive_customer_name(assignment.get("title"), assignment["chat_id"])
        found, docname, _ = await self._find_customer(api_key, api_secret, customer_name)
        if not docname:
            success, docname, detail = await self._create_customer(
                api_key,
                api_secret,
                customer_name,
            )
            if not success:
                logger.warning(
                    "Failed to create customer for chat %s: %s",
                    assignment["chat_id"],
                    detail,
                )
                return
        if not docname:
            return

        self.storage.store_customer_doc(assignment["chat_id"], docname)
        assignment["customer_docname"] = docname
        try:
            await context.bot.send_message(
                chat_id=assignment["chat_id"],
                text=f"Yangi mijoz yaratildi: {customer_name} ({docname}).",
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("Unable to notify group about customer creation: %s", exc)

    async def _find_customer(
        self,
        api_key: str,
        api_secret: str,
        customer_name: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        base_url = self.config.erpnext_base_url
        if not base_url:
            return False, None, "ERPNext URL not configured"
        endpoint = f"{base_url}/api/resource/Customer"
        params = {
            "filters": json.dumps([["Customer", "customer_name", "=", customer_name]]),
            "fields": json.dumps(["name"]),
            "limit_page_length": "1",
        }

        def _request() -> Tuple[bool, Optional[str], Optional[str]]:
            headers = {
                "Authorization": f"token {api_key}:{api_secret}",
                "Accept": "application/json",
            }
            response = requests.get(endpoint, headers=headers, params=params, timeout=10)
            if response.status_code >= 400:
                try:
                    payload = response.json()
                    detail = payload.get("message") or payload.get("exception") or str(payload)
                except ValueError:
                    detail = response.text
                return False, None, detail
            try:
                payload = response.json()
                data = payload.get("data") if isinstance(payload, dict) else payload
                if isinstance(data, list) and data:
                    docname = data[0].get("name")
                    return True, docname, None
            except ValueError:
                return False, None, "JSON decode error"
            return True, None, None

        try:
            return await asyncio.to_thread(_request)
        except Exception as exc:  # noqa: BLE001
            return False, None, str(exc)

    async def _create_customer(
        self,
        api_key: str,
        api_secret: str,
        customer_name: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        base_url = self.config.erpnext_base_url
        if not base_url:
            return False, None, "ERPNext URL not configured"
        endpoint = f"{base_url}/api/resource/Customer"
        payload = {
            "customer_name": customer_name,
            "customer_group": self.config.default_customer_group,
            "customer_type": self.config.default_customer_type,
        }

        def _request() -> Tuple[bool, Optional[str], Optional[str]]:
            headers = {
                "Authorization": f"token {api_key}:{api_secret}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            response = requests.post(endpoint, headers=headers, json=payload, timeout=15)
            if response.status_code >= 400:
                try:
                    body = response.json()
                    detail = (
                        body.get("message")
                        or body.get("exception")
                        or body.get("_server_messages")
                        or str(body)
                    )
                except ValueError:
                    detail = response.text
                return False, None, detail
            try:
                data = response.json().get("data")
                docname = data.get("name") if isinstance(data, dict) else None
            except Exception:  # noqa: BLE001
                docname = None
            return True, docname, None

        try:
            return await asyncio.to_thread(_request)
        except Exception as exc:  # noqa: BLE001
            return False, None, str(exc)

    # --------------------------------------------------------------- handlers
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        if not chat or not user:
            return

        if chat.type == ChatType.PRIVATE:
            self.storage.record_user(
                user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )
            assignment = self.storage.get_user_assignment(user.id)
            if assignment:
                status = assignment.get("credentials_status") or "pending_key"
                group_label = assignment.get("title") or assignment.get("chat_id")
                if status == "pending_key":
                    greeting = (
                        f"Siz \"{group_label}\" guruhida sales manager sifatida tayinlandingiz.\n"
                        "Iltimos ERPNext profilidan API kalitni (masalan: 3739e78cec4e139) yozib yuboring."
                    )
                elif status == "pending_secret":
                    greeting = (
                        "API kalit saqlangan. Endi ERPNext profilidagi API secret ni yuboring "
                        "(masalan: 2a428d03deaceb8)."
                    )
                else:
                    greeting = (
                        "ERPNext API kalitlari saqlangan. Agar yangilash kerak bo'lsa, admin bilan bog'laning."
                    )
            else:
                greeting = (
                    "Assalomu alaykum!\n\n"
                    "Sales manager tanlovi admin tomonidan amalga oshirilgach, "
                    "bot sizga shaxsiy xabar yuboradi."
                )
            await context.bot.send_message(chat_id=chat.id, text=greeting)
            return

        self.storage.record_user(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        self.storage.record_group_chat(chat.id, title=chat.title)
        message = (
            "Salom! Bu bot orqali guruh uchun bitta sales manager tayinlanadi.\n"
            "Admin uchun buyruq: `/assign_manager`"
        )
        await update.message.reply_text(message)

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        if not chat:
            return
        help_text = (
            "Asosiy buyruq:\n"
            "• `/assign_manager` — admin uchun, sales managerni tanlash.\n\n"
            "Foydali buyruqlar:\n"
            "• `/status` — joriy guruh/sales manager holatini ko'rish.\n"
            "• `/reset_api` — (faqat manager) API kalitlarini qayta kiritishni boshlash.\n\n"
            "Shaxsiy chatda /start yuborgan foydalanuvchilar ro'yxatga olinadi."
        )
        if chat.type == ChatType.PRIVATE:
            await context.bot.send_message(chat_id=chat.id, text=help_text)
        else:
            await update.message.reply_text(help_text)

    async def handle_group_activity(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        message = update.message
        if not chat or not message:
            return
        self.storage.record_group_chat(chat.id, title=chat.title)
        if user and not user.is_bot:
            self.storage.record_user(
                user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )
            await self._maybe_progress_group_item_flow(chat, user, message)

    async def handle_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        message = update.message
        if not chat or not message:
            return
        if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            await message.reply_text("Hisobotni faqat guruhda so'rash mumkin.")
            return

        assignment = self.storage.get_group_assignment(chat.id)
        if not assignment:
            await message.reply_text("Bu guruh uchun hali sales manager tayinlanmagan.")
            return
        if assignment.get("credentials_status") != "active":
            await message.reply_text("Sales manager ERPNext API kalitlarini hali tasdiqlamagan.")
            return

        api_key = assignment.get("api_key")
        api_secret = assignment.get("api_secret")
        if not api_key or not api_secret:
            await message.reply_text("API kalitlari saqlanmagan.")
            return

        success, error_detail, rows = await self._fetch_report_data(api_key, api_secret)
        if not success:
            extra = f"\nMa'lumot: {error_detail}" if error_detail else ""
            await message.reply_text("ERPNext hisobotini olishda xatolik yuz berdi." + extra)
            return

        if not rows:
            await message.reply_text("ERPNext dan hisobot ma'lumotlari topilmadi.")
            return

        header = (
            f"ERPNext hisobot ({self.config.report_resource}) — so'nggi {len(rows)} yozuv:"
        )
        field_labels = self.config.report_fields
        lines = [header]
        for row in rows:
            summary_parts: list[str] = []
            for field in field_labels:
                value = row.get(field)
                if value is None or value == "":
                    continue
                summary_parts.append(f"{field}: {value}")
            if not summary_parts:
                summary_parts.append(json.dumps(row, ensure_ascii=False))
            lines.append(" • " + "; ".join(summary_parts))

        await message.reply_text("\n".join(lines))

    async def handle_new_item(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        message = update.message
        if not chat or not user or not message:
            return
        if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            await message.reply_text("Bu buyruq faqat guruh chatida ishlaydi.")
            return

        assignment = self.storage.get_group_assignment(chat.id)
        if not assignment or assignment.get("user_id") != (user.id if user else None):
            await message.reply_text("Faqat ushbu guruhga tayinlangan sales manager /new yozishi mumkin.")
            return

        status = assignment.get("credentials_status")
        if status != "active":
            await message.reply_text("Avval ERPNext API kalitlarini to'liq tasdiqlang.")
            return
        if not self.config.erpnext_base_url:
            await message.reply_text("ERPNext URL sozlanmagan. Administrator bilan bog'laning.")
            return
        await self._ensure_customer_exists(
            assignment,
            assignment.get("api_key"),
            assignment.get("api_secret"),
            context,
        )

        draft = {
            "stage": "await_item_code",
            "data": {},
            "chat_id": chat.id,
        }
        self.storage.save_item_draft(user.id, draft)
        await message.reply_text(
            "Yangi Item yaratishni boshladik.\n"
            "1-qadam: Item Code (ID) ni kiriting. Masalan: ITEM-001\n"
            "Har bir qadamga javobni shu guruhda yozing. Jarayonni qayta boshlash uchun /new ni yana kiriting."
        )

    async def handle_private_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        user = update.effective_user
        if not message or not user:
            return
        text = (message.text or "").strip()
        if not text:
            return

        assignment = self.storage.get_user_assignment(user.id)
        if not assignment:
            await message.reply_text("Siz sales manager sifatida tayinlanmagansiz.")
            return

        status = assignment.get("credentials_status") or "pending_key"
        if status == "pending_key":
            if not self._validate_api_key(text):
                await message.reply_text(
                    "API kalit formati noto'g'ri. Masalan: 3739e78cec4e139"
                )
                return
            self.storage.store_api_key(user.id, text)
            await message.reply_text("API kalit saqlandi. Endi API secret key yuboring.")
            return

        if status == "pending_secret":
            if not self._validate_api_secret(text):
                await message.reply_text(
                    "API secret formati noto'g'ri. Masalan: 2a428d03deaceb8 (15-16 ta hex belgi)"
                )
                return
            api_key = assignment.get("api_key") or ""
            verified, error_detail = await self._verify_credentials(api_key, text)
            self.storage.store_api_secret(user.id, text, verified=verified)
            if verified:
                await message.reply_text(
                    "API kalit muvaffaqqiyatli kiritildi.\nERPNext bilan ham muvaffaqqiyatli ulandi."
                )
                await self._ensure_customer_exists(assignment, api_key, text, context)
            else:
                extra = f"\nMa'lumot: {error_detail}" if error_detail else ""
                await message.reply_text(
                    "API secret saqlandi, biroq ERPNext bilan ulanish amalga oshmadi. Lutfan ma'lumotlarni tekshiring." + extra
                )
            group_id = assignment["chat_id"]
            label = self._format_assignment_label(assignment)
            group_message = (
                f"{label} ERPNext API kalitlarini kiritdi."
                if verified
                else f"{label} API ma'lumotlarini yubordi, ammo ERPNext bilan ulanish amalga oshmadi."
            )
            await context.bot.send_message(chat_id=group_id, text=group_message)
            return

        await message.reply_text(
            "API ma'lumotlari allaqachon saqlangan. Yangi Item jarayonini guruhda /new orqali boshlang."
        )

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        message = update.message
        if not chat or not user or not message:
            return

        if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            assignment = self.storage.get_group_assignment(chat.id)
            if not assignment:
                await message.reply_text("Hali sales manager tayinlanmagan.")
                return
            label = self._format_assignment_label(assignment)
            status = assignment.get("credentials_status") or "pending_key"
            customer = assignment.get("customer_docname") or "yaratilmagan"
            await message.reply_text(
                f"Guruh: {chat.title or chat.id}\n"
                f"Sales Manager: {label}\n"
                f"API holati: {status}\n"
                f"Customer: {customer}"
            )
            return

        assignment = self.storage.get_user_assignment(user.id)
        if not assignment:
            await message.reply_text("Sizga hali guruh biriktirilmagan.")
            return
        status = assignment.get("credentials_status") or "pending_key"
        customer = assignment.get("customer_docname") or "yaratilmagan"
        await message.reply_text(
            f"Guruh: {assignment.get('title') or assignment.get('chat_id')}\n"
            f"API holati: {status}\n"
            f"Customer: {customer}\n"
            f"Customer yaratish uchun guruhda /new yoki API tasdiqlangach kuting."
        )

    async def handle_reset_api(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        message = update.message
        if not chat or not user or not message or chat.type != ChatType.PRIVATE:
            return
        assignment = self.storage.get_user_assignment(user.id)
        if not assignment:
            await message.reply_text("Sizga hali guruh biriktirilmagan.")
            return
        self.storage.reset_credentials(user.id)
        await message.reply_text(
            "API kalitlari reset qilindi. Iltimos, yangi API kalitni yuboring."
        )
        group_id = assignment["chat_id"]
        try:
            await context.bot.send_message(
                chat_id=group_id,
                text=f"{self._format_assignment_label(assignment)} API kalitlarini yangilamoqda.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("Group notice failed: %s", exc)

    async def _progress_item_creation(
        self,
        *,
        user_id: int,
        message,
        assignment: Dict[str, Optional[str]],
        draft: Dict[str, Any],
        text: str,
    ) -> None:
        api_key = assignment.get("api_key")
        api_secret = assignment.get("api_secret")
        if not api_key or not api_secret:
            await message.reply_text("API credentiallari topilmadi. Avval ularni qayta kiriting.")
            self.storage.delete_item_draft(user_id)
            return

        stage = draft.get("stage")
        data = draft.setdefault("data", {})
        text_value = text.strip()
        if not text_value:
            await message.reply_text("Bo'sh qiymat qabul qilinmaydi. Qaytadan kiriting.")
            return

        if stage == "await_item_code":
            data["item_code"] = text_value
            draft["stage"] = "await_item_name"
            self.storage.save_item_draft(user_id, draft)
            await message.reply_text("2-qadam: Item Name ni kiriting.")
            return

        if stage == "await_item_name":
            data["item_name"] = text_value
            await self._prompt_item_group(user_id, message, draft, api_key, api_secret)
            return

        if stage == "await_item_group":
            choices = (draft.get("choices") or {}).get("item_groups", [])
            selected = self._match_choice(text_value, choices)
            if not selected:
                await message.reply_text("Noto'g'ri item group. Ro'yxatdan birini tanlang yoki aniq nomini kiriting.")
                return
            data["item_group"] = selected
            await self._prompt_uom(user_id, message, draft, api_key, api_secret)
            return

        if stage == "await_uom":
            choices = (draft.get("choices") or {}).get("uoms", [])
            selected = self._match_choice(text_value, choices)
            if not selected:
                await message.reply_text("Noto'g'ri o'lchov birligi. Ro'yxatdan birini tanlang yoki aniq nomini kiriting.")
                return
            data["stock_uom"] = selected
            success, error_detail = await self._create_item(
                api_key,
                api_secret,
                item_code=data["item_code"],
                item_name=data["item_name"],
                item_group=data["item_group"],
                uom=data["stock_uom"],
            )
            if success:
                await message.reply_text(
                    "✅ Item ERPNext ga muvaffaqiyatli yaratildi.\n"
                    f"• Item Code: {data['item_code']}\n"
                    f"• Item Name: {data['item_name']}\n"
                    f"• Item Group: {data['item_group']}\n"
                    f"• UOM: {data['stock_uom']}"
                )
                self.storage.delete_item_draft(user_id)
            else:
                extra = f"\nMa'lumot: {error_detail}" if error_detail else ""
                await message.reply_text("Item yaratishda xatolik yuz berdi." + extra)
            return

        await message.reply_text("Jarayon topilmadi. /new orqali qayta boshlang.")
        self.storage.delete_item_draft(user_id)

    def _match_choice(self, text_value: str, choices: list[str]) -> Optional[str]:
        if not choices:
            return text_value
        for option in choices:
            if option.lower() == text_value.lower():
                return option
        return None

    async def _prompt_item_group(
        self,
        user_id: int,
        message,
        draft: Dict[str, Any],
        api_key: str,
        api_secret: str,
    ) -> None:
        success, error_detail, groups = await self._fetch_resource_names(
            api_key, api_secret, "Item Group", limit=500
        )
        if not success or not groups:
            extra = f"\nMa'lumot: {error_detail}" if error_detail else ""
            await message.reply_text("Item group ro'yxatini olishda xatolik yuz berdi." + extra)
            self.storage.delete_item_draft(user_id)
            return
        draft["stage"] = "await_item_group"
        draft.setdefault("choices", {})["item_groups"] = groups
        draft.setdefault("pages", {})["item_group"] = 0
        draft.setdefault("chat_id", message.chat_id)
        self.storage.save_item_draft(user_id, draft)
        await self._send_choice_keyboard(
            kind="item_group",
            draft=draft,
            chat_id=message.chat_id,
            user_id=user_id,
            message=message,
        )

    async def _prompt_uom(
        self,
        user_id: int,
        message,
        draft: Dict[str, Any],
        api_key: str,
        api_secret: str,
    ) -> None:
        success, error_detail, uoms = await self._fetch_resource_names(
            api_key, api_secret, "UOM", limit=500
        )
        if not success or not uoms:
            extra = f"\nMa'lumot: {error_detail}" if error_detail else ""
            await message.reply_text("O'lchov birliklari ro'yxatini olishda xatolik yuz berdi." + extra)
            self.storage.delete_item_draft(user_id)
            return
        draft["stage"] = "await_uom"
        draft.setdefault("choices", {})["uoms"] = uoms
        draft.setdefault("pages", {})["uom"] = 0
        self.storage.save_item_draft(user_id, draft)
        await self._send_choice_keyboard(
            kind="uom",
            draft=draft,
            chat_id=message.chat_id,
            user_id=user_id,
            message=message,
        )
        if self._bot_username:
            search_button = InlineKeyboardButton(
                "🔍 UOM qidirish",
                switch_inline_query_current_chat="",
            )
            await message.reply_text(
                "Yuqoridagi tugmalar bilan tanlang yoki pastdagi qidiruv tugmasini bosing.",
                reply_markup=InlineKeyboardMarkup([[search_button]]),
            )

    async def _send_choice_keyboard(
        self,
        *,
        kind: str,
        draft: Dict[str, Any],
        chat_id: int,
        user_id: int,
        message=None,
        query=None,
    ) -> None:
        config = CHOICE_CONFIG.get(kind)
        if not config:
            return
        choices_key = config["choices_key"]
        choices = (draft.get("choices") or {}).get(choices_key, [])
        if not choices:
            text = "Tanlash uchun ma'lumot topilmadi."
            if query:
                await query.edit_message_text(text)
            elif message:
                await message.reply_text(text)
            return

        pages = draft.setdefault("pages", {})
        page = pages.get(kind, 0)
        max_page = max(0, (len(choices) - 1) // CHOICE_PAGE_SIZE)
        page = max(0, min(page, max_page))
        pages[kind] = page
        start = page * CHOICE_PAGE_SIZE
        end = min(len(choices), start + CHOICE_PAGE_SIZE)
        chunk = choices[start:end]

        rows = []
        current_row: list[InlineKeyboardButton] = []
        for idx, option in enumerate(chunk, start=start):
            label = option if len(option) <= 32 else option[:29] + "…"
            current_row.append(
                InlineKeyboardButton(
                    label,
                    callback_data=f"pick_{kind}:{chat_id}:{user_id}:{idx}",
                )
            )
            if len(current_row) == CHOICE_COLUMNS:
                rows.append(current_row)
                current_row = []
        if current_row:
            rows.append(current_row)

        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    "⬅️ Oldingi",
                    callback_data=f"page_{kind}:{chat_id}:{user_id}:{page - 1}",
                )
            )
        if end < len(choices):
            nav_buttons.append(
                InlineKeyboardButton(
                    "Keyingi ➡️",
                    callback_data=f"page_{kind}:{chat_id}:{user_id}:{page + 1}",
                )
            )
        if nav_buttons:
            rows.append(nav_buttons)

        keyboard = InlineKeyboardMarkup(rows) if rows else None
        prompt = config["prompt"]
        info = f"Sahifa {page + 1}/{max_page + 1}. Jami: {len(choices)}."
        text = f"{prompt}\n{info}"

        if query:
            await query.edit_message_text(text, reply_markup=keyboard)
        elif message:
            await message.reply_text(text, reply_markup=keyboard)

    async def handle_choice_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data:
            return
        try:
            action, chat_id_raw, user_id_raw, value = query.data.split(":", 3)
            chat_id = int(chat_id_raw)
            target_user_id = int(user_id_raw)
        except ValueError:
            await query.answer("Noto'g'ri format.", show_alert=True)
            return

        user = query.from_user
        if not user or user.id != target_user_id:
            await query.answer("Bu tugmalar siz uchun emas.", show_alert=True)
            return

        assignment = self.storage.get_group_assignment(chat_id)
        if not assignment or assignment.get("user_id") != target_user_id:
            await query.answer("Guruh tayinlanishi topilmadi.", show_alert=True)
            return

        if assignment.get("credentials_status") != "active":
            await query.answer("Avval API credentiallari tasdiqlansin.", show_alert=True)
            return

        draft = self.storage.get_item_draft(target_user_id)
        if not draft or draft.get("chat_id") != chat_id:
            await query.answer("Jarayon topilmadi. /new bilan qayta boshlang.", show_alert=True)
            if draft and draft.get("chat_id") != chat_id:
                self.storage.delete_item_draft(target_user_id)
            return

        if action.startswith("page_"):
            _, kind = action.split("_", 1)
            if kind not in CHOICE_CONFIG:
                await query.answer("Noto'g'ri tur.", show_alert=True)
                return
            try:
                page = max(0, int(value))
            except ValueError:
                await query.answer("Noto'g'ri sahifa.", show_alert=True)
                return
            draft.setdefault("pages", {})[kind] = page
            self.storage.save_item_draft(target_user_id, draft)
            await self._send_choice_keyboard(
                kind=kind,
                draft=draft,
                chat_id=chat_id,
                user_id=target_user_id,
                query=query,
            )
            await query.answer()
            return

        if action.startswith("pick_"):
            _, kind = action.split("_", 1)
            try:
                index = int(value)
            except ValueError:
                await query.answer("Noto'g'ri tanlov.", show_alert=True)
                return
            config = CHOICE_CONFIG.get(kind)
            if not config:
                await query.answer("Noto'g'ri tur.", show_alert=True)
                return
            options = (draft.get("choices") or {}).get(config["choices_key"], [])
            if index < 0 or index >= len(options):
                await query.answer("Variant topilmadi.", show_alert=True)
                return
            selected = options[index]
            await query.answer(f"{selected} tanlandi.")
            try:
                await query.edit_message_text(f"{selected} tanlandi.")
            except Exception:  # noqa: BLE001
                pass
            msg = query.message
            if not msg:
                msg = await context.bot.send_message(chat_id=chat_id, text=f"{selected} tanlandi.")
            await self._progress_item_creation(
                user_id=target_user_id,
                message=msg,
                assignment=assignment,
                draft=draft,
                text=selected,
            )
            return

        await query.answer("Noma'lum amal.", show_alert=True)

    async def handle_inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        inline_query = update.inline_query
        if not inline_query:
            return
        user = inline_query.from_user
        if not user:
            return

        draft = self.storage.get_item_draft(user.id)
        if not draft or draft.get("stage") != "await_uom":
            await inline_query.answer([], cache_time=5, is_personal=True)
            return

        choices = (draft.get("choices") or {}).get("uoms", [])
        if not choices:
            await inline_query.answer([], cache_time=5, is_personal=True)
            return

        query_text = (inline_query.query or "").strip().lower()
        results = []
        for idx, option in enumerate(choices):
            if query_text and query_text not in option.lower():
                continue
            results.append(
                InlineQueryResultArticle(
                    id=f"uom-{idx}",
                    title=option,
                    input_message_content=InputTextMessageContent(option),
                    description="Tanlash uchun tegishli tugmani bosing",
                )
            )
            if len(results) >= 25:
                break

        await inline_query.answer(results, cache_time=0, is_personal=True)

    async def _maybe_progress_group_item_flow(self, chat, user, message) -> None:
        text = (message.text or "").strip()
        if not text:
            return
        assignment = self.storage.get_group_assignment(chat.id)
        if (
            not assignment
            or assignment.get("user_id") != user.id
            or assignment.get("credentials_status") != "active"
        ):
            return
        draft = self.storage.get_item_draft(user.id)
        if not draft or not draft.get("stage"):
            return
        draft_chat_id = draft.get("chat_id")
        if draft_chat_id and draft_chat_id != chat.id:
            await message.reply_text(
                "Item yaratish boshqa guruhda boshlangan. /new bilan shu guruhda qayta boshlang."
            )
            self.storage.delete_item_draft(user.id)
            return
        draft.setdefault("chat_id", chat.id)
        await self._progress_item_creation(
            user_id=user.id,
            message=message,
            assignment=assignment,
            draft=draft,
            text=text,
        )

    async def handle_assign_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        message = update.message
        if not chat or not user or not message:
            return

        if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            await message.reply_text("Bu buyruq faqat guruhlarda ishlaydi.")
            return

        if not self.config.is_admin(user.id):
            await message.reply_text("Bu buyruq faqat administrator uchun.")
            return

        self.storage.record_group_chat(chat.id, title=chat.title)

        existing = self.storage.get_group_assignment(chat.id)
        if existing:
            label_parts = [existing.get("first_name") or "", existing.get("last_name") or ""]
            label = " ".join(part for part in label_parts if part).strip()
            if not label and existing.get("username"):
                label = f"@{existing['username']}"
            if not label:
                label = str(existing["user_id"])
            await message.reply_text(f"Bu guruh uchun allaqachon sales manager tayinlangan: {label}.")
            return

        candidates = self.storage.list_unassigned_users(limit=25)
        if not candidates:
            await message.reply_text(
                "Hali hech kim botga shaxsiy chatda /start yubormagan. "
                "Iltimos, nomzodlar /start yuborsin."
            )
            return

        keyboard_rows = []
        for chunk in _chunk(candidates, size=2):
            buttons = [
                InlineKeyboardButton(
                    text=candidate.display_label,
                    callback_data=f"assign_sm:{chat.id}:{candidate.telegram_id}",
                )
                for candidate in chunk
            ]
            keyboard_rows.append(buttons)

        prompt = (
            "Sales manager qilib tayinlamoqchi bo'lgan foydalanuvchini tanlang.\n"
            "Ro'yxatda ko'rinmasa, ular botga /start yuborganini tekshiring."
        )
        await message.reply_text(prompt, reply_markup=InlineKeyboardMarkup(keyboard_rows))

    async def handle_assign_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()
        user = query.from_user
        if not user:
            return

        if not self.config.is_admin(user.id):
            await query.edit_message_text("Faqat administrator tanlovni tasdiqlashi mumkin.")
            return

        data = (query.data or "").split(":")
        if len(data) != 3:
            await query.edit_message_text("Noto'g'ri format.")
            return
        _, chat_id_raw, candidate_id_raw = data
        try:
            chat_id = int(chat_id_raw)
            candidate_id = int(candidate_id_raw)
        except ValueError:
            await query.edit_message_text("Tanlov ma'lumotlari buzilgan.")
            return

        chat = query.message.chat if query.message else None
        if not chat or chat.id != chat_id:
            await query.edit_message_text("Tanlov bu guruhga tegishli emas.")
            return

        self.storage.record_group_chat(chat_id, title=chat.title)

        candidate = self.storage.get_user(candidate_id)
        if not candidate:
            await query.edit_message_text("Bu foydalanuvchi botga /start yubormagan.")
            return

        try:
            await context.bot.get_chat_member(chat_id, candidate_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chat member tekshiruvda xatolik: %s", exc)
            await query.edit_message_text("Foydalanuvchi guruh a'zosi emas yoki aniqlanmadi.")
            return

        try:
            self.storage.assign_sales_manager(chat_id=chat_id, user_id=candidate_id)
        except AssignmentError as exc:
            await query.edit_message_text(str(exc))
            return

        private_message = (
            "🎉 Tabriklaymiz!\n\n"
            f"Siz \"{chat.title or chat_id}\" guruhida sales manager sifatida tayinlandingiz.\n"
            "Bot orqali keladigan so'rovlarni kuzatib boring.\n\n"
            "Endi ERPNext profilidan API kalitni shu chatga yuboring (masalan: 3739e78cec4e139).\n"
            "Kalit saqlangach bot sizdan API secret ni so'raydi."
        )
        try:
            await context.bot.send_message(
                chat_id=candidate_id,
                text=private_message,
            )
            dm_status = "Shaxsiy xabar yuborildi."
        except Forbidden:
            dm_status = (
                "Foydalanuvchiga shaxsiy xabar yuborilmadi. "
                "Iltimos, ularga botga /start yuborishlarini eslatib qo'ying."
            )

        await query.edit_message_text(
            f"{candidate.display_label} sales manager sifatida tayinlandi.\n{dm_status}"
        )

    async def handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Bot xatoligi: %s", context.error)

    async def handle_clear_assignments(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        message = update.message
        if not user or not message:
            return
        if not self.config.is_admin(user.id):
            await message.reply_text("Bu buyruq faqat adminlar uchun.")
            return

        self.storage.clear_all_assignments()
        await message.reply_text("Barcha sales manager tayinlovlari va API ma'lumotlari o'chirildi.")
