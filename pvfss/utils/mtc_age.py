"""MTC age rule (SMR-20, SMR-21, SCR-SMR-06/07).

Lookup order: Client Project override -> Project override -> MTC Age Rule (company default).
Each level is searched for the item's product category and then its parent groups, with the
item's material type. A blank max age means "no limit, warn only".

Age is measured from the MTC issue date to a reference date: the SMR review date by default
(PVFSS Settings, Q-02). A certificate is over age when the reference date is later than
issue date + limit months.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, date_diff, formatdate, getdate, nowdate

from pvfss.utils import alerts, settings

COMPANY_DEFAULT = "company default"


def item_profile(item_code, po_item=None):
	"""(category, material) for the rule lookup: PO line values first, then the item master."""
	item = frappe.get_cached_value(
		"Item", item_code, ["item_group", "pvfss_material_type", "pvfss_mtc_rule_category"], as_dict=True
	)
	category = material = None
	if po_item:
		category = po_item.get("pvfss_product_category")
		material = po_item.get("pvfss_material_type")
	if item:
		category = category or item.pvfss_mtc_rule_category or item.item_group
		material = material or item.pvfss_material_type
	return category, material


def group_chain(category):
	"""The category and its parent Item Groups, nearest first."""
	chain = []
	while category and category not in chain:
		chain.append(category)
		category = frappe.get_cached_value("Item Group", category, "parent_item_group")
	return chain


def _match(rows, chain, material):
	for group in chain:
		for row in rows:
			if row.product_category == group and row.material_type == material:
				return row, group
	return None, None


def find_rule(item_code, project=None, client_project=None, po_item=None):
	"""Return {"months": int | None, "source": str, "label": str} or None when no rule applies."""
	category, material = item_profile(item_code, po_item)
	chain = group_chain(category)
	if not chain or not material:
		return None
	if project and not client_project:
		client_project = frappe.db.get_value("Project", project, "pvfss_client_project")
	levels = []
	if client_project:
		levels.append(
			(
				_("client project {0}").format(client_project),
				frappe.get_all(
					"Client Project MTC Override",
					filters={"parent": client_project, "parenttype": "Client Project"},
					fields=["product_category", "material_type", "max_age_months"],
				),
			)
		)
	if project:
		levels.append(
			(
				_("project {0}").format(project),
				frappe.get_all(
					"Client Project MTC Override",
					filters={"parent": project, "parenttype": "Project"},
					fields=["product_category", "material_type", "max_age_months"],
				),
			)
		)
	levels.append(
		(
			_(COMPANY_DEFAULT),
			frappe.get_all(
				"MTC Age Rule",
				filters={"active": 1},
				fields=["product_category", "material_type", "max_age_months"],
			),
		)
	)
	for source, rows in levels:
		row, group = _match(rows, chain, material)
		if row:
			return {
				"months": cint(row.max_age_months) or None,
				"source": source,
				"label": f"{group} + {material}",
			}
	return None


def age_months(issue_date, ref_date):
	issue, ref = getdate(issue_date), getdate(ref_date)
	months = (ref.year - issue.year) * 12 + ref.month - issue.month
	if ref.day < issue.day:
		months -= 1
	return max(months, 0)


def reference_date(review_date=None):
	return getdate(review_date or nowdate())


def check(mtc, heat_no, item_code, ref_date, project=None, client_project=None, po_item=None):
	"""Age check for one heat on one MTC. Returns a dict with over / message / expiry."""
	issue = frappe.db.get_value("MTC", mtc, "issue_date")
	rule = find_rule(item_code, project, client_project, po_item)
	age = age_months(issue, ref_date)
	out = {
		"mtc": mtc,
		"heat_no": heat_no,
		"age": age,
		"limit": rule and rule["months"],
		"rule": rule,
		"over": False,
		"expiry": None,
		"message": None,
	}
	if not rule or not rule["months"]:
		out["message"] = _("No MTC age limit set for this category and material (warning only).")
		out["display"] = _("{0} m / no limit").format(age)
		return out
	expiry = add_months(getdate(issue), rule["months"])
	out["expiry"] = expiry
	out["display"] = f"{age} / {rule['months']} m"
	if getdate(ref_date) > expiry:
		out["over"] = True
		out["message"] = _(
			"Heat {0} MTC {1} is {2} months old (issue {3}, review {4}). Limit {5} months (rule: {6}, {7})."
		).format(
			heat_no,
			mtc,
			age,
			formatdate(issue),
			formatdate(ref_date),
			rule["months"],
			rule["label"],
			rule["source"],
		)
	return out


# ----------------------------------------------------------------------------- SMR-21
def age_alerts():
	"""Daily: alert Quality when a stocked heat's MTC reaches its limit minus N days."""
	days = settings.get_int("mtc_age_alert_days", 60)
	today = getdate(nowdate())
	rows = frappe.db.sql(
		"""
		select mh.name, mh.heat_no, mh.heat_number, mh.item_code, m.name as mtc, m.issue_date,
			m.supplier_po, m.certificate_no, coalesce(mh.item_code, h.item_code) as heat_item
		from `tabMTC Heat` mh
		join `tabMTC` m on m.name = mh.parent
		join `tabHeat Number` h on h.name = mh.heat_number
		where m.docstatus = 1 and mh.age_alerted_on is null and h.balance_qty > 0
		""",
		as_dict=True,
	)
	recipients = alerts.users_with_role("Quality User", "Quality Manager")
	sent = 0
	for row in rows:
		project = row.supplier_po and frappe.db.get_value("Purchase Order", row.supplier_po, "project")
		rule = find_rule(row.heat_item, project)
		if not rule or not rule["months"]:
			continue
		expiry = add_months(getdate(row.issue_date), rule["months"])
		if today < add_days(expiry, -days):
			continue
		stock = heat_stock(row.heat_number)
		where = ", ".join(f"{frappe.utils.flt(q):g} at {w}" for w, q in stock) or _("no stock")
		subject = _("MTC {0} for heat {1} reaches its {2}-month limit on {3} ({4} days). Stock: {5}.").format(
			row.certificate_no or row.mtc,
			row.heat_number,
			rule["months"],
			formatdate(expiry),
			date_diff(expiry, today),
			where,
		)
		alerts.send(recipients, subject, "Heat Number", row.heat_number)
		frappe.db.set_value("MTC Heat", row.name, "age_alerted_on", today, update_modified=False)
		sent += 1
	return sent


def heat_stock(heat):
	"""[(warehouse, qty)] with a positive balance for the heat's batches."""
	return frappe.db.sql(
		"""
		select sbe.warehouse, sum(sbe.qty) as qty
		from `tabSerial and Batch Entry` sbe
		join `tabBatch` b on b.name = sbe.batch_no
		where b.pvfss_heat_number = %s and sbe.is_cancelled = 0 and sbe.docstatus = 1
		group by sbe.warehouse
		having sum(sbe.qty) > 0
		""",
		heat,
	)
