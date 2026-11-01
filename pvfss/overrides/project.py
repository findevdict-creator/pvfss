"""Project doc events (PRJ-10, PRJ-40, FIN-50 dates)."""

import frappe
from frappe import _
from frappe.utils import add_months, cint, nowdate

DIRECTOR_ROLES = ("PVFSS Director", "System Manager")
COMPLETED = "Completed"


def validate(doc, method=None):
	set_warranty_dates(doc)
	check_closure(doc)
	set_status_summary(doc)


def set_warranty_dates(doc):
	if doc.get("pvfss_final_acceptance_date") and cint(doc.get("pvfss_warranty_months")):
		doc.pvfss_warranty_end_date = add_months(
			doc.pvfss_final_acceptance_date, cint(doc.pvfss_warranty_months)
		)
	else:
		doc.pvfss_warranty_end_date = doc.get("pvfss_final_acceptance_date")
	doc.pvfss_retention_release_date = doc.pvfss_warranty_end_date if doc.get("pvfss_retention_pct") else None


def check_closure(doc):
	"""PRJ-40 [RULE]: Completed only when every closure row is done or waived; waive is Director only."""
	before = doc.get_doc_before_save()
	old = {r.name: r for r in (before.get("pvfss_closure_items") or [])} if before else {}
	is_director = bool(set(frappe.get_roles()) & set(DIRECTOR_ROLES))
	for row in doc.get("pvfss_closure_items") or []:
		prev = old.get(row.name)
		waived_changed = cint(row.waived) != (cint(prev.waived) if prev else 0)
		done_changed = cint(row.done) != (cint(prev.done) if prev else 0)
		if waived_changed and cint(row.waived):
			if not is_director:
				frappe.throw(
					_("Only a Director can waive closure item {0}.").format(row.item), frappe.PermissionError
				)
			if not (row.waiver_reason or "").strip():
				frappe.throw(_("Enter the waiver reason for {0}.").format(row.item))
		if waived_changed or done_changed:
			row.by_user = frappe.session.user
			row.on_date = nowdate()
	if doc.status == COMPLETED:
		open_rows = [
			r.item for r in doc.get("pvfss_closure_items") or [] if not (cint(r.done) or cint(r.waived))
		]
		if open_rows:
			frappe.throw(
				_("Project cannot be Completed. Closure items not done or waived: {0}").format(
					"; ".join(open_rows)
				),
				title=_("Closure checklist (PRJ-40)"),
			)


def set_status_summary(doc):
	routes = doc.get("pvfss_supply_routes") or []
	if not routes and not doc.get("pvfss_handover"):
		return
	risky = sum(1 for r in routes if cint(r.at_risk))
	closure = doc.get("pvfss_closure_items") or []
	parts = [_("{0} Supplier PO(s)").format(len(routes))]
	parts.append(_("{0} at risk").format(risky) if risky else _("on track"))
	if closure:
		done = sum(1 for r in closure if cint(r.done) or cint(r.waived))
		parts.append(_("closure {0}/{1}").format(done, len(closure)))
	doc.pvfss_status_summary = ", ".join(parts)
