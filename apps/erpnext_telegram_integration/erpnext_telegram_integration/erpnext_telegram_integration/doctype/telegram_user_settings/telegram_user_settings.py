# -*- coding: utf-8 -*-
# Copyright (c) 2019, Youssef Restom and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import binascii
import os
from typing import Optional

from erpnext_telegram_integration.utils.telegram_api import get_updates


class TelegramUserSettings(Document):
	

	def validate(self):
		pass


	def get_token_settings(self):
		return frappe.db.get_value('Telegram Settings', self.telegram_settings,'telegram_token')


	def get_chat_id(self):
		telegram_token = self.get_token_settings()
		updates = get_updates(telegram_token, limit=100)
		self.telegram_chat_id = _find_chat_id_by_token(updates, self.telegram_token)




@frappe.whitelist()
def generate_telegram_token(is_group_chat):
	if int(is_group_chat) == 1:
		return "/"+ binascii.hexlify(os.urandom(19)).decode()
	else:
		return binascii.hexlify(os.urandom(20)).decode()

@frappe.whitelist()
def get_chat_id_button(telegram_token, telegram_settings):
	telegram_token_bot = frappe.db.get_value('Telegram Settings', telegram_settings,'telegram_token')
	updates = get_updates(telegram_token_bot, limit=100)
	chat_id = _find_chat_id_by_token(updates, telegram_token)
	if chat_id:
		return chat_id
	return None


def _find_chat_id_by_token(updates, token: str) -> Optional[int]:
	for update in updates:
		message = (update.get("message") or update.get("channel_post") or {})
		text = message.get("text")
		chat = message.get("chat") or {}
		chat_id = chat.get("id")
		if text and text.strip() == token and chat_id:
			return chat_id
	return None
	
