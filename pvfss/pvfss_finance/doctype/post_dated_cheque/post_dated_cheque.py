# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

from pvfss.pvfss_finance import accounts
from pvfss.utils import alerts

RECEIVED, ISSUED = "Received", "Issued"


class PostDatedCheque(Document):
	"""Post-dated cheque received from a customer or issued to a supplier (FIN-45, SCR-FIN-10)."""

	def validate(self):
		self.party_type = "Customer" if self.direction == RECEIVED else "Supplier"
		if self.docstatus == 0:
			self.status = "Draft"
		company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		if self.currency == company_currency:
			self.exchange_rate = 1
		invoice_type = "Sales Invoice" if self.direction == RECEIVED else "Purchase Invoice"
		party_field = "customer" if self.direction == RECEIVED else "supplier"
		for row in self.invoices:
			if row.invoice_type != invoice_type:
				frappe.throw(_("Row {0}: a {1} cheque links to a {2}.").format(row.idx, _(self.direction), _(invoice_type)))
			if frappe.db.get_value(invoice_type, row.invoice, party_field) != self.party:
				frappe.throw(_("Row {0}: {1} is not for {2}.").format(row.idx, row.invoice, self.party))
		if sum(flt(r.allocated_amount) for r in self.invoices) > flt(self.amount) + 0.005:
			frappe.throw(_("Allocated amounts exceed the cheque amount."))

	# ------------------------------------------------------------------ postings
	def _base(self, amount=None):
		return flt(flt(self.amount if amount is None else amount) * flt(self.exchange_rate or 1), 2)

	def _party(self):
		return {"party_type": self.party_type, "party": self.party}

	def _main_account(self):
		return accounts.party_account(self.party_type, self.party, self.company)

	def _hold_rows(self):
		"""Received: Debtors -> PDC Receivable. Issued: Creditors -> PDC Payable (mirror)."""
		main = self._main_account()
		side = "credit" if self.direction == RECEIVED else "debit"
		rows, allocated = [], 0.0
		for inv in self.invoices:
			allocated += flt(inv.allocated_amount)
			rows.append(
				{
					"account": main,
					side: self._base(inv.allocated_amount),
					"exchange_rate": self.exchange_rate,
					"reference_type": inv.invoice_type,
					"reference_name": inv.invoice,
					**self._party(),
				}
			)
		if flt(self.amount) - allocated > 0.005:
			rows.append(
				{"account": main, side: self._base(flt(self.amount) - allocated), "exchange_rate": self.exchange_rate, **self._party()}
			)
		pdc_key = "pdc_receivable" if self.direction == RECEIVED else "pdc_payable"
		other = "debit" if side == "credit" else "credit"
		rows.append({"account": accounts.get(self.company, pdc_key), other: self._base(), **self._party()})
		return rows

	def on_submit(self):
		self.db_set("status", "In hand" if self.direction == RECEIVED else "Issued")
		je = accounts.post(
			self.company, self._hold_rows(), _("PDC {0} cheque {1}").format(self.name, self.cheque_no), posting_date=nowdate()
		)
		self.db_set("hold_journal_entry", je)

	def on_cancel(self):
		if self.status not in ("In hand", "Issued"):
			frappe.throw(_("A cheque that is {0} cannot be cancelled.").format(_(self.status)))
		accounts.cancel(self.hold_journal_entry)
		self.db_set("status", "Cancelled")

	def pdc_account(self):
		return accounts.get(self.company, "pdc_receivable" if self.direction == RECEIVED else "pdc_payable")


def _pdc(name, expected):
	doc = frappe.get_doc("Post-Dated Cheque", name)
	doc.check_permission("submit")
	if doc.status not in expected:
		frappe.throw(_("Cheque {0} is {1}.").format(doc.cheque_no, _(doc.status)))
	return doc


def _set(doc, **values):
	doc.db_set(values)
	doc.add_comment("Info", _("Status: {0}").format(_(doc.status)))


@frappe.whitelist()
def deposit(pdc: str, bank_account: str, deposit_date: str | None = None):
	doc = _pdc(pdc, ("In hand",))
	_set(doc, status="Deposited", bank_account=bank_account, deposit_date=getdate(deposit_date or nowdate()))
	return doc.status


@frappe.whitelist()
def present(pdc: str, presented_date: str | None = None):
	doc = _pdc(pdc, (ISSUED,))
	_set(doc, status="Presented", deposit_date=getdate(presented_date or nowdate()))
	return doc.status


@frappe.whitelist()
def clear(pdc: str, cleared_date: str | None = None, bank_account: str | None = None):
	"""Received: PDC Receivable -> Bank. Issued: Bank -> PDC Payable."""
	doc = _pdc(pdc, ("Deposited", ISSUED, "Presented"))
	bank = bank_account or doc.bank_account
	if not bank:
		frappe.throw(_("Select the bank account."))
	if doc.direction == RECEIVED:
		rows = [
			{"account": bank, "debit": doc._base()},
			{"account": doc.pdc_account(), "credit": doc._base(), **doc._party()},
		]
	else:
		rows = [
			{"account": doc.pdc_account(), "debit": doc._base(), **doc._party()},
			{"account": bank, "credit": doc._base()},
		]
	date = getdate(cleared_date or nowdate())
	je = accounts.post(doc.company, rows, _("PDC {0} cleared").format(doc.name), posting_date=date)
	_set(doc, status="Cleared", cleared_date=date, bank_account=bank, clear_journal_entry=je)
	return je


def _reverse(doc, status, remark):
	"""Undo the PDC posting: the hold rows with debit and credit swapped, so the invoices are open again."""
	rows = []
	for row in doc._hold_rows():
		swapped = dict(row)
		swapped["debit"], swapped["credit"] = row.get("credit", 0), row.get("debit", 0)
		rows.append(swapped)
	je = accounts.post(doc.company, rows, remark)
	_set(doc, status=status, reversal_journal_entry=je)
	return je


@frappe.whitelist()
def bounce(pdc: str, remarks: str | None = None):
	"""Bounced: back to Debtors and Finance is alerted."""
	doc = _pdc(pdc, ("Deposited", "In hand"))
	je = _reverse(doc, "Bounced", _("PDC {0} bounced").format(doc.name))
	if remarks:
		doc.db_set("remarks", remarks)
	alerts.send(
		alerts.users_with_role("Finance User", "Finance Manager"),
		_("Cheque {0} from {1} bounced ({2} {3}).").format(doc.cheque_no, doc.party, doc.currency, doc.amount),
		"Post-Dated Cheque",
		doc.name,
	)
	return je


@frappe.whitelist()
def stop(pdc: str):
	doc = _pdc(pdc, (ISSUED, "Presented"))
	return _reverse(doc, "Stopped", _("PDC {0} stopped").format(doc.name))


@frappe.whitelist()
def replace(pdc: str):
	"""Bounced cheque replaced by a new draft PDC linked both ways."""
	doc = _pdc(pdc, ("Bounced",))
	new = frappe.copy_doc(doc)
	new.update({"cheque_no": "", "cheque_date": None, "replaces": doc.name, "remarks": ""})
	new.flags.ignore_mandatory = True
	new.insert()
	_set(doc, status="Replaced", replacement_pdc=new.name)
	return new.name
