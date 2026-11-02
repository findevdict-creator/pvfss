# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate, nowdate

from pvfss.pvfss_finance import accounts

FINAL = ("Paid", "Expired", "Cancelled")


class LetterofCredit(Document):
	"""Import or export letter of credit (FIN-40 to FIN-42, SCR-FIN-07)."""

	def validate(self):
		self.party_type = "Supplier" if self.direction == "Import" else "Customer"
		if self.docstatus == 0:
			self.status = "Draft"
		if getdate(self.expiry_date) < getdate(self.issue_date):
			frappe.throw(_("Expiry date is before the issue date."))
		if self.latest_shipment_date and getdate(self.latest_shipment_date) > getdate(self.expiry_date):
			frappe.throw(_("Latest shipment date is after the expiry date."))
		if self.transferable == "Transferable" and flt(self.transferred_amount) > flt(self.amount):
			frappe.throw(_("Transferred amount exceeds the LC amount."))
		self.set_presentation()

	def before_update_after_submit(self):
		self.set_presentation()

	def set_presentation(self):
		"""Presentation deadline = shipment date (DN B/L date) + presentation period."""
		if self.delivery_note:
			bl_date, posting = frappe.db.get_value(
				"Delivery Note", self.delivery_note, ["pvfss_bl_date", "posting_date"]
			)
			self.shipment_date = bl_date or posting
		self.presentation_deadline = (
			add_days(self.shipment_date, self.presentation_days or 0) if self.shipment_date else None
		)

	def on_submit(self):
		self.db_set("status", "Issued")

	def on_cancel(self):
		self.db_set("status", "Cancelled")


def _lc(name):
	doc = frappe.get_doc("Letter of Credit", name)
	doc.check_permission("submit")
	if doc.docstatus != 1:
		frappe.throw(_("Submit the LC first."))
	if doc.status in FINAL:
		frappe.throw(_("LC {0} is {1}.").format(doc.lc_no, _(doc.status)))
	return doc


@frappe.whitelist()
def amend(lc: str, change: str, amount_change: float = 0, new_expiry_date: str | None = None):
	doc = _lc(lc)
	doc.append(
		"amendments",
		{
			"amendment_date": nowdate(),
			"change": change,
			"amount_change": flt(amount_change),
			"new_expiry_date": new_expiry_date,
			"currency": doc.currency,
		},
	)
	doc.amount = flt(doc.amount) + flt(amount_change)
	if new_expiry_date:
		doc.expiry_date = new_expiry_date
		doc.expiry_alerts_sent = ""
	doc.status = "Amended"
	doc.save()
	return doc.status


@frappe.whitelist()
def presentation_checklist(lc: str):
	"""FIN-42 / SCR-FIN-08: LC required documents against the DN dispatch documents."""
	doc = frappe.get_doc("Letter of Credit", lc)
	doc.check_permission("read")
	on_dn = {}
	if doc.delivery_note:
		for row in frappe.get_all(
			"Dispatch Document",
			filters={"parent": doc.delivery_note, "parenttype": "Delivery Note"},
			fields=["document", "status"],
		):
			on_dn[row.document.strip().lower()] = row.status
	out = []
	for row in doc.documents:
		status = on_dn.get(row.document.strip().lower())
		out.append(
			{
				"document": row.document,
				"available": status == "Ready",
				"dn_status": status or _("Not on DN"),
				"discrepancy": row.discrepancy,
			}
		)
	return out


@frappe.whitelist()
def mark_presented(lc: str):
	doc = _lc(lc)
	ready = {r["document"]: r["available"] for r in presentation_checklist(lc)}
	for row in doc.documents:
		row.available_on_dn = int(bool(ready.get(row.document)))
	doc.status = "Documents presented"
	doc.presented_on = nowdate()
	doc.save()
	return doc.status


@frappe.whitelist()
def set_status(lc: str, status: str):
	allowed = {
		"Accepted": ("Documents presented",),
		"Paid": ("Accepted", "Documents presented"),
		"Expired": ("Issued", "Amended", "Documents presented"),
	}
	doc = _lc(lc)
	if status not in allowed or doc.status not in allowed[status]:
		frappe.throw(_("An LC that is {0} cannot be set to {1}.").format(_(doc.status), _(status)))
	doc.status = status
	doc.save()
	return doc.status


@frappe.whitelist()
def post_charges(lc: str):
	"""Margin and bank charges: LC Margin / LC Charges -> bank."""
	doc = _lc(lc)
	if doc.charges_journal_entry:
		frappe.throw(_("Margin and charges are already posted in {0}.").format(doc.charges_journal_entry))
	total = flt(doc.margin_amount) + flt(doc.charges_amount)
	if not total or not doc.bank_account:
		frappe.throw(_("Enter the margin or charges amount and the bank account."))
	je = accounts.post(
		doc.company,
		[
			{"account": accounts.get(doc.company, "lc_margin"), "debit": flt(doc.margin_amount)},
			{"account": accounts.get(doc.company, "lc_charges"), "debit": flt(doc.charges_amount)},
			{"account": doc.bank_account, "credit": total},
		],
		_("LC {0} margin and charges").format(doc.lc_no),
	)
	doc.db_set("charges_journal_entry", je)
	return je
