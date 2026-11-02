"""Submittal Register (DMS-06, SCR-DMS-06): customer submittals per project with overdue responses."""

import frappe
from frappe import _
from frappe.utils import date_diff, nowdate

from pvfss.utils import settings


def execute(filters=None):
	filters = frappe._dict(filters or {})
	limit = settings.get_int("submittal_overdue_days", 14)
	conditions = {}
	if filters.project:
		conditions["project"] = filters.project
	if filters.document_type:
		conditions["document_type"] = filters.document_type
	docs = {
		d.name: d
		for d in frappe.get_all(
			"Project Document",
			filters=conditions,
			fields=["name", "document_no", "title", "project", "document_type"],
		)
	}
	data = []
	for row in frappe.get_all(
		"Project Document Submittal",
		filters={"parent": ["in", list(docs) or [""]], "parenttype": "Project Document"},
		fields=["parent", "transmittal_no", "revision", "submitted_date", "response", "response_date"],
		order_by="submitted_date asc",
	):
		pending = row.response in (None, "", "Pending")
		waiting = date_diff(row.response_date if not pending else nowdate(), row.submitted_date)
		overdue = pending and waiting > limit
		if filters.response and row.response != filters.response:
			continue
		if filters.overdue_only and not overdue:
			continue
		doc = docs[row.parent]
		data.append(
			{
				"document": row.parent,
				"document_no": doc.document_no,
				"title": doc.title,
				"project": doc.project,
				"revision": row.revision,
				"transmittal_no": row.transmittal_no,
				"submitted_date": row.submitted_date,
				"response": row.response,
				"response_date": row.response_date,
				"days_waiting": waiting,
				"overdue": int(overdue),
			}
		)
	columns = [
		{
			"fieldname": "document",
			"label": _("Document"),
			"fieldtype": "Link",
			"options": "Project Document",
			"width": 130,
		},
		{"fieldname": "document_no", "label": _("Document No"), "fieldtype": "Data", "width": 140},
		{"fieldname": "title", "label": _("Title"), "fieldtype": "Data", "width": 200},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 120,
		},
		{"fieldname": "revision", "label": _("Rev"), "fieldtype": "Data", "width": 50},
		{"fieldname": "transmittal_no", "label": _("Transmittal No"), "fieldtype": "Data", "width": 120},
		{"fieldname": "submitted_date", "label": _("Submitted"), "fieldtype": "Date", "width": 95},
		{"fieldname": "response", "label": _("Response"), "fieldtype": "Data", "width": 150},
		{"fieldname": "response_date", "label": _("Response Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_waiting", "label": _("Days Waiting"), "fieldtype": "Int", "width": 90},
	]
	return columns, data
