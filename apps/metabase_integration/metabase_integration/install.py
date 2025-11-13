# -*- coding: utf-8 -*-
import json

import frappe

MODULE_NAME = "Metabase Integration"
WORKSPACE_NAME = "Metabase Integration"


def after_install():
	"""Ensure module definition and workspace exist so the app appears on the Desk."""
	ensure_module_definition()
	ensure_workspace()


def ensure_module_definition():
	if frappe.db.exists("Module Def", MODULE_NAME):
		return

	module_def = frappe.new_doc("Module Def")
	module_def.module_name = MODULE_NAME
	module_def.app_name = "metabase_integration"
	module_def.save(ignore_permissions=True)


def ensure_workspace():
	if frappe.db.exists("Workspace", WORKSPACE_NAME):
		return

	workspace = frappe.new_doc("Workspace")
	workspace.label = WORKSPACE_NAME
	workspace.title = WORKSPACE_NAME
	workspace.module = MODULE_NAME
	workspace.icon = "octicon octicon-graph"
	workspace.public = 1
	workspace.content = json.dumps(
		[
			{
				"id": "header_metabase",
				"type": "header",
				"data": {
					"text": "<span class=\\\"h4\\\"><b>Metabase Dashboards</b></span>",
					"col": 12,
				},
			},
			{
				"id": "shortcut_metabase_dashboard",
				"type": "shortcut",
				"data": {"shortcut_name": "Metabase Dashboard", "col": 3},
			},
		]
	)

	workspace.append(
		"shortcuts",
		{
			"label": "Metabase Dashboard",
			"type": "Page",
			"link_to": "metabase-dashboard",
			"color": "#FF4136",
			"icon": "octicon octicon-graph",
		},
	)

	workspace.insert(ignore_permissions=True)
