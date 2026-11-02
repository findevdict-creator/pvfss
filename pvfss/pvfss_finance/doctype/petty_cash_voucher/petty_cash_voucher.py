# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from pvfss.pvfss_finance import accounts
from pvfss.utils import settings


class PettyCashVoucher(Document):
	"""Petty cash expense posted on submit (FIN-65, SCR-FIN-15)."""

	def validate(self):
		if not self.vat_input:
			self.vat_amount = 0
		if flt(self.vat_amount) >= flt(self.amount) and flt(self.amount):
			frappe.throw(_("VAT cannot be more than the amount."))
		threshold = settings.get_float("petty_cash_approval_threshold")
		self.approval_required = int(bool(threshold) and flt(self.amount) > threshold)
		if not self.approval_required:
			self.approved_by = None

	def before_submit(self):
		if self.approval_required and not self.approved_by:
			frappe.throw(
				_("Vouchers above {0} need Finance Manager approval.").format(
					frappe.format_value(
						settings.get_float("petty_cash_approval_threshold"), {"fieldtype": "Currency"}
					)
				)
			)

	def on_submit(self):
		net = flt(self.amount) - flt(self.vat_amount)
		rows = [
			{"account": self.expense_account, "debit": net, "project": self.project},
			{"account": accounts.get(self.company, "vat_input"), "debit": flt(self.vat_amount)},
			{"account": self.cash_account, "credit": flt(self.amount)},
		]
		je = accounts.post(
			self.company,
			rows,
			_("Petty cash {0}: {1}").format(self.name, self.description),
			self.posting_date,
			self.project,
		)
		self.db_set("journal_entry", je)

	def on_cancel(self):
		accounts.cancel(self.journal_entry)


@frappe.whitelist()
def approve(voucher: str):
	accounts.require_finance_manager()
	doc = frappe.get_doc("Petty Cash Voucher", voucher)
	doc.check_permission("write")
	doc.approved_by = frappe.session.user
	doc.save()
	return doc.approved_by
