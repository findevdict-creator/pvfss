"""Sales Invoice, Purchase Invoice and Payment Entry rules (FIN-10, FIN-11, FIN-20, FIN-31, FIN-50, FIN-51, FIN-60)."""

import frappe
from frappe import _
from frappe.utils import flt

from pvfss.gates.base import GateResult
from pvfss.pvfss_finance import retention, vc
from pvfss.utils import settings
from pvfss.utils.importing import is_import

QTY_TOLERANCE = 0.001


# ----------------------------------------------------------------------------- Sales Invoice
def sales_invoice_validate(doc, method=None):
	if doc.is_return or doc.get("is_opening") == "Yes":
		return
	check_source(doc)
	so = next((r.sales_order for r in doc.items if r.get("sales_order")), None)
	if so:
		po_no, project = frappe.db.get_value("Sales Order", so, ["po_no", "project"])
		doc.pvfss_customer_po_no = doc.get("po_no") or po_no
		if not doc.get("project") and project:
			doc.project = project
	doc.pvfss_supply_date = doc.get("pvfss_supply_date") or doc.posting_date
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	foreign = doc.currency != company_currency
	doc.pvfss_aed_taxable = doc.base_net_total if foreign else 0
	doc.pvfss_aed_vat = doc.base_total_taxes_and_charges if foreign else 0
	retention.preview_sales(doc)


def check_source(doc):
	"""FIN-10: every line comes from a Delivery Note, or from a Customer PO approved for advance billing."""
	if is_import(doc):
		return
	for row in doc.items:
		if row.get("delivery_note"):
			continue
		if row.get("sales_order") and frappe.db.get_value(
			"Sales Order", row.sales_order, "pvfss_advance_billing_allowed"
		):
			continue
		frappe.throw(
			_(
				"Sales Invoices are created from Delivery Notes. Advance or milestone billing needs Finance Manager approval on the Customer PO."
			),
			title=_("Invoice source"),
		)


def sales_invoice_on_submit(doc, method=None):
	retention.hold_sales(doc)
	vc.recognise(doc)


def sales_invoice_before_cancel(doc, method=None):
	retention.undo(doc)
	vc.reverse(doc)


# ----------------------------------------------------------------------------- Purchase Invoice
def purchase_invoice_validate(doc, method=None):
	if doc.is_return or doc.get("is_opening") == "Yes":
		return
	if not doc.bill_no or not doc.bill_date:
		frappe.throw(_("Enter the supplier invoice no and date (FIN-20)."))
	duplicate = frappe.db.get_value(
		"Purchase Invoice",
		{
			"supplier": doc.supplier,
			"bill_no": doc.bill_no,
			"docstatus": ["<", 2],
			"name": ["!=", doc.name or ""],
		},
		"name",
	)
	if duplicate:
		frappe.throw(
			_("Supplier invoice {0} from {1} is already entered in {2}.").format(
				doc.bill_no, doc.supplier, duplicate
			)
		)
	three_way_match(doc).throw_if_failed()
	retention.preview_purchase(doc)


def _billed_elsewhere(pr_detail, exclude):
	rows = frappe.get_all(
		"Purchase Invoice Item",
		filters={"pr_detail": pr_detail, "docstatus": 1, "parent": ["!=", exclude or ""]},
		pluck="qty",
	)
	return sum(flt(q) for q in rows)


def three_way_match(doc):
	"""FIN-20: goods lines come from a receipt; rate equals the PO rate and qty stays within the receipt."""
	result = GateResult(_("3-way match failed"), doc=doc)
	failed = 0
	for row in doc.items:
		line = row.get("pvfss_customer_line_ref") or row.idx
		if not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			row.pvfss_match = ""
			continue
		issues = []
		if not row.get("pr_detail"):
			result.fail(
				_("Line {0}: goods are invoiced from a Purchase Receipt.").format(line), rule="FIN-20"
			)
			issues.append(_("no receipt"))
		else:
			received = flt(frappe.db.get_value("Purchase Receipt Item", row.pr_detail, "qty"))
			available = received - _billed_elsewhere(row.pr_detail, doc.name)
			if flt(row.qty) > available + QTY_TOLERANCE:
				result.fail(
					_("Line {0}: invoiced qty {1:g} exceeds received and unbilled qty {2:g}.").format(
						line, flt(row.qty), available
					),
					rule="FIN-20",
				)
				issues.append(_("qty"))
		if row.get("po_detail"):
			po_rate = flt(frappe.db.get_value("Purchase Order Item", row.po_detail, "rate"))
			if abs(flt(row.rate) - po_rate) > 0.0001:
				result.fail(
					_("Line {0}: invoice rate {1} differs from PO rate {2}.").format(
						line,
						frappe.format_value(row.rate, {"fieldtype": "Currency"}),
						frappe.format_value(po_rate, {"fieldtype": "Currency"}),
					),
					rule="FIN-20",
				)
				issues.append(_("rate"))
		row.pvfss_match = ("✗ " + ", ".join(issues)) if issues else "✓"
		failed += bool(issues)
	doc.pvfss_match_status = _("{0} lines failed").format(failed) if failed else _("Matched")
	return result


def purchase_invoice_on_submit(doc, method=None):
	retention.hold_purchase(doc)


def purchase_invoice_before_cancel(doc, method=None):
	retention.undo(doc)


# ----------------------------------------------------------------------------- Payment Entry
def payment_entry_validate(doc, method=None):
	"""FIN-31: supplier payments above the threshold need the Director (workflow condition)."""
	threshold = settings.get_float("supplier_payment_approval_threshold")
	doc.pvfss_needs_director = int(
		doc.payment_type == "Pay" and bool(threshold) and flt(doc.base_paid_amount) > threshold
	)
