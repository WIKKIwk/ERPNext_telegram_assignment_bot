import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class RFIDTagEvent(Document):
	"""Simple log of tag reads coming from external RFID readers."""

	def autoname(self):
		# Respect an explicit name if it was already supplied.
		if self.name:
			return

		if not self.read_time:
			self.read_time = now_datetime()

		key = f"{(self.rfid or '').upper()}-{self.read_time.isoformat()}"
		self.name = frappe.generate_hash(key, 16)
