# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ICVSettings(Document):
	"""ICV component weightages (ICV-01)."""

	def validate(self):
		total = sum(flt(r.weight_pct) for r in self.components)
		if abs(total - 100) > 0.001:
			frappe.throw(_("Component weights must total 100% (now {0}%).").format(flt(total, 2)))
