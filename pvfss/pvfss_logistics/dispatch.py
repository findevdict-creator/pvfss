"""Dispatch (Module 10: DSP-01 to DSP-10, gate G7) on the standard Delivery Note."""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, nowdate

from pvfss.gates.base import GateResult
from pvfss.pvfss_quality import traceability
from pvfss.utils import alerts, settings

DOCS_COMPLETE = "Documents complete"
APPROVED = "Approved for dispatch"
DELIVERED = "Delivered"
QTY_TOLERANCE = 0.001


# ----------------------------------------------------------------------------- DSP-02 / G7
def irn_required(item_code):
	required = frappe.db.get_value("Item", item_code, "pvfss_irn_required")
	return bool(required) or not settings.get_flag("allow_dispatch_without_irn")


def irn_released(batch):
	"""(qty released on Issued IRNs, latest IRN) for a batch."""
	row = frappe.db.sql(
		"""select sum(l.qty_released), max(i.name) from `tabIRN Line` l join `tabIRN` i on i.name = l.parent
		where l.batch = %s and i.docstatus = 1""",
		batch,
	)[0]
	return flt(row[0]), row[1]


def shipped_before(batch, exclude):
	return abs(
		flt(
			frappe.db.sql(
				"""select sum(qty) from `tabSerial and Batch Entry`
				where batch_no = %s and voucher_type = 'Delivery Note' and voucher_no != %s
					and is_cancelled = 0 and docstatus = 1""",
				(batch, exclude or ""),
			)[0][0]
		)
	)


def gate(doc):
	"""Dispatch gate (DSP-02, TRC-04): batches on an Issued IRN, within released qty, heat not held."""
	result = GateResult(_("Dispatch gate failed"), doc=doc, gate="G7")
	traceability.check_release(doc, result)
	for row in doc.items:
		if not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			continue
		line = row.get("pvfss_customer_line_ref") or row.idx
		batches = traceability.row_batches(row)
		needs_irn = irn_required(row.item_code)
		status = []
		if needs_irn and not batches and traceability.is_heat_traceable(row.item_code):
			result.fail(_("Line {0}: select the batches to ship.").format(line), rule="DSP-02")
			status.append(_("no batch"))
		for batch, qty in batches:
			if not needs_irn:
				continue
			released, irn = irn_released(batch)
			before = shipped_before(batch, doc.name)
			row.pvfss_irn, row.pvfss_irn_qty, row.pvfss_shipped_before = irn, released, before
			if not irn:
				result.fail(
					_("Line {0}, batch {1}: not on any issued IRN.").format(line, batch), rule="DSP-02"
				)
				status.append(_("no IRN"))
			elif before + flt(qty) > released + QTY_TOLERANCE:
				result.fail(
					_(
						"Line {0}, batch {1}: shipping {2:g}, {3} released {4:g}, already shipped {5:g}."
					).format(line, batch, flt(qty), irn, released, before),
					rule="DSP-02",
				)
				status.append(_("over IRN qty"))
		row.pvfss_gate_status = ("✗ " + ", ".join(status)) if status else "✓"
	return result


# ----------------------------------------------------------------------------- DSP-03
def template_rows(transport):
	return [
		r
		for r in settings.get_table("dispatch_document_template")
		if r.delivery_mode in ("All", transport or "Road")
	]


def fill_documents(doc):
	"""Pre-fill from the template by transport mode plus the PO / SO document requirements;
	MTC and IRN rows are filled from the shipped batches."""
	existing = {r.document for r in doc.pvfss_dispatch_documents}
	for t in template_rows(doc.get("pvfss_transport_mode")):
		if t.document not in existing:
			doc.append(
				"pvfss_dispatch_documents",
				{"document": t.document, "required": t.required, "status": "Pending", "source": "Template"},
			)
			existing.add(t.document)
	for row in doc.items:
		for req in (row.get("pvfss_doc_req") or "").replace(";", ",").split(","):
			req = req.strip()
			if req and req not in existing:
				doc.append(
					"pvfss_dispatch_documents",
					{"document": req, "required": 1, "status": "Pending", "source": "PO requirement"},
				)
				existing.add(req)
	auto_fill(doc)
	refresh_ready(doc)


def shipped_heats(doc):
	batches = [b for row in doc.items for b, _q in traceability.row_batches(row)]
	return batches, {
		r.pvfss_heat_number for r in traceability.batch_heats(batches).values() if r.pvfss_heat_number
	}


def auto_fill(doc):
	batches, heats = shipped_heats(doc)
	irns = sorted({irn_released(b)[1] for b in batches} - {None})
	mtcs = sorted(
		set(
			frappe.get_all(
				"MTC Heat",
				filters={"heat_number": ["in", list(heats) or [""]], "parenttype": "MTC", "docstatus": 1},
				pluck="parent",
			)
		)
	)
	for row in doc.pvfss_dispatch_documents:
		if row.document == "IRN / MPQT documentation" and irns:
			row.update({"reference_doctype": "IRN", "reference_name": irns[0], "source": "Auto"})
			row.remarks = ", ".join(irns)
			row.status = "Ready"
		if row.document == "MTCs" and mtcs and heats:
			covered = set(
				frappe.get_all(
					"MTC Heat",
					filters={"parent": ["in", mtcs], "heat_number": ["in", list(heats)]},
					pluck="heat_number",
				)
			)
			row.update({"reference_doctype": "MTC", "reference_name": mtcs[0], "source": "Auto"})
			row.remarks = ", ".join(mtcs)
			row.status = "Ready" if covered >= heats else "Pending"


def refresh_ready(doc):
	rows = [r for r in doc.pvfss_dispatch_documents if r.status != "N/A"]
	ready = sum(1 for r in rows if r.status == "Ready")
	doc.pvfss_documents_ready = f"{ready}/{len(rows)}"


