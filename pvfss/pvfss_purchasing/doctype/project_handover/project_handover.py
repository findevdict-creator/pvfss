# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, nowdate

from pvfss.gates.base import GateResult
from pvfss.utils import alerts, settings

SUBMITTED = "Pending Acceptance"
RETURNED = "Returned"
ACCEPTED = "Accepted"


class ProjectHandover(Document):
	"""Pre-Bidding to Post-Bidding handover (PRJ-01 to PRJ-04, SCR-PRJ-02)."""

	def onload(self):
		if self.is_new() and self.sales_order and not self.items:
			self.pull_from_sales_order()

	def before_validate(self):
		if self.sales_order and not self.items:
			self.pull_from_sales_order()

	def validate(self):
		self.check_one_per_sales_order()
		self.refresh_supplier_pos()
		self.tick_system_rows()
		self.count_outstanding()
		before = self.get_doc_before_save()
		previous = before.get("workflow_state") if before else None
		if self.get("workflow_state") == SUBMITTED and previous != SUBMITTED:
			self.gate().throw_if_failed()
			self.submitted_on = nowdate()
			for row in self.returns:
				row.resolved = 1
		if self.get("workflow_state") == RETURNED and previous != RETURNED:
			self.record_return()

	def check_one_per_sales_order(self):
		other = frappe.db.get_value(
			"Project Handover",
			{"sales_order": self.sales_order, "docstatus": ["<", 2], "name": ["!=", self.name or ""]},
		)
		if other:
			frappe.throw(_("Customer PO {0} already has handover {1}.").format(self.sales_order, other))

	# ------------------------------------------------------------------ PRJ-01
	@frappe.whitelist()
	def pull_from_sales_order(self):
		so = frappe.get_doc("Sales Order", self.sales_order)
		self.customer = so.customer
		self.customer_name = so.customer_name
		self.po_no = so.po_no
		self.po_date = so.po_date
		self.delivery_date = so.delivery_date
		self.client_project = so.get("pvfss_client_project")
		self.inquiry = so.get("pvfss_inquiry")
		if self.inquiry:
			inquiry = frappe.db.get_value(
				"Opportunity",
				self.inquiry,
				["transaction_date", "pvfss_contractor_ref", "pvfss_owner"],
				as_dict=True,
			)
			self.inquiry_date = inquiry.transaction_date
			self.contractor_ref = inquiry.pvfss_contractor_ref
			self.pre_bidding_owner = self.pre_bidding_owner or inquiry.pvfss_owner
		self.pre_bidding_owner = self.pre_bidding_owner or frappe.session.user
		terms = [
			_("Payment terms: {0}").format(so.payment_terms_template) if so.payment_terms_template else None,
			_("Payment method: {0}").format(so.pvfss_payment_method)
			if so.get("pvfss_payment_method")
			else None,
			_("Retention: {0}% ({1})").format(so.pvfss_retention_pct, so.pvfss_retention_basis or "-")
			if so.get("pvfss_retention_pct")
			else None,
			_("Warranty: {0} months").format(so.pvfss_warranty_months)
			if so.get("pvfss_warranty_months")
			else None,
			_("LDs: {0}").format(so.pvfss_ld_terms) if so.get("pvfss_ld_terms") else None,
		]
		self.commercial_terms = "\n".join(t for t in terms if t)
		self.delivery_requirements = self.delivery_requirements or _("Deliver by {0}{1}").format(
			frappe.utils.formatdate(so.delivery_date), f", {so.incoterm}" if so.incoterm else ""
		)
		lines = [
			f"{r.pvfss_customer_line_ref}: {r.pvfss_inspection_req}"
			for r in so.items
			if r.get("pvfss_inspection_req")
		]
		self.inspection_requirements = self.inspection_requirements or "\n".join(lines)
		if not self.items:
			for row in settings.get_table("handover_item_template"):
				self.append(
					"items",
					{
						"item": row.item,
						"mandatory": cint(row.mandatory),
						"applicable": 1,
						"status": "Outstanding",
						"backed_by_doctype": row.backed_by_doctype,
					},
				)

	def refresh_supplier_pos(self):
		pos = frappe.get_all(
			"Purchase Order",
			filters={"pvfss_sales_order": self.sales_order, "docstatus": ["<", 2]},
			fields=["name", "supplier", "status", "grand_total", "currency"],
			order_by="creation",
		)
		self.set(
			"supplier_pos",
			[
				{
					"purchase_order": p.name,
					"supplier": p.supplier,
					"status": p.status,
					"grand_total": p.grand_total,
					"currency": p.currency,
				}
				for p in pos
			],
		)

	# ------------------------------------------------------------------ PRJ-02
	def system_document(self, doctype):
		"""The document that backs a handover row, if it exists (submitted where submittable)."""
		so = self.sales_order
		quotation = frappe.db.get_value("Sales Order Item", {"parent": so}, "prevdoc_docname")
		if doctype == "Sales Order":
			return so if frappe.db.get_value("Sales Order", so, "docstatus") == 1 else None
		if doctype == "Purchase Order":
			return frappe.db.get_value("Purchase Order", {"pvfss_sales_order": so, "docstatus": 1})
		if doctype == "Opportunity":
			return self.inquiry
		if doctype == "Quotation":
			return quotation
		if doctype in ("Supplier Quotation", "Technical Evaluation", "Costing Sheet") and self.inquiry:
			field = "opportunity" if doctype == "Supplier Quotation" else "inquiry"
			return frappe.db.get_value(doctype, {field: self.inquiry, "docstatus": 1})
		return None

	def tick_system_rows(self):
		for row in self.items:
			if not row.backed_by_doctype or row.status == "N/A":
				continue
			name = self.system_document(row.backed_by_doctype)
			if name:
				row.reference_doctype = row.backed_by_doctype
				row.reference_name = name
				row.status = "Received"
		for row in self.items:
			if not cint(row.applicable):
				row.status = "N/A"
			elif row.status == "Outstanding" and (row.attachment or row.reference_name):
				row.status = "Received"

	def outstanding(self):
		return [
			r for r in self.items if cint(r.mandatory) and cint(r.applicable) and r.status == "Outstanding"
		]

	def count_outstanding(self):
		mandatory = [r for r in self.items if cint(r.mandatory) and cint(r.applicable)]
		self.outstanding_count = len(self.outstanding())
		self.mandatory_progress = f"{len(mandatory) - self.outstanding_count} / {len(mandatory)}"

	# ------------------------------------------------------------------ PRJ-03 / G4
	def gate(self):
		result = GateResult(_("Handover cannot be submitted"), doc=self, gate="G4")
		missing = self.outstanding()
		if missing:
			result.fail(
				_("Outstanding mandatory items: {0}").format("; ".join(r.item for r in missing)),
				rule="PRJ-03",
			)
		for field in ("pre_bidding_owner", "post_bidding_owner", "quality_lead"):
			if not self.get(field):
				result.fail(_("{0} is required.").format(_(self.meta.get_label(field))), rule="PRJ-01")
		return result

	def record_return(self):
		reason = (self.return_reason or "").strip()
		if not reason:
			frappe.throw(_("Enter the return reason."), title=_("Return handover"))
		self.append(
			"returns",
			{"returned_on": nowdate(), "returned_by": frappe.session.user, "reason": reason, "resolved": 0},
		)
		self.return_reason = None
		alerts.send(
			[self.pre_bidding_owner, self.owner],
			_("Handover {0} for {1} returned: {2}").format(self.name, self.sales_order, reason),
			self.doctype,
			self.name,
		)

	def before_submit(self):
		result = self.gate()
		before = self.get_doc_before_save()
		result.check(
			before is not None and before.get("workflow_state") == SUBMITTED,
			_("The handover must be submitted by Pre-Bidding and accepted by the Post-Bidding Manager."),
			rule="PRJ-03",
		)
		result.throw_if_failed()

	# ------------------------------------------------------------------ PRJ-04
	def on_submit(self):
		from pvfss.pvfss_purchasing import project as project_module

		project = project_module.create_from_handover(self)
		self.db_set("project", project.name)
		frappe.msgprint(
			_("Project {0} created").format(frappe.utils.get_link_to_form("Project", project.name)),
			alert=True,
			indicator="green",
		)


@frappe.whitelist()
def make_handover(sales_order):
	frappe.has_permission("Project Handover", "create", throw=True)
	existing = frappe.db.get_value("Project Handover", {"sales_order": sales_order, "docstatus": ["<", 2]})
	if existing:
		return existing
	doc = frappe.new_doc("Project Handover")
	doc.sales_order = sales_order
	doc.pull_from_sales_order()
	doc.post_bidding_owner = doc.post_bidding_owner or frappe.session.user
	doc.quality_lead = doc.quality_lead or frappe.session.user
	doc.insert()
	return doc.name
