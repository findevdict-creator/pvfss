"""ICV estimate (ICV-01 to ICV-20). Estimates only: the official score comes from the certifying body."""

import frappe
from frappe import _
from frappe.utils import add_months, cint, date_diff, flt, formatdate, getdate, nowdate

from pvfss.utils import alerts, settings

# ICV-01 working weightages (component, weight %, formula note)
DEFAULT_COMPONENTS = [
	("Local procurement", 50, "ICV-weighted supplier spend / total procurement spend"),
	("UAE net assets / investment", 25, "UAE fixed assets / total revenue, capped at 100%"),
	("Emiratisation", 5, "UAE nationals / headcount at period end"),
	("Headcount / payroll", 10, "Emirati payroll / total payroll (headcount ratio when payroll is blank)"),
	("Bonus factors", 5, "Sum of the bonus factor scores, capped at 100%"),
	("Other", 5, "Entered on the period"),
]
CERTIFICATE_MONTHS = 14
AUTO_METRICS = (
	"procurement_spend",
	"uae_spend",
	"icv_weighted_spend",
	"revenue",
	"fixed_assets",
	"headcount",
	"uae_nationals",
)


def seed_settings():
	doc = frappe.get_single("ICV Settings")
	if doc.components:
		return
	for component, weight, note in DEFAULT_COMPONENTS:
		doc.append("components", {"component": component, "weight_pct": weight, "formula_note": note})
	doc.flags.ignore_permissions = True
	doc.save()


def active_certificate():
	name = frappe.db.get_value("ICV Certificate", {"status": "Active"}, "name", order_by="issue_date desc")
	return frappe.get_doc("ICV Certificate", name) if name else None


def current_score():
	"""Active certificate score, else the latest estimate."""
	cert = active_certificate()
	if cert:
		return flt(cert.score_pct)
	return flt(frappe.db.get_value("ICV Period Data", {}, "estimated_icv_pct", order_by="to_date desc"))


# ----------------------------------------------------------------------------- ICV-10 auto values
def supplier_spend(from_date, to_date, company):
	"""Purchase Invoice spend net of VAT per supplier, with UAE flag and ICV score."""
	rows = frappe.get_all(
		"Purchase Invoice",
		filters={"docstatus": 1, "company": company, "posting_date": ["between", [from_date, to_date]]},
		fields=["supplier", "base_net_total"],
	)
	spend = {}
	for row in rows:
		spend[row.supplier] = spend.get(row.supplier, 0.0) + flt(row.base_net_total)
	out = []
	for supplier, amount in sorted(spend.items(), key=lambda kv: -kv[1]):
		info = frappe.db.get_value(
			"Supplier",
			supplier,
			["supplier_name", "pvfss_uae_based", "pvfss_icv_score", "pvfss_icv_cert_expiry"],
			as_dict=True,
		)
		valid = not info.pvfss_icv_cert_expiry or getdate(info.pvfss_icv_cert_expiry) >= getdate(to_date)
		score = flt(info.pvfss_icv_score) if valid else 0
		out.append(
			{
				"supplier": supplier,
				"supplier_name": info.supplier_name,
				"uae_based": cint(info.pvfss_uae_based),
				"spend": amount,
				"icv_score": score,
				"weighted": amount * score / 100,
			}
		)
	return out


def employees_at(to_date, company):
	to_date = getdate(to_date)
	out = []
	for emp in frappe.get_all(
		"Employee",
		filters={"company": company, "date_of_joining": ["<=", to_date]},
		fields=["name", "employee_name", "relieving_date", "pvfss_nationality_uae"],
	):
		if emp.relieving_date and getdate(emp.relieving_date) <= to_date:
			continue
		out.append(emp)
	return out


def fixed_assets(to_date, company):
	accounts = frappe.get_all(
		"Account", filters={"company": company, "account_type": "Fixed Asset", "is_group": 0}, pluck="name"
	)
	rows = frappe.get_all(
		"GL Entry",
		filters={"account": ["in", accounts or [""]], "is_cancelled": 0, "posting_date": ["<=", to_date]},
		fields=["debit", "credit"],
	)
	return sum(flt(r.debit) - flt(r.credit) for r in rows)


def collect(doc):
	suppliers = supplier_spend(doc.from_date, doc.to_date, doc.company)
	staff = employees_at(doc.to_date, doc.company)
	revenue = sum(
		flt(v)
		for v in frappe.get_all(
			"Sales Invoice",
			filters={
				"docstatus": 1,
				"company": doc.company,
				"posting_date": ["between", [doc.from_date, doc.to_date]],
			},
			pluck="base_net_total",
		)
	)
	return {
		"procurement_spend": sum(r["spend"] for r in suppliers),
		"uae_spend": sum(r["spend"] for r in suppliers if r["uae_based"]),
		"icv_weighted_spend": sum(r["weighted"] for r in suppliers),
		"revenue": revenue,
		"fixed_assets": fixed_assets(doc.to_date, doc.company),
		"headcount": len(staff),
		"uae_nationals": sum(1 for e in staff if e.pvfss_nationality_uae),
	}


