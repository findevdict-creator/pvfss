# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from pvfss.pvfss_hse.doctype.capa.capa import open_capas


class HSEAudit(Document):
	"""HSE audit or site inspection with findings and CAPAs (HSE-40)."""

	def validate(self):
		if self.status in ("Done", "Closed") and not self.actual_date:
			self.actual_date = getdate(nowdate())
		if self.status == "Closed":
			missing = [str(r.idx) for r in self.findings if r.severity != "Observation" and not r.capa]
			if missing:
				frappe.throw(_("Findings {0} need a CAPA.").format(", ".join(missing)))
			pending = open_capas(r.capa for r in self.findings if r.capa)
			if pending:
				frappe.throw(_("CAPAs still open: {0}.").format(", ".join(pending)))


@frappe.whitelist()
def get_events(start: str, end: str, filters: str | list | None = None):
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or [])
	return frappe.get_list(
		"HSE Audit",
		filters=[*filters, ["planned_date", "between", [start, end]]],
		fields=["name", "scope as title", "planned_date", "status", "audit_type"],
	)
