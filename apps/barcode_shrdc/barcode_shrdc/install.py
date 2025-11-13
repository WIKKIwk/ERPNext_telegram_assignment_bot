# -*- coding: utf-8 -*-
import json

import frappe

MODULE_NAME = "Barcode Shrdc"
WORKSPACE_NAME = "Barcode Scanning System"


def after_install():
	ensure_module_definition()
	ensure_workspace()


def ensure_module_definition():
	if frappe.db.exists("Module Def", MODULE_NAME):
		return

	module_def = frappe.new_doc("Module Def")
	module_def.module_name = MODULE_NAME
	module_def.app_name = "barcode_shrdc"
	module_def.save(ignore_permissions=True)


def ensure_workspace():
	if frappe.db.exists("Workspace", WORKSPACE_NAME):
		return

	workspace = frappe.new_doc("Workspace")
	workspace.label = WORKSPACE_NAME
	workspace.title = WORKSPACE_NAME
	workspace.module = MODULE_NAME
	workspace.icon = "fa fa-barcode"
	workspace.public = 1
	workspace.content = json.dumps(
		[
			{
				"id": "header_barcode",
				"type": "header",
				"data": {
					"text": "<span class=\\\"h4\\\"><b>Barcode Tools</b></span>",
					"col": 12,
				},
			},
			{
				"id": "shortcut_barcode_printing",
				"type": "shortcut",
				"data": {"shortcut_name": "Barcode Printing", "col": 3},
			},
			{
				"id": "shortcut_barcode_config",
				"type": "shortcut",
				"data": {"shortcut_name": "Barcode Configuration", "col": 3},
			},
			{
				"id": "shortcut_qr_config",
				"type": "shortcut",
				"data": {"shortcut_name": "QR Code Configuration", "col": 3},
			},
		]
	)

	workspace.append(
		"shortcuts",
		{
			"label": "Barcode Printing",
			"type": "DocType",
			"link_to": "Barcode Printing",
			"color": "#7f8c8d",
			"icon": "fa fa-print",
		},
	)
	workspace.append(
		"shortcuts",
		{
			"label": "Barcode Configuration",
			"type": "DocType",
			"link_to": "Barcode Configuration",
			"color": "#7f8c8d",
			"icon": "fa fa-sliders",
		},
	)
	workspace.append(
		"shortcuts",
		{
			"label": "QR Code Configuration",
			"type": "DocType",
			"link_to": "QR Code Configuration",
			"color": "#7f8c8d",
			"icon": "fa fa-qrcode",
		},
	)

	workspace.insert(ignore_permissions=True)
