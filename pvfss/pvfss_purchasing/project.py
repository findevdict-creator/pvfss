"""Project creation from the handover and delivery tracking (PRJ-04, PRJ-05, PRJ-10, PRJ-11, PRJ-20,
PRJ-21, DMS-01 folders, PRJ-30 auto-created changes)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from pvfss.utils import alerts, settings

MANUFACTURING = "Manufacturing"
SMR = "Ready stock (SMR)"
READY_MILESTONE = "Ready for dispatch"
DELIVERED_MILESTONE = "Delivered"
DMS_SUBFOLDERS = [
	"01 Inquiry & RFQ",
	"02 Quotation & Customer PO",
	"03 Supplier PO",
	"04 Quality",
	"05 Dispatch",
	"06 Finance",
	"07 Correspondence",
	"08 Final dossier",
]


# ----------------------------------------------------------------------------- PRJ-04
def create_from_handover(handover):
	so = frappe.get_doc("Sales Order", handover.sales_order)
	if so.get("project") and frappe.db.exists("Project", so.project):
		project = frappe.get_doc("Project", so.project)
	else:
		project = frappe.new_doc("Project")
		project.project_name = f"{so.po_no or so.name} - {so.customer_name}"[:140]
		if frappe.db.exists("Project", {"project_name": project.project_name}):
			project.project_name = f"{project.project_name} ({so.name})"
	project.update(
		{
			"customer": so.customer,
			"sales_order": so.name,
			"company": so.company,
			"expected_end_date": so.delivery_date,
			"pvfss_handover": handover.name,
			"pvfss_client_project": handover.client_project,
			"pvfss_customer_po_no": so.po_no,
			"pvfss_post_bidding_owner": handover.post_bidding_owner,
			"pvfss_quality_lead": handover.quality_lead,
			"pvfss_customer_delivery_date": so.delivery_date,
			"pvfss_retention_pct": so.get("pvfss_retention_pct"),
			"pvfss_retention_basis": so.get("pvfss_retention_basis"),
			"pvfss_warranty_months": so.get("pvfss_warranty_months"),
		}
	)
	pos = frappe.get_all(
		"Purchase Order",
		filters={"pvfss_sales_order": so.name, "docstatus": 1},
		fields=["name", "supplier", "schedule_date"],
		order_by="creation",
	)
	transit = settings.get_int("default_transit_buffer_days", 0)
	if not project.get("pvfss_supply_routes"):
		for po in pos:
			project.append(
				"pvfss_supply_routes",
				{
					"purchase_order": po.name,
					"supplier": po.supplier,
					"supply_route": MANUFACTURING,
					"committed_ready_date": po.schedule_date,
					"forecast_ready_date": po.schedule_date,
					"transit_days": transit,
				},
			)
	if not project.get("pvfss_technical_requirements"):
		for row in technical_requirements(so, handover.inquiry):
			project.append("pvfss_technical_requirements", row)
	if not project.get("pvfss_closure_items"):
		for row in settings.get_table("project_closure_template"):
			project.append("pvfss_closure_items", {"item": row.item})
	if not project.get("pvfss_mtc_overrides") and handover.client_project:
		for row in frappe.get_doc("Client Project", handover.client_project).mtc_age_overrides:
			project.append(
				"pvfss_mtc_overrides",
				{
					"product_category": row.product_category,
					"material_type": row.material_type,
					"max_age_months": row.max_age_months,
					"reference_basis": row.reference_basis,
					"note": row.note,
				},
			)
	project.flags.ignore_permissions = True
	project.save()

	frappe.db.set_value("Sales Order", so.name, "project", project.name, update_modified=False)
	for po in pos:
		frappe.db.set_value("Purchase Order", po.name, "project", project.name, update_modified=False)
		ensure_expediting_log(po.name, project)
	create_folders(project)
	return project


def technical_requirements(so, inquiry):
	"""PRJ-05: one row per SO line requirement, plus the inquiry key requirements."""
	rows = []
	for line in so.items:
		ref = line.get("pvfss_customer_line_ref") or str(line.idx)
		for category, field in (
			("Material", "pvfss_specification"),
			("Inspection", "pvfss_inspection_req"),
			("Documentation", "pvfss_doc_req"),
		):
			if line.get(field):
				rows.append(
					{
						"category": category,
						"requirement": line.get(field),
						"source_document": f"Customer PO {so.name}",
						"applies_to_lines": ref,
					}
				)
	key = frappe.db.get_value("Opportunity", inquiry, "pvfss_key_requirements") if inquiry else None
	for text in (key or "").splitlines():
		text = text.strip(" -•\t")
		if text:
			rows.append({"category": "Other", "requirement": text, "source_document": f"Inquiry {inquiry}"})
	return rows


def create_folders(project):
	"""DMS-01: Home/Projects/{Project} - {Customer PO no} with the standard subfolders."""
	projects = ensure_folder("Projects", "Home")
	title = f"{project.name} - {project.pvfss_customer_po_no or ''}".strip(" -")
	root = ensure_folder(title, projects)
	for sub in DMS_SUBFOLDERS:
		ensure_folder(sub, root)
	return root


def ensure_folder(name, parent):
	existing = frappe.db.get_value("File", {"file_name": name, "folder": parent, "is_folder": 1})
	if existing:
		return existing
	doc = frappe.get_doc({"doctype": "File", "file_name": name, "folder": parent, "is_folder": 1})
	doc.insert(ignore_permissions=True)
	return doc.name


# ----------------------------------------------------------------------------- PRJ-20
def milestone_template(route):
	key = SMR if route == SMR else MANUFACTURING
	return sorted(
		settings.get_table("expediting_milestone_template", supply_route=key), key=lambda r: cint(r.sequence)
	)


def ensure_expediting_log(purchase_order, project=None):
	existing = frappe.db.get_value("Expediting Log", {"purchase_order": purchase_order})
	if existing:
		return existing
	po = frappe.db.get_value(
		"Purchase Order",
		purchase_order,
		["supplier", "schedule_date", "project", "contact_person"],
		as_dict=True,
	)
	route_row = None
	if project:
		route_row = next(
			(r for r in project.get("pvfss_supply_routes") or [] if r.purchase_order == purchase_order), None
		)
	log = frappe.new_doc("Expediting Log")
	log.purchase_order = purchase_order
	log.supplier = po.supplier
	log.project = project.name if project else po.project
	log.supply_route = route_row.supply_route if route_row else MANUFACTURING
	log.expeditor = project.get("pvfss_post_bidding_owner") if project else None
	log.supplier_contact = po.contact_person
	seed_milestones(log, po.schedule_date, cint(route_row.transit_days) if route_row else None)
	log.insert(ignore_permissions=True)
	return log.name


def seed_milestones(log, ready_date, transit=None):
	transit = settings.get_int("default_transit_buffer_days", 0) if transit is None else transit
	log.set("milestones", [])
	for row in milestone_template(log.supply_route):
		committed = None
		if row.milestone == READY_MILESTONE:
			committed = ready_date
		elif row.milestone == DELIVERED_MILESTONE and ready_date:
			committed = add_days(ready_date, transit)
		log.append(
			"milestones",
			{
				"milestone": row.milestone,
				"sequence": row.sequence,
				"committed_date": committed,
				"forecast_date": committed,
			},
		)


def milestone_status(row, today, warn_days):
	"""PRJ-21: Late when past due without an actual date; At risk when the forecast is after the
	committed date, or the committed date is within ``warn_days`` without an actual date."""
	if row.actual_date:
		return "Done"
	due = row.forecast_date or row.committed_date
	if due and getdate(due) < today:
		return "Late"
	if row.forecast_date and row.committed_date and getdate(row.forecast_date) > getdate(row.committed_date):
		return "At risk"
	if row.committed_date and getdate(row.committed_date) <= add_days(today, warn_days):
		return "At risk"
	return "On track"


def refresh_log(log):
	today = getdate(nowdate())
	warn = settings.get_int("expediting_delay_alert_days", 7)
	for row in log.milestones:
		row.status = milestone_status(row, today, warn)
	pending = [r for r in sorted(log.milestones, key=lambda r: cint(r.sequence)) if r.status != "Done"]
	nxt = pending[0] if pending else None
	log.next_milestone = nxt.milestone if nxt else None
	log.next_committed_date = nxt.committed_date if nxt else None
	log.next_forecast_date = nxt.forecast_date if nxt else None
	statuses = {r.status for r in pending}
	if log.milestones and not pending:
		log.status = "Complete"
	elif "Late" in statuses:
		log.status = "Late"
	elif "At risk" in statuses:
		log.status = "At risk"
	else:
		log.status = "On track"
	dates = [r.contact_date for r in log.contacts if r.contact_date] + [
		r.last_contact_date for r in log.milestones if r.last_contact_date
	]
	log.last_contact_date = max(getdate(d) for d in dates) if dates else None


def forecast_ready(log):
	row = next((r for r in log.milestones if r.milestone == READY_MILESTONE), None)
	if not row:
		return None
	return row.actual_date or row.forecast_date or row.committed_date


def update_project_risk(project_name):
	"""PRJ-21: delivery at risk when any PO's forecast ready date + transit > customer delivery date."""
	if not project_name or not frappe.db.exists("Project", project_name):
		return
	project = frappe.get_doc("Project", project_name)
	due = project.get("pvfss_customer_delivery_date")
	reasons = []
	for route in project.get("pvfss_supply_routes") or []:
		log = frappe.db.get_value("Expediting Log", {"purchase_order": route.purchase_order})
		if log:
			ready = forecast_ready(frappe.get_doc("Expediting Log", log))
			if ready:
				route.forecast_ready_date = ready
		route.at_risk = 0
		if due and route.forecast_ready_date:
			arrival = add_days(getdate(route.forecast_ready_date), cint(route.transit_days))
			if arrival > getdate(due):
				route.at_risk = 1
				reasons.append(
					_("{0}: ready {1} + {2} days transit is after {3}").format(
						route.purchase_order,
						frappe.utils.formatdate(route.forecast_ready_date),
						cint(route.transit_days),
						frappe.utils.formatdate(due),
					)
				)
	project.pvfss_delivery_at_risk = 1 if reasons else 0
	project.pvfss_risk_reason = "\n".join(reasons) or None
	project.flags.ignore_permissions = True
	project.save()