def pending_documents(doc):
	return [r.document for r in doc.pvfss_dispatch_documents if r.required and r.status == "Pending"]


# ----------------------------------------------------------------------------- DSP-07
def marking_instructions(sales_order):
	"""Packing and marking instructions of the Supplier POs placed against the Customer PO."""
	pos = frappe.get_all(
		"Purchase Order Item",
		filters={"sales_order": sales_order, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)
	texts = []
	for po in sorted(set(pos)):
		text = frappe.db.get_value("Purchase Order", po, "pvfss_packing_instructions")
		if text and text not in texts:
			texts.append(text)
	return "\n".join(texts)


# ----------------------------------------------------------------------------- doc events
def validate(doc, method=None):
	if doc.is_return:
		return
	so = next((r.against_sales_order for r in doc.items if r.get("against_sales_order")), None)
	if so:
		values = frappe.db.get_value("Sales Order", so, ["po_no", "project"], as_dict=True)
		doc.pvfss_customer_po_no = doc.po_no or values.po_no
		doc.pvfss_project = doc.pvfss_project or values.project or doc.get("project")
		if not doc.get("pvfss_marking_instructions"):
			doc.pvfss_marking_instructions = marking_instructions(so)
	if doc.docstatus == 0:
		fill_documents(doc)
		result = gate(doc)
		doc.pvfss_dispatch_gate = _("OK") if result.ok else _("{0} issues").format(len(result.failures))
	state = doc.get("workflow_state")
	before = doc.get_doc_before_save()
	previous = before.get("workflow_state") if before else None
	if state != previous and state == DOCS_COMPLETE:
		pending = pending_documents(doc)
		if pending:
			frappe.throw(
				_("Cannot mark documents complete. Pending required documents: {0}.").format(
					"; ".join(pending)
				),
				title=_("Dispatch documents not ready"),
			)
	if state != previous and state == APPROVED:
		gate(doc).throw_if_failed()


def before_submit(doc, method=None):
	if doc.is_return:
		return
	gate(doc).throw_if_failed()  # re-checked on submit (SCR-DSP-02)


def on_update_after_submit(doc, method=None):
	"""DSP-09: recording the POD on a submitted DN marks it Delivered and drafts the invoice."""
	if doc.get("pvfss_pod_date") and not doc.get("pvfss_sales_invoice"):
		make_invoice(doc)


def make_invoice(doc):
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

	if not (doc.pvfss_received_by and doc.pvfss_pod_attachment):
		frappe.throw(_("Enter who received the goods and attach the POD."))
	si = make_sales_invoice(doc.name)
	si.flags.ignore_permissions = True
	si.insert()
	doc.db_set({"pvfss_sales_invoice": si.name, "workflow_state": DELIVERED}, update_modified=False)
	finance = alerts.users_with_role("Finance User", "Finance Manager")
	for user in finance[:1]:
		from frappe.desk.form.assign_to import add as assign

		assign(
			{
				"assign_to": [user],
				"doctype": "Sales Invoice",
				"name": si.name,
				"description": _("Draft invoice ready"),
			}
		)
	alerts.send(
		finance,
		_("Draft invoice {0} ready for {1} (POD {2}).").format(si.name, doc.name, doc.pvfss_pod_date),
		"Sales Invoice",
		si.name,
	)
	return si.name


@frappe.whitelist()
def record_pod(
	delivery_note: str, pod_date: str, received_by: str, pod_attachment: str, remarks: str | None = None
):
	"""SCR-DSP-05 Record POD."""
	doc = frappe.get_doc("Delivery Note", delivery_note)
	doc.check_permission("submit")
	if doc.docstatus != 1:
		frappe.throw(_("Submit the Delivery Note before recording the POD."))
	doc.pvfss_pod_date = pod_date
	doc.pvfss_received_by = received_by
	doc.pvfss_pod_attachment = pod_attachment
	doc.pvfss_delivery_remarks = remarks
	doc.save()
	return frappe.db.get_value("Delivery Note", delivery_note, "pvfss_sales_invoice")


@frappe.whitelist()
def check_gate(delivery_note: str):
	doc = frappe.get_doc("Delivery Note", delivery_note)
	doc.check_permission("read")
	result = gate(doc)
	for row in pending_documents(doc):
		result.fail(_("Document pending: {0}").format(row), rule="DSP-03")
	return result.as_dict()


# ----------------------------------------------------------------------------- DSP-10
def pod_alerts():
	"""Daily: ETA passed N days ago and no POD -> the project's Post-Bidding owner."""
	days = settings.get_int("pod_missing_days", 3)
	cutoff = add_days(nowdate(), -days)
	rows = frappe.get_all(
		"Delivery Note",
		filters={
			"docstatus": 1,
			"pvfss_eta": ["<=", cutoff],
			"pvfss_pod_date": ["is", "not set"],
			"pvfss_pod_alerted_on": ["is", "not set"],
			"is_return": 0,
		},
		fields=["name", "pvfss_eta", "pvfss_project", "owner"],
	)
	for row in rows:
		owner = row.pvfss_project and frappe.db.get_value(
			"Project", row.pvfss_project, "pvfss_post_bidding_owner"
		)
		subject = _("{0} - ETA {1} passed {2} days ago with no POD.").format(
			row.name, frappe.utils.formatdate(row.pvfss_eta), date_diff(nowdate(), row.pvfss_eta)
		)
		alerts.send([owner or row.owner], subject, "Delivery Note", row.name)
		frappe.db.set_value(
			"Delivery Note", row.name, "pvfss_pod_alerted_on", getdate(nowdate()), update_modified=False
		)
	return len(rows)
