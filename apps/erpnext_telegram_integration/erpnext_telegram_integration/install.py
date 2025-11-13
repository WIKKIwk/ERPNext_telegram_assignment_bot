# -*- coding: utf-8 -*-
import json

import frappe

TELEGRAM_MODULE = "Erpnext Telegram Integration"
EXTRA_NOTIFICATIONS_MODULE = "Extra Notifications"


def after_install():
	for module_name in (TELEGRAM_MODULE, EXTRA_NOTIFICATIONS_MODULE):
		ensure_module_definition(module_name)

	ensure_telegram_workspace()
	ensure_extra_notifications_workspace()


def ensure_module_definition(module_name: str):
	if frappe.db.exists("Module Def", module_name):
		return

	module_def = frappe.new_doc("Module Def")
	module_def.module_name = module_name
	module_def.app_name = "erpnext_telegram_integration"
	module_def.save(ignore_permissions=True)


def ensure_telegram_workspace():
	workspace_name = TELEGRAM_MODULE
	if frappe.db.exists("Workspace", workspace_name):
		return

	workspace = frappe.new_doc("Workspace")
	workspace.label = workspace_name
	workspace.title = workspace_name
	workspace.module = TELEGRAM_MODULE
	workspace.icon = "octicon octicon-comment-discussion"
	workspace.public = 1
	workspace.content = json.dumps(
		[
			{
				"id": "header_telegram",
				"type": "header",
				"data": {
					"text": "<span class=\\\"h4\\\"><b>Telegram Integrations</b></span>",
					"col": 12,
				},
			},
			{
				"id": "shortcut_telegram_settings",
				"type": "shortcut",
				"data": {"shortcut_name": "Telegram Settings", "col": 3},
			},
			{
				"id": "shortcut_telegram_notification",
				"type": "shortcut",
				"data": {"shortcut_name": "Telegram Notification", "col": 3},
			},
			{
				"id": "shortcut_telegram_users",
				"type": "shortcut",
				"data": {"shortcut_name": "Telegram User Settings", "col": 3},
			},
		]
	)

	workspace.append(
		"shortcuts",
		{
			"label": "Telegram Settings",
			"type": "DocType",
			"link_to": "Telegram Settings",
			"color": "#3498db",
			"icon": "octicon octicon-gear",
		},
	)
	workspace.append(
		"shortcuts",
		{
			"label": "Telegram Notification",
			"type": "DocType",
			"link_to": "Telegram Notification",
			"color": "#3498db",
			"icon": "octicon octicon-bell",
		},
	)
	workspace.append(
		"shortcuts",
		{
			"label": "Telegram User Settings",
			"type": "DocType",
			"link_to": "Telegram User Settings",
			"color": "#3498db",
			"icon": "octicon octicon-organization",
		},
	)

	workspace.insert(ignore_permissions=True)


def ensure_extra_notifications_workspace():
	workspace_name = EXTRA_NOTIFICATIONS_MODULE
	if frappe.db.exists("Workspace", workspace_name):
		return

	workspace = frappe.new_doc("Workspace")
	workspace.label = workspace_name
	workspace.title = workspace_name
	workspace.module = EXTRA_NOTIFICATIONS_MODULE
	workspace.icon = "octicon octicon-bell"
	workspace.public = 1
	workspace.content = json.dumps(
		[
			{
				"id": "header_extra_notifications",
				"type": "header",
				"data": {
					"text": "<span class=\\\"h4\\\"><b>Extra Notifications</b></span>",
					"col": 12,
				},
			},
			{
				"id": "shortcut_sms_notification",
				"type": "shortcut",
				"data": {"shortcut_name": "SMS Notification", "col": 3},
			},
			{
				"id": "shortcut_date_notification",
				"type": "shortcut",
				"data": {"shortcut_name": "Date Notification", "col": 3},
			},
			{
				"id": "shortcut_extra_notification_log",
				"type": "shortcut",
				"data": {"shortcut_name": "Extra Notification Log", "col": 3},
			},
		]
	)

	workspace.append(
		"shortcuts",
		{
			"label": "SMS Notification",
			"type": "DocType",
			"link_to": "SMS Notification",
			"color": "#1abc9c",
			"icon": "octicon octicon-comment",
		},
	)
	workspace.append(
		"shortcuts",
		{
			"label": "Date Notification",
			"type": "DocType",
			"link_to": "Date Notification",
			"color": "#1abc9c",
			"icon": "octicon octicon-calendar",
		},
	)
	workspace.append(
		"shortcuts",
		{
			"label": "Extra Notification Log",
			"type": "DocType",
			"link_to": "Extra Notification Log",
			"color": "#1abc9c",
			"icon": "octicon octicon-unmute",
		},
	)

	workspace.insert(ignore_permissions=True)