def delay_alerts():
	"""Daily (PRJ-21): alert the Post-Bidding owner once per milestone that is At risk or Late."""
	today = getdate(nowdate())
	for name in frappe.get_all("Expediting Log", filters={"status": ["!=", "Complete"]}, pluck="name"):
		log = frappe.get_doc("Expediting Log", name)
		refresh_log(log)
		owner = (
			frappe.db.get_value("Project", log.project, "pvfss_post_bidding_owner") if log.project else None
		) or log.expeditor
		for row in log.milestones:
			if row.status in ("At risk", "Late") and not row.alerted_on:
				alerts.send(
					[owner],
					_("{0} {1}: {2} {3} (committed {4}, forecast {5})").format(
						log.purchase_order,
						log.supplier,
						row.milestone,
						_(row.status).lower(),
						frappe.utils.formatdate(row.committed_date) if row.committed_date else "-",
						frappe.utils.formatdate(row.forecast_date) if row.forecast_date else "-",
					),
					"Expediting Log",
					log.name,
				)
				row.alerted_on = today
		log.flags.ignore_permissions = True
		log.save()


# ----------------------------------------------------------------------------- PRJ-30
def auto_change(doc, method=None):
	"""after_insert on Sales Order / Purchase Order: an amendment of a project document opens a change."""
	if not doc.get("amended_from"):
		return
	project = doc.get("project") or frappe.db.get_value(doc.doctype, doc.amended_from, "project")
	if not project:
		return
	reason = doc.get("pvfss_amendment_reason") or _("Amendment of {0}").format(doc.amended_from)
	old_total = flt(frappe.db.get_value(doc.doctype, doc.amended_from, "base_grand_total"))
	cost = flt(doc.base_grand_total) - old_total if doc.doctype == "Purchase Order" else 0
	revenue = flt(doc.base_grand_total) - old_total if doc.doctype == "Sales Order" else 0
	change = frappe.get_doc(
		{
			"doctype": "Project Change",
			"project": project,
			"change_type": "Other",
			"raised_by": "PVFSS",
			"raised_on": nowdate(),
			"auto_created": 1,
			"source": f"{doc.doctype} {doc.name}",
			"description": reason,
			"cost_impact": cost,
			"margin_impact": revenue - cost,
			"affected_documents": [
				{"document_type": doc.doctype, "document_name": doc.amended_from},
				{"document_type": doc.doctype, "document_name": doc.name},
			],
		}
	)
	change.flags.ignore_links = True  # the amended-from document is cancelled
	change.insert(ignore_permissions=True)
	frappe.msgprint(
		_("Change register entry {0} created").format(
			frappe.utils.get_link_to_form("Project Change", change.name)
		),
		alert=True,
	)
	return change.name


