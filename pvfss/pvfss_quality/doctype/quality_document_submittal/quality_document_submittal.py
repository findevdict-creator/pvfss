# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff, nowdate

APPROVED = ("Approved", "Approved with comments")


class QualityDocumentSubmittal(Document):
	"""Supplier quality document and its customer approval (QA-01, SCR-QA-02)."""

	def validate(self):
		other = frappe.db.get_value(
			"Quality Document Submittal",
			{
				"supplier_po": self.supplier_po,
				"document_no": self.document_no,
				"revision": self.revision,
				"name": ["!=", self.name or ""],
			},
		)
		if other:
			frappe.throw(
				_("Revision {0} of {1} already exists: {2}.").format(self.revision, self.document_no, other)
			)
		if self.customer_response and self.customer_response != "Pending" and not self.response_date:
			self.response_date = nowdate()
		waiting = (
			self.customer_approval_required
			and self.customer_response == "Pending"
			and self.sent_to_customer_date
		)
		self.days_waiting = date_diff(nowdate(), self.sent_to_customer_date) if waiting else 0


@frappe.whitelist()
def new_revision(submittal: str):
	"""SCR-QA-02 "New revision": a copy with revision + 1 and the customer response reset."""
	doc = frappe.get_doc("Quality Document Submittal", submittal)
	doc.check_permission("read")
	new = frappe.copy_doc(doc)
	latest = frappe.get_all(
		"Quality Document Submittal",
		filters={"supplier_po": doc.supplier_po, "document_no": doc.document_no},
		pluck="revision",
		order_by="revision desc",
		limit=1,
	)
	new.revision = cint(latest[0] if latest else doc.revision) + 1
	for field in ("supplier_submission_date", "sent_to_customer_date", "transmittal_no", "response_date"):
		new.set(field, None)
	new.customer_response = "Pending"
	new.comments = new.comments_file = new.attachment = None
	new.flags.ignore_mandatory = True
	new.insert()
	return new.name


def pending_approvals(supplier_po):
	"""QA-02: customer-approval submittals of a PO whose latest revision is not approved."""
	latest = {}
	for row in frappe.get_all(
		"Quality Document Submittal",
		filters={"supplier_po": supplier_po, "customer_approval_required": 1},
		fields=["name", "document_no", "document_type", "revision", "customer_response"],
		order_by="revision asc",
	):
		latest[row.document_no] = row
	return [r for r in latest.values() if r.customer_response not in APPROVED]


def check_manufacturing_start(doc, method=None):
	"""Expediting Log validate (QA-02): no actual manufacturing start while approvals are pending."""
	from pvfss.utils import settings

	if doc.supply_route == "Ready stock (SMR)":
		return
	before = doc.get_doc_before_save()
	old = {r.name: r.actual_date for r in (before.milestones if before else [])}
	for row in doc.milestones:
		if row.milestone != "Manufacturing start" or not row.actual_date or old.get(row.name):
			continue
		pending = pending_approvals(doc.purchase_order)
		if not pending:
			continue
		message = _("Manufacturing start cannot be recorded: customer approval pending for {0}.").format(
			", ".join(
				f"{r.document_type} {r.document_no} rev {r.revision} ({_(r.customer_response)})"
				for r in pending
			)
		)
		if settings.get_value("qa02_mode") == "Warn":
			frappe.msgprint(message, indicator="orange", alert=True)
		else:
			frappe.throw(message, title=_("QA-02"))
