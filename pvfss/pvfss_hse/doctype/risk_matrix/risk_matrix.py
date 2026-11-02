# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class RiskMatrix(Document):
	"""Score bands that colour the 5 x 5 matrix (HSE-02, SCR-HSE-02)."""

	def validate(self):
		covered = set()
		for row in sorted(self.bands, key=lambda r: cint(r.from_score)):
			if cint(row.from_score) > cint(row.to_score):
				frappe.throw(_("Row {0}: From score is above To score.").format(row.idx))
			span = set(range(cint(row.from_score), cint(row.to_score) + 1))
			if covered & span:
				frappe.throw(_("Row {0}: the score band overlaps another band.").format(row.idx))
			covered |= span
		missing = sorted(set(range(1, 26)) - covered)
		if missing:
			frappe.throw(_("Scores {0} have no band.").format(", ".join(str(s) for s in missing)))
		frappe.clear_document_cache("Risk Matrix", "Risk Matrix")
