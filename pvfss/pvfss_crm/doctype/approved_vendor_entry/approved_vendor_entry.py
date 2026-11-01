# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class ApprovedVendorEntry(Document):
	"""A supplier or mill on a client project's AVL (SUP-03, SCR-SUP-03)."""

	def validate(self):
		if not (self.supplier or (self.manufacturer_name or "").strip()):
			frappe.throw(_("Enter a Supplier or a Manufacturer Name."))
		if self.valid_from and self.valid_to and getdate(self.valid_to) < getdate(self.valid_from):
			frappe.throw(_("Valid To cannot be before Valid From."))
		duplicate = frappe.db.exists(
			"Approved Vendor Entry",
			{
				"client_project": self.client_project,
				"product_category": self.product_category,
				"supplier": self.supplier or ["is", "not set"],
				"manufacturer_name": self.manufacturer_name or ["is", "not set"],
				"avl_reference": self.avl_reference,
				"name": ["!=", self.name or ""],
			},
		)
		if duplicate:
			frappe.throw(_("This AVL entry already exists: {0}").format(duplicate))