# ----------------------------------------------------------------------------- PRJ-11
def _sum(sql, values):
	return flt(frappe.db.sql(sql, values)[0][0])


def po_figures(po):
	"""Per Supplier PO figures for the dashboard. Later modules add ITP, RFI, NCR and IRN figures."""
	received = _sum("select sum(received_qty) from `tabPurchase Order Item` where parent=%s", po.name)
	ordered = _sum("select sum(qty) from `tabPurchase Order Item` where parent=%s", po.name)
	invoiced = _sum(
		"""select sum(pii.base_net_amount) from `tabPurchase Invoice Item` pii
		join `tabPurchase Invoice` pi on pi.name = pii.parent
		where pii.purchase_order=%s and pi.docstatus=1""",
		po.name,
	)
	paid = flt(po.advance_paid)
	exp = frappe.db.get_value(
		"Expediting Log",
		{"purchase_order": po.name},
		["name", "status", "next_milestone", "next_forecast_date"],
		as_dict=True,
	)
	return {
		"purchase_order": po.name,
		"supplier": po.supplier,
		"status": po.status,
		"ordered_qty": ordered,
		"received_qty": received,
		"per_received": flt(po.per_received),
		"invoiced_amount": invoiced,
		"per_billed": flt(po.per_billed),
		"paid_amount": paid,
		"expediting_log": exp.name if exp else None,
		"expediting_status": exp.status if exp else None,
		"next_milestone": exp.next_milestone if exp else None,
		"next_forecast_date": exp.next_forecast_date if exp else None,
	}


