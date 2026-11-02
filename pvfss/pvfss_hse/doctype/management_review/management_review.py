# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from frappe.utils import add_months, getdate

from pvfss.pvfss_hse import kpi


class ManagementReview(Document):
	"""HSE management review (HSE-50)."""


@frappe.whitelist()
def snapshot_kpis(review: str):
	doc = frappe.get_doc("Management Review", review)
	doc.check_permission("write")
	to_date = getdate(doc.kpi_to or doc.review_date)
	from_date = getdate(doc.kpi_from or add_months(to_date, -12))
	doc.kpi_from, doc.kpi_to = from_date, to_date
	doc.kpi_snapshot = json.dumps(kpi.kpis(from_date, to_date), indent=1, default=str)
	doc.save()
	return doc.kpi_snapshot
