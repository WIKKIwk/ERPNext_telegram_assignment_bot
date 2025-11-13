import frappe

from .rfid.setup import deploy_workspace


def after_install():
	_ensure_workspace()


def after_migrate():
	_ensure_workspace()


def _ensure_workspace():
	try:
		deploy_workspace()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "RFID Workspace Deployment Failed")
