# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ProjectDocumentType(Document):
	"""Document type with its mandatory metadata (DMS-03)."""

	def validate(self):
		for row in self.metadata_fields:
			if row.fieldtype == "Link" and not (row.options and frappe.db.exists("DocType", row.options)):
				frappe.throw(_("Row {0}: a Link field needs a DocType in Options.").format(row.idx))