EXTRA_FIGURES = []  # dotted paths: fn(po_name) -> dict merged into each PO row (12-quality, 13-dispatch)


@frappe.whitelist()
def get_dashboard(project: str):
	doc = frappe.get_doc("Project", project)
	doc.check_permission("read")
	pos = frappe.get_all(
		"Purchase Order",
		filters={"project": project, "docstatus": 1},
		fields=["name", "supplier", "status", "per_received", "per_billed", "advance_paid"],
		order_by="creation",
	)
	rows = []
	for po in pos:
		row = po_figures(po)
		for path in EXTRA_FIGURES:
			row.update(frappe.get_attr(path)(po.name) or {})
		rows.append(row)
	changes = frappe.get_all(
		"Project Change", filters={"project": project, "docstatus": ["<", 2]}, fields=["workflow_state"]
	)
	return {
		"purchase_orders": rows,
		"at_risk": cint(doc.get("pvfss_delivery_at_risk")),
		"risk_reason": doc.get("pvfss_risk_reason"),
		"open_changes": sum(1 for c in changes if c.workflow_state == "Open"),
		"closure_done": sum(1 for r in doc.get("pvfss_closure_items") or [] if r.done or r.waived),
		"closure_total": len(doc.get("pvfss_closure_items") or []),
	}