def _ratio(part, whole):
	return min(flt(part) * 100 / flt(whole), 100) if flt(whole) else 0


def component_scores(doc):
	"""Score % per component from the used values (formulas in ICV Settings notes)."""
	payroll = (
		_ratio(doc.emirati_payroll, doc.payroll_total)
		if flt(doc.payroll_total)
		else _ratio(doc.uae_nationals, doc.headcount)
	)
	return {
		"Local procurement": _ratio(doc.icv_weighted_spend, doc.procurement_spend),
		"UAE net assets / investment": _ratio(doc.fixed_assets, doc.revenue),
		"Emiratisation": _ratio(doc.uae_nationals, doc.headcount),
		"Headcount / payroll": payroll,
		"Bonus factors": min(sum(flt(r.score_pct) for r in doc.bonus_factors), 100),
		"Other": min(flt(doc.other_score_pct), 100),
	}


# ----------------------------------------------------------------------------- ICV-20
@frappe.whitelist()
def compare(
	bid_price: float,
	icv_score: float,
	weightage: float,
	competitor_bid: float = 0,
	competitor_score: float = 0,
):
	"""SCR-ICV-07: evaluated prices and the bid that would match the competitor."""
	weight = flt(weightage) / 100

	def evaluated(price, score):
		return flt(flt(price) * (1 - flt(score) / 100 * weight), 2)

	ours = evaluated(bid_price, icv_score)
	theirs = evaluated(competitor_bid, competitor_score) if flt(competitor_bid) else 0
	factor = 1 - flt(icv_score) / 100 * weight
	return {
		"pvfss_evaluated": ours,
		"competitor_evaluated": theirs,
		"difference": flt(ours - theirs, 2) if theirs else 0,
		"matching_bid": flt(theirs / factor, 2) if theirs and factor else 0,
	}


@frappe.whitelist()
def defaults():
	return {"icv_score": current_score(), "weightage": settings.get_float("default_icv_weightage_pct")}


# ----------------------------------------------------------------------------- ICV-03 / ICV-11 alerts
def certificate_expiry():
	"""PVFSS certificate expiry at 90 and 30 days (each level once) to Finance and Directors."""
	cert = active_certificate()
	if not cert:
		return 0
	days = date_diff(cert.expiry_date, nowdate())
	done = {int(x) for x in (cert.expiry_alerts_sent or "").split(",") if x.strip().isdigit()}
	due = [d for d in settings.get_alert_days("icv_expiry_alert_days") if days <= d and d not in done]
	if not due or days < 0:
		return 0
	alerts.send(
		alerts.users_with_role("Finance User", "Finance Manager", "PVFSS Director", "ICV User"),
		_("PVFSS ICV certificate {0} expires on {1} ({2} days).").format(
			cert.certificate_no, formatdate(cert.expiry_date), days
		),
		"ICV Certificate",
		cert.name,
	)
	done.update(due)
	cert.db_set(
		"expiry_alerts_sent", ",".join(str(d) for d in sorted(done, reverse=True)), update_modified=False
	)
	return 1


MAJOR_SUPPLIERS = 10
SUPPLIER_ALERT_DAYS = (30, 0)


def supplier_certificate_expiry():
	"""ICV-03: a major supplier's ICV certificate expires in 30 days or today (top suppliers by 12-month spend)."""
	company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
	if not company:
		return 0
	top = supplier_spend(add_months(nowdate(), -12), nowdate(), company)[:MAJOR_SUPPLIERS]
	sent = 0
	for row in top:
		expiry = frappe.db.get_value("Supplier", row["supplier"], "pvfss_icv_cert_expiry")
		if expiry and date_diff(expiry, nowdate()) in SUPPLIER_ALERT_DAYS:
			alerts.send(
				alerts.users_with_role("ICV User", "Finance Manager", "Post-Bidding Manager"),
				_("ICV certificate of {0} expires on {1}.").format(row["supplier_name"], formatdate(expiry)),
				"Supplier",
				row["supplier"],
			)
			sent += 1
	return sent


def expire_certificates():
	for name in frappe.get_all(
		"ICV Certificate", filters={"status": "Active", "expiry_date": ["<", nowdate()]}, pluck="name"
	):
		frappe.db.set_value("ICV Certificate", name, "status", "Expired")


def daily():
	expire_certificates()
	return certificate_expiry() + supplier_certificate_expiry()


def certificate_expiry_date(issue_date):
	return add_months(issue_date, CERTIFICATE_MONTHS)
