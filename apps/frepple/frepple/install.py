# -*- coding: utf-8 -*-
import json

import frappe

MODULE_NAME = "Frepple"
WORKSPACE_NAME = "Frepple"


def after_install():
	ensure_module_definition()
	ensure_workspace()


def ensure_module_definition():
	if frappe.db.exists("Module Def", MODULE_NAME):
		return

	module_def = frappe.new_doc("Module Def")
	module_def.module_name = MODULE_NAME
	module_def.app_name = "frepple"
	module_def.save(ignore_permissions=True)


def ensure_workspace():
	if frappe.db.exists("Workspace", WORKSPACE_NAME):
		return

	workspace = frappe.new_doc("Workspace")
	workspace.label = WORKSPACE_NAME
	workspace.title = WORKSPACE_NAME
	workspace.module = MODULE_NAME
	workspace.icon = "fa fa-calendar"
	workspace.public = 1
	workspace.content = json.dumps(
		[
			{
				"id": "header_frepple",
				"type": "header",
				"data": {
					"text": "<span class=\\\"h4\\\"><b>Frepple Planning</b></span>",
					"col": 12,
				},
			},
			{
				"id": "shortcut_frepple_settings",
				"type": "shortcut",
				"data": {"shortcut_name": "Frepple Settings", "col": 3},
			},
			{
				"id": "shortcut_frepple_fetch",
				"type": "shortcut",
				"data": {"shortcut_name": "Integration Data", "col": 3},
			},
			{
				"id": "shortcut_frepple_page",
				"type": "shortcut",
				"data": {"shortcut_name": "Frepple Custom Page", "col": 3},
			},
		]
	)

	workspace.append(
		"shortcuts",
		{
			"label": "Frepple Settings",
			"type": "DocType",
			"link_to": "Frepple Settings",
			"color": "#2980b9",
			"icon": "octicon octicon-tools",
		},
	)
	workspace.append(
		"shortcuts",
		{
			"label": "Integration Data",
			"type": "DocType",
			"link_to": "Frepple Integration Data Fetching",
			"color": "#2980b9",
			"icon": "octicon octicon-cloud-download",
		},
	)
	workspace.append(
		"shortcuts",
		{
			"label": "Frepple Custom Page",
			"type": "Page",
			"link_to": "frepple-custom-page",
			"color": "#2980b9",
			"icon": "octicon octicon-organization",
		},
	)

	workspace.insert(ignore_permissions=True)
