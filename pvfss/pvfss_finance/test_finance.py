"""Module 11 tests (FIN-10 to FIN-71). Names carry the requirement ID (GEN-07)."""

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice as so_invoice
from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from pvfss.pvfss_finance import accounts, alerts, vc
from pvfss.pvfss_finance.doctype.letter_of_credit import letter_of_credit as lc_module
from pvfss.pvfss_finance.doctype.petty_cash_voucher import petty_cash_voucher as pcv_module
from pvfss.pvfss_finance.doctype.post_dated_cheque import post_dated_cheque as pdc_module
from pvfss.pvfss_finance.doctype.retention import retention as ret_module
from pvfss.pvfss_finance.report.cash_flow_forecast import cash_flow_forecast
from pvfss.pvfss_finance.report.invoice_and_payment_status import invoice_and_payment_status
from pvfss.pvfss_finance.report.payment_status_by_project import payment_status_by_project
from pvfss.pvfss_finance.report.pdc_maturity_register import pdc_maturity_register
from pvfss.pvfss_finance.report.retention_register import retention_register
from pvfss.pvfss_finance.report.revenue_and_vc_by_project import revenue_and_vc_by_project
from pvfss.tests import factories as f
from pvfss.utils import settings

SERVICE = "_PVFSS FIN Service"
GOODS = "_PVFSS FIN Flange"


def service_item():
	return f.make_item(SERVICE, is_stock_item=0, item_group="Testing").name


def goods_item():
	return f.make_item(GOODS, pvfss_heat_traceable=0, pvfss_irn_required=0).name


def balance(account, party=None):
	filters = {"account": account, "is_cancelled": 0}
	if party:
		filters["party"] = party
	rows = frappe.get_all("GL Entry", filters=filters, fields=["debit", "credit"])
	return flt(sum(flt(r.debit) - flt(r.credit) for r in rows), 2)


def bank_account():
	name = frappe.db.get_value("Account", {"company": f.TEST_COMPANY, "account_type": "Bank", "is_group": 0}, "name")
	if name:
		return name
	parent = frappe.db.get_value(
		"Account", {"company": f.TEST_COMPANY, "account_type": "Bank", "is_group": 1}, "name"
	)
	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"company": f.TEST_COMPANY,
				"account_name": "_PVFSS Test Bank",
				"parent_account": parent,
				"account_type": "Bank",
			}
		)
		.insert()
		.name
	)


def make_so(qty=10, rate=1000, **kw):
	kw.setdefault("po_no", "CPO-FIN-" + frappe.generate_hash(length=6))
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": f.make_customer().name,
			"company": f.TEST_COMPANY,
			"transaction_date": nowdate(),
			"delivery_date": f.delivery_date(),
			"selling_price_list": f.price_list(),
			"currency": "AED",
			"items": [{"item_code": service_item(), "qty": qty, "rate": rate, "delivery_date": f.delivery_date()}],
			**kw,
		}
	)
	f.customer_po(so).insert()
	return f.submit_sales_order(so)


def invoice_from_dn(so, qty=None):
	dn = make_delivery_note(so.name)
	if qty:
		dn.items[0].qty = qty
	dn.insert()
	dn.submit()
	si = make_sales_invoice(dn.name)
	si.insert()
	si.submit()
	return si


def make_po(rate=100, qty=10, **kw):
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": f.make_supplier("_PVFSS FIN Supplier").name,
			"company": f.TEST_COMPANY,
			"transaction_date": nowdate(),
			"schedule_date": add_days(nowdate(), 10),
			"items": [
				{
					"item_code": goods_item(),
					"qty": qty,
					"rate": rate,
					"schedule_date": add_days(nowdate(), 10),
					"warehouse": f.warehouse(),
				}
			],
			**kw,
		}
	).insert()
	return f.submit_purchase_order(po)


