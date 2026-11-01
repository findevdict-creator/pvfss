"""G3: Supplier PO compliance with the Customer PO (PUR-02 to PUR-07, PUR-10, SUP-03, SUP-07).

``refresh(po)`` rebuilds the PO Compliance Lines, margins, over-ordering and approval route
on every save. ``check(po)`` is the submit gate.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate

from pvfss.gates.base import GateResult
from pvfss.pvfss_crm import supplier_rules
from pvfss.utils import settings

APPROVED = "Approved"
VALUE = "Value Approval"
DIRECTOR = "Director Approval"
MGR_ROLES = ("Post-Bidding Manager", "System Manager")


# ----------------------------------------------------------------------------- helpers
def so_lines(po):
	names = [r.sales_order_item for r in po.items if r.get("sales_order_item")]
	if not names:
		return {}
	rows = frappe.get_all(
		"Sales Order Item",
		filters={"name": ["in", names]},
		fields=[
			"name",
			"parent",
			"item_code",
			"qty",
			"stock_qty",
			"uom",
			"delivery_date",
			"base_net_rate",
			"base_net_amount",
			"pvfss_customer_line_ref",
			"pvfss_specification",
			"pvfss_inspection_req",
			"pvfss_doc_req",
		],
	)
	return {r.name: r for r in rows}


def ordered_elsewhere(so_item, exclude_po):
	"""Stock qty of this SO line on other live (draft or submitted) Supplier POs."""
	return flt(
		frappe.db.sql(
			"""select sum(poi.stock_qty) from `tabPurchase Order Item` poi
			join `tabPurchase Order` po on po.name = poi.parent
			where poi.sales_order_item = %s and po.docstatus < 2 and po.name != %s""",
			(so_item, exclude_po or ""),
		)[0][0]
	)


def _text(value):
	return " ".join(str(value or "").split())


def _credit_days(template):
	if not template:
		return None
	days = frappe.get_all("Payment Terms Template Detail", filters={"parent": template}, pluck="credit_days")
	return max([cint(d) for d in days] or [0])


# ----------------------------------------------------------------------------- refresh
def refresh(po):
	old = {r.key: r.justification for r in po.get("pvfss_compliance") or [] if r.key}
	po.set("pvfss_compliance", [])
	lines = so_lines(po)
	so_name = po.get("pvfss_sales_order") or next((r.parent for r in lines.values()), None)
	buffer = settings.get_int("default_transit_buffer_days", 0)
	tolerance = settings.get_float("over_ordering_tolerance_pct", 0)

	def add(level, ref, check, so_value, po_value, result, key):
		po.append(
			"pvfss_compliance",
			{
				"level": level,
				"line_ref": ref,
				"check": check,
				"so_value": _text(so_value),
				"po_value": _text(po_value),
				"result": result,
				"key": key,
				"justification": old.get(key) if result != "Match" else None,
			},
		)

	over = 0
	margin_total = so_total = 0.0
	negatives = []
	for row in po.items:
		so = lines.get(row.get("sales_order_item"))
		if not so:
			continue
		ref = row.pvfss_customer_line_ref or so.pvfss_customer_line_ref or str(row.idx)
		k = f"{so.name}:"
		same_item = row.item_code == so.item_code and _text(row.pvfss_specification) == _text(
			so.pvfss_specification
		)
		add(
			"Line",
			ref,
			"Item / spec",
			f"{so.item_code} {so.pvfss_specification or ''}",
			f"{row.item_code} {row.pvfss_specification or ''}",
			"Match" if same_item else "Deviation",
			k + "item",
		)

		other = ordered_elsewhere(so.name, po.name)
		this_qty = flt(row.stock_qty) or flt(row.qty) * flt(row.conversion_factor or 1)
		remaining = flt(so.stock_qty) - other
		allowed = flt(so.stock_qty) * (1 + tolerance / 100.0)
		if other + this_qty > allowed + 1e-9:
			over += 1
			add(
				"Line",
				ref,
				"Over-ordering",
				_("{0} + {1}% tolerance").format(flt(so.stock_qty), tolerance),
				_("{0} here + {1} on other POs").format(this_qty, other),
				"Deviation",
				k + "over",
			)
		else:
			add(
				"Line",
				ref,
				"Quantity",
				_("{0} (remaining {1})").format(flt(so.stock_qty), remaining),
				this_qty,
				"Match" if this_qty >= remaining - 1e-9 else "Deviation",
				k + "qty",
			)

		add("Line", ref, "UOM", so.uom, row.uom, "Match" if so.uom == row.uom else "Deviation", k + "uom")

		if so.delivery_date and row.schedule_date:
			arrival = add_days(getdate(row.schedule_date), buffer)
			ok = getdate(arrival) <= getdate(so.delivery_date)
			add(
				"Line",
				ref,
				"Delivery date",
				frappe.utils.formatdate(so.delivery_date),
				_("{0} + {1} days transit").format(frappe.utils.formatdate(row.schedule_date), buffer),
				"Match" if ok else "Deviation",
				k + "date",
			)
		for check, field in (("Inspection req", "pvfss_inspection_req"), ("Document req", "pvfss_doc_req")):
			so_v, po_v = _text(so.get(field)), _text(row.get(field))
			add("Line", ref, check, so_v, po_v, "Match" if so_v == po_v else "Deviation", k + field)

		# PUR-06 margin per stock unit, in AED
		po_unit = flt(row.base_net_amount) / this_qty if this_qty else 0
		so_unit = flt(so.base_net_amount) / flt(so.stock_qty) if flt(so.stock_qty) else 0
		row.pvfss_so_rate = so_unit * flt(row.conversion_factor or 1)
		row.pvfss_line_margin = (so_unit - po_unit) * this_qty
		row.pvfss_line_margin_pct = (so_unit - po_unit) * 100.0 / so_unit if so_unit else 0
		margin_total += row.pvfss_line_margin
		so_total += so_unit * this_qty
		if row.pvfss_line_margin < -0.005:
			negatives.append(ref)

	if so_name:
		so = frappe.db.get_value("Sales Order", so_name, ["incoterm", "payment_terms_template"], as_dict=True)
		if so.incoterm or po.incoterm:
			if so.incoterm == po.incoterm:
				result = "Match"
			elif so.incoterm and not po.incoterm:
				result = "Deviation"
			else:
				result = "Flag"  # different terms: PVFSS covers the leg in between
			add("Header", "", "Incoterm", so.incoterm, po.incoterm, result, "h:incoterm")
		so_days, po_days = _credit_days(so.payment_terms_template), _credit_days(po.payment_terms_template)
		if so_days is not None and po_days is not None:
			add(
				"Header",
				"",
				"Payment terms",
				_("{0} days").format(so_days),
				_("{0} days").format(po_days),
				"Flag" if po_days < so_days else "Match",
				"h:payment",
			)

	po.pvfss_deviation_count = sum(1 for r in po.pvfss_compliance if r.result == "Deviation")
	po.pvfss_flag_count = sum(1 for r in po.pvfss_compliance if r.result == "Flag")
	po.pvfss_over_order_lines = over
	if not po.pvfss_compliance:
		po.pvfss_compliance_status = _("Not linked to a Customer PO")
	elif po.pvfss_deviation_count:
		po.pvfss_compliance_status = _("{0} deviations - justification required").format(
			po.pvfss_deviation_count
		)
	else:
		po.pvfss_compliance_status = _("All checks match")

	po.pvfss_margin_amount = flt(margin_total, 2)
	po.pvfss_margin_pct = flt(margin_total * 100.0 / so_total, 2) if so_total else 0
	po.pvfss_negative_margin_lines = ", ".join(negatives)
	po.pvfss_approval_route = approval_route(po, bool(negatives))


def approval_route(po, negative_margin):
	"""PUR-10: Director at or above the value threshold or with a negative-margin line."""
	threshold = settings.get_float("spo_value_approval_threshold")
	if negative_margin or (threshold and flt(po.base_grand_total) >= threshold):
		return DIRECTOR
	return VALUE


# ----------------------------------------------------------------------------- rules
def check_locked_links(po):
	"""PUR-02 [RULE]: SO and supplier quotation links cannot change after creation."""
	if po.is_new():
		return
	saved = {
		r.name: r
		for r in frappe.get_all(
			"Purchase Order Item",
			filters={"parent": po.name},
			fields=[
				"name",
				"sales_order",
				"sales_order_item",
				"supplier_quotation",
				"supplier_quotation_item",
			],
		)
	}
	for row in po.items:
		before = saved.get(row.name)
		if not before:
			continue
		for field in ("sales_order", "sales_order_item", "supplier_quotation", "supplier_quotation_item"):
			if (row.get(field) or None) != (before.get(field) or None):
				frappe.throw(
					_("Row {0}: {1} cannot be changed after the Supplier PO is created.").format(
						row.idx, _(frappe.get_meta("Purchase Order Item").get_label(field))
					),
					title=_("Locked link"),
				)


def check_avl_ref_role(po):
	before = po.get_doc_before_save()
	old = before.get("pvfss_avl_customer_approval_ref") if before else None
	if (po.get("pvfss_avl_customer_approval_ref") or None) != (old or None):
		if not set(frappe.get_roles()) & set(MGR_ROLES):
			frappe.throw(
				_("Only a Post-Bidding Manager can record the AVL customer approval reference."),
				frappe.PermissionError,
			)


def avl_gaps(po):
	client_project = po.get("pvfss_client_project")
	categories = [r.pvfss_product_category or r.item_group for r in po.items]
	return supplier_rules.avl_gaps(client_project, po.supplier, categories)


def check(po, require_approval=True):
	"""The G3 submit gate: collects every failure."""
	result = GateResult(_("Supplier PO cannot be submitted"), doc=po, gate="G3")
	supplier_rules.check_status(result, po.supplier, rule="SUP-07")
	gaps = avl_gaps(po)
	if gaps and not po.get("pvfss_avl_customer_approval_ref"):
		for category in gaps:
			result.fail(
				supplier_rules.avl_message(po.supplier, po.pvfss_client_project, category)
				+ " "
				+ _("Record the customer approval reference."),
				rule="SUP-03",
			)
	for row in po.get("pvfss_compliance") or []:
		if row.result == "Deviation" and not (row.justification or "").strip():
			result.fail(
				_("Line {0} {1}: deviation needs a justification.").format(row.line_ref or "-", _(row.check)),
				rule="PUR-05",
			)
	if require_approval:
		before = po.get_doc_before_save()
		result.check(
			before is not None and before.get("workflow_state") == APPROVED,
			_("The Supplier PO must be approved ({0}).").format(_(po.pvfss_approval_route or VALUE)),
			rule="PUR-10",
		)
	return result