def received_invoice(po, bill_no="SUP-INV-1"):
	pr = make_purchase_receipt(po.name)
	for row in pr.items:
		row.warehouse = f.warehouse()
	pr.insert()
	pr.submit()
	pi = make_purchase_invoice(pr.name)
	pi.bill_no, pi.bill_date = bill_no, nowdate()
	return pi


class TestFinance(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		settings.clear_cache()

	# ------------------------------------------------------------------ FIN-10
	def test_fin10_invoice_from_dn_or_approved_advance_billing(self):
		so = make_so()
		si = so_invoice(so.name)
		with self.assertRaises(frappe.ValidationError) as ctx:
			si.insert()
		self.assertIn("Sales Invoices are created from Delivery Notes", str(ctx.exception))
		frappe.db.set_value("Sales Order", so.name, "pvfss_advance_billing_allowed", 1)
		so_invoice(so.name).insert()  # advance billing approved by Finance

		so = make_so()
		si = invoice_from_dn(so)
		self.assertEqual(si.pvfss_customer_po_no, so.po_no)

	# ------------------------------------------------------------------ FIN-50 / FIN-52
	def test_fin50_retention_moves_to_retention_receivable_and_releases(self):
		so = make_so(pvfss_retention_pct=10, pvfss_retention_basis="Per invoice", pvfss_warranty_months=12)
		si = invoice_from_dn(so)
		si.reload()
		self.assertEqual(flt(si.pvfss_retention_amount), 1000)
		self.assertEqual(flt(si.outstanding_amount), 9000)
		account = accounts.get(f.TEST_COMPANY, "retention_receivable")
		self.assertEqual(balance(account, si.customer), 1000)
		ret = frappe.get_doc("Retention", si.pvfss_retention)
		self.assertEqual((ret.status, ret.release_due_date), ("Held", frappe.utils.getdate(frappe.utils.add_months(si.posting_date, 12))))

		frappe.db.set_single_value("PVFSS Settings", "retention_release_alert_days", 400)
		settings.clear_cache()
		self.assertGreaterEqual(alerts.retention_alerts(), 1)
		self.assertTrue(frappe.db.get_value("Retention", ret.name, "alerted_on"))

		ret_module.release(ret.name)
		self.assertEqual(balance(account, si.customer), 0)
		self.assertEqual(frappe.db.get_value("Retention", ret.name, "status"), "Released")
		_cols, rows = retention_register.execute({"party": si.customer})
		self.assertEqual(rows[0]["status"], "Released")

	# ------------------------------------------------------------------ FIN-20 / FIN-51
	def test_fin20_three_way_match_blocks_price_difference(self):
		po = make_po(pvfss_supplier_retention_pct=5)
		pi = received_invoice(po)
		pi.items[0].rate = 110
		self.assertRaises(frappe.ValidationError, pi.insert)
		pi.items[0].rate = 100
		pi.insert()
		self.assertEqual((pi.items[0].pvfss_match, pi.pvfss_match_status), ("✓", "Matched"))
		pi.submit()
		pi.reload()
		self.assertEqual(flt(pi.pvfss_retention_amount), 50)
		self.assertEqual(balance(accounts.get(f.TEST_COMPANY, "retention_payable"), pi.supplier), -50)

		other = received_invoice(make_po(), bill_no="")
		self.assertRaises(frappe.ValidationError, other.insert)  # supplier invoice no is mandatory
		other.bill_no = pi.bill_no
		self.assertRaises(frappe.ValidationError, other.insert)  # duplicate supplier invoice no

	# ------------------------------------------------------------------ FIN-31
	def test_fin31_supplier_payment_above_threshold_needs_director(self):
		frappe.db.set_single_value("PVFSS Settings", "supplier_payment_approval_threshold", 500)
		settings.clear_cache()
		po = make_po()
		pi = received_invoice(po, bill_no="SUP-INV-31")
		pi.insert()
		pi.submit()
		pe = get_payment_entry("Purchase Invoice", pi.name, bank_account=bank_account())
		pe.reference_no, pe.reference_date = "TT-1", nowdate()
		pe.insert()
		self.assertTrue(pe.pvfss_needs_director)
		pe = apply_workflow(pe.as_dict(), "Send for Approval")
		pe = apply_workflow(pe.as_dict(), "Approve")
		self.assertEqual((pe.workflow_state, pe.docstatus), ("Pending Director", 0))
		pe = apply_workflow(pe.as_dict(), "Approve")
		self.assertEqual(pe.docstatus, 1)

	# ------------------------------------------------------------------ FIN-45
	def test_fin45_pdc_received_cleared_and_bounced(self):
		si = invoice_from_dn(make_so())
		pdc_account = accounts.get(f.TEST_COMPANY, "pdc_receivable")

		def pdc(no):
			return frappe.get_doc(
				{
					"doctype": "Post-Dated Cheque",
					"direction": "Received",
					"company": f.TEST_COMPANY,
					"party_type": "Customer",
					"party": si.customer,
					"cheque_no": no,
					"bank": "ENBD",
					"cheque_date": add_days(nowdate(), 2),
					"currency": "AED",
					"amount": 4000,
					"invoices": [{"invoice_type": "Sales Invoice", "invoice": si.name, "allocated_amount": 4000}],
				}
			).insert()

		first = pdc("100001")
		first.submit()
		self.assertEqual(frappe.db.get_value("Post-Dated Cheque", first.name, "status"), "In hand")
		self.assertEqual(balance(pdc_account, si.customer), 4000)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount")), 6000)
		self.assertEqual(alerts.pdc_alerts(), 1)

		pdc_module.deposit(first.name, bank_account())
		pdc_module.clear(first.name)
		self.assertEqual(balance(pdc_account, si.customer), 0)
		self.assertEqual(balance(bank_account()), 4000)

		second = pdc("100002")
		second.submit()
		pdc_module.deposit(second.name, bank_account())
		pdc_module.bounce(second.name, "Insufficient funds")
		self.assertEqual(balance(pdc_account, si.customer), 0)
		self.assertEqual(frappe.db.get_value("Post-Dated Cheque", second.name, "status"), "Bounced")
		replacement = pdc_module.replace(second.name)
		self.assertEqual(frappe.db.get_value("Post-Dated Cheque", replacement, "replaces"), second.name)

		_cols, rows = pdc_maturity_register.execute({"direction": "Received"})
		self.assertIn(first.name, [r.get("pdc") for r in rows])

	# ------------------------------------------------------------------ FIN-40 / FIN-41
	def test_fin41_lc_expiry_alerts_at_30_15_7(self):
		lc = frappe.get_doc(
			{
				"doctype": "Letter of Credit",
				"direction": "Export",
				"lc_no": "LC-T-1",
				"company": f.TEST_COMPANY,
				"party_type": "Customer",
				"party": f.make_customer().name,
				"issuing_bank": "Bank A",
				"applicant": "Customer",
				"beneficiary": "PVFSS",
				"currency": "AED",
				"amount": 50000,
				"issue_date": nowdate(),
				"expiry_date": add_days(nowdate(), 20),
				"documents": [{"document": "Commercial Invoice", "originals": 3}],
			}
		).insert()
		lc.submit()
		self.assertEqual(alerts.lc_alerts(), 1)  # within 30 days
		self.assertEqual(alerts.lc_alerts(), 0)  # once per level
		lc_module.amend(lc.name, "Shorter expiry", 0, add_days(nowdate(), 6))
		self.assertEqual(alerts.lc_alerts(), 1)  # 7-day level
		lc = frappe.get_doc("Letter of Credit", lc.name)
		self.assertEqual((lc.status, lc.expiry_alerts_sent), ("Amended", "30,15,7"))
		self.assertEqual(lc_module.presentation_checklist(lc.name)[0]["available"], False)
		lc_module.mark_presented(lc.name)
		self.assertEqual(frappe.db.get_value("Letter of Credit", lc.name, "status"), "Documents presented")

	# ------------------------------------------------------------------ FIN-60
	def test_fin60_vc_accrues_pro_rata_and_trues_up(self):
		so = make_so(
			pvfss_variable_consideration=[
				{
					"vc_type": "Early delivery incentive",
					"maximum_amount": 1000,
					"estimation_method": "Expected value",
					"probability_pct": 60,
					"constrained_amount": 600,
				}
			]
		)
		self.assertEqual(flt(so.pvfss_variable_consideration[0].estimated_amount), 600)
		si = invoice_from_dn(so, qty=5)
		si.reload()
		self.assertEqual(flt(si.pvfss_vc_amount), 300)
		account = accounts.get(f.TEST_COMPANY, "vc_accrual")
		self.assertEqual(balance(account), 300)

		row = so.pvfss_variable_consideration[0].name
		result = vc.settle(so.name, row, 1000)
		self.assertEqual(result["true_up"], 700)
		self.assertEqual(balance(account), 1000)
		_cols, rows = revenue_and_vc_by_project.execute({"customer": so.customer})
		mine = next(r for r in rows if r["sales_order"] == so.name)
		self.assertEqual((mine["vc_recognised"], mine["true_up"], mine["revenue"]), (300, 700, 6000))

	# ------------------------------------------------------------------ FIN-65
	def test_fin65_petty_cash_above_threshold_needs_approval(self):
		frappe.db.set_single_value("PVFSS Settings", "petty_cash_approval_threshold", 500)
		settings.clear_cache()
		if not frappe.db.exists("Gender", "Male"):
			frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert()
		cash = frappe.db.get_value("Account", {"company": f.TEST_COMPANY, "account_type": "Cash", "is_group": 0}, "name")
		employee = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "_PVFSS Custodian",
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": f.TEST_COMPANY,
				"pvfss_petty_cash_account": cash,
			}
		).insert()
		expense = frappe.db.get_value(
			"Account", {"company": f.TEST_COMPANY, "root_type": "Expense", "is_group": 0}, "name"
		)
		pcv = frappe.get_doc(
			{
				"doctype": "Petty Cash Voucher",
				"company": f.TEST_COMPANY,
				"custodian": employee.name,
				"posting_date": nowdate(),
				"expense_account": expense,
				"description": "Site courier",
				"amount": 630,
				"vat_input": 1,
				"vat_amount": 30,
				"attachment": "/files/receipt.jpg",
			}
		).insert()
		self.assertEqual(pcv.cash_account, cash)
		self.assertRaises(frappe.ValidationError, pcv.submit)
		pcv_module.approve(pcv.name)
		pcv = frappe.get_doc("Petty Cash Voucher", pcv.name)
		before = balance(cash)
		pcv.submit()
		self.assertEqual(balance(cash), flt(before - 630, 2))
		self.assertEqual(balance(accounts.get(f.TEST_COMPANY, "vat_input")), 30)

	# ------------------------------------------------------------------ FIN-12 / 70 / 71
	def test_fin12_fin70_fin71_reports_run(self):
		so = make_so(pvfss_retention_pct=10, pvfss_retention_basis="Per invoice")
		si = invoice_from_dn(so)
		_cols, rows = invoice_and_payment_status.execute({"side": "Receivable", "party": si.customer})
		mine = next(r for r in rows if r["invoice"] == si.name)
		self.assertEqual((mine["retention"], mine["balance"]), (1000, 9000))
		_cols, rows = payment_status_by_project.execute({"project": so.project})
		if so.project:
			self.assertEqual(rows[0]["retention_held"], 1000)
		columns, data, _msg, chart = cash_flow_forecast.execute({})
		self.assertEqual(len(columns), 14)
		self.assertEqual(data[-1]["line"], "Closing balance")
		ar = next(r for r in data if r["line"] == "AR by payment schedule")
		self.assertGreaterEqual(sum(flt(v) for k, v in ar.items() if k.startswith("w")), 9000)
		self.assertTrue(chart["data"]["datasets"])
