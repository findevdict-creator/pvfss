"""Supplier Performance (RPT-07, SUP-06, SCR-RPT-08)."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate


def _period(filters):
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or add_days(to_date, -365))
	return from_date, to_date


def _suppliers(filters):
	conditions = {"disabled": 0}
	if filters.get("supplier_group"):
		conditions["supplier_group"] = filters["supplier_group"]
	if filters.get("supplier"):
		conditions["name"] = filters["supplier"]
	names = frappe.get_all("Supplier", filters=conditions, pluck="name")
	if filters.get("product_category"):
		names = set(names) & set(
			frappe.get_all(
				"Supplier Product Category",
				filters={"parenttype": "Supplier", "product_category": filters["product_category"]},
				pluck="parent",
			)
		)
	return set(names)


def _on_time(suppliers, period):
	"""Lines received / received by the PO line schedule date, per supplier."""
	rows = frappe.db.sql(
		"""select po.supplier, poi.name, poi.schedule_date, min(pr.posting_date) as received
		from `tabPurchase Order Item` poi
		join `tabPurchase Order` po on po.name = poi.parent
		join `tabPurchase Receipt Item` pri on pri.purchase_order_item = poi.name
		join `tabPurchase Receipt` pr on pr.name = pri.parent and pr.docstatus = 1
		where po.docstatus = 1 and po.transaction_date between %s and %s
		group by po.supplier, poi.name, poi.schedule_date""",
		period,
		as_dict=True,
	)
	out = {}
	for r in rows:
		if r.supplier not in suppliers:
			continue
		total, on_time = out.get(r.supplier, (0, 0))
		out[r.supplier] = (total + 1, on_time + (1 if getdate(r.received) <= getdate(r.schedule_date) else 0))
	return out


def _lowest_share(suppliers, period):
	"""Share of RFQs (with two or more quotes) where the supplier quoted lowest."""
	rows = frappe.db.sql(
		"""select sq.name, sq.supplier, sq.base_net_total, min(sqi.request_for_quotation) as rfq
		from `tabSupplier Quotation` sq join `tabSupplier Quotation Item` sqi on sqi.parent = sq.name
		where sq.docstatus = 1 and sq.transaction_date between %s and %s and ifnull(sqi.request_for_quotation, '') != ''
		group by sq.name, sq.supplier, sq.base_net_total""",
		period,
		as_dict=True,
	)
	by_rfq = {}
	for r in rows:
		by_rfq.setdefault(r.rfq, []).append(r)
	quoted, lowest = {}, {}
	for quotes in by_rfq.values():
		if len({q.supplier for q in quotes}) < 2:
			continue
		best = min(flt(q.base_net_total) for q in quotes)
		for supplier in {q.supplier for q in quotes}:
			quoted[supplier] = quoted.get(supplier, 0) + 1
			if any(q.supplier == supplier and flt(q.base_net_total) == best for q in quotes):
				lowest[supplier] = lowest.get(supplier, 0) + 1
	return {s: (quoted[s], lowest.get(s, 0)) for s in quoted if s in suppliers}


def _count_by(doctype, field, filters):
	out = {}
	for value in frappe.get_all(doctype, filters=filters, pluck=field):
		out[value] = out.get(value, 0) + 1
	return out


def get_rows(filters):
	filters = frappe._dict(filters or {})
	period = _period(filters)
	between = ["between", list(period)]
	suppliers = _suppliers(filters)
	pos = _count_by("Purchase Order", "supplier", {"docstatus": 1, "transaction_date": between})
	ncrs = _count_by("Non Conformance", "pvfss_supplier", {"pvfss_raised_on": between})
	rfqs = {}
	for supplier in frappe.db.sql(
		"""select rs.supplier from `tabRequest for Quotation Supplier` rs
		join `tabRequest for Quotation` r on r.name = rs.parent
		where r.docstatus = 1 and r.transaction_date between %s and %s""",
		period,
		pluck=True,
	):
		rfqs[supplier] = rfqs.get(supplier, 0) + 1
	quotes = _count_by("Supplier Quotation", "supplier", {"docstatus": 1, "transaction_date": between})
	on_time = _on_time(suppliers, period)
	lowest = _lowest_share(suppliers, period)
	evaluations = {}
	for r in frappe.get_all(
		"Supplier Evaluation",
		filters={"docstatus": 1, "evaluation_date": between},
		fields=["supplier", "weighted_total"],
	):
		evaluations.setdefault(r.supplier, []).append(flt(r.weighted_total))
	standing = {}
	if frappe.db.exists("DocType", "Supplier Scorecard"):
		standing = dict(frappe.get_all("Supplier Scorecard", fields=["supplier", "status"], as_list=True))

	rows = []
	for supplier in sorted(suppliers):
		active = pos.get(supplier) or rfqs.get(supplier) or quotes.get(supplier) or ncrs.get(supplier)
		if not active:
			continue
		received, timely = on_time.get(supplier, (0, 0))
		n_quoted, n_lowest = lowest.get(supplier, (0, 0))
		evals = evaluations.get(supplier, [])
		po_count = pos.get(supplier, 0)
		rows.append(
			{
				"supplier": supplier,
				"pos": po_count,
				"lines_received": received,
				"on_time_pct": flt(timely * 100 / received, 1) if received else 0,
				"ncrs": ncrs.get(supplier, 0),
				"ncr_rate": flt(ncrs.get(supplier, 0) / po_count, 2) if po_count else 0,
				"rfqs": rfqs.get(supplier, 0),
				"quotes": quotes.get(supplier, 0),
				"lowest_share": flt(n_lowest * 100 / n_quoted, 1) if n_quoted else 0,
				"evaluation": flt(sum(evals) / len(evals), 1) if evals else None,
				"standing": standing.get(supplier),
			}
		)
	return rows


def execute(filters=None):
	rows = get_rows(filters)
	columns = [
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 200,
		},
		{"fieldname": "pos", "label": _("POs"), "fieldtype": "Int", "width": 70},
		{"fieldname": "lines_received", "label": _("Lines received"), "fieldtype": "Int", "width": 100},
		{"fieldname": "on_time_pct", "label": _("On-time delivery %"), "fieldtype": "Percent", "width": 120},
		{"fieldname": "ncrs", "label": _("NCRs"), "fieldtype": "Int", "width": 70},
		{"fieldname": "ncr_rate", "label": _("NCR rate"), "fieldtype": "Float", "width": 90},
		{"fieldname": "rfqs", "label": _("RFQs received"), "fieldtype": "Int", "width": 100},
		{"fieldname": "quotes", "label": _("Quotes submitted"), "fieldtype": "Int", "width": 110},
		{
			"fieldname": "lowest_share",
			"label": _("Lowest-quote share %"),
			"fieldtype": "Percent",
			"width": 130,
		},
		{"fieldname": "evaluation", "label": _("Evaluation average"), "fieldtype": "Float", "width": 120},
		{"fieldname": "standing", "label": _("Scorecard standing"), "fieldtype": "Data", "width": 130},
	]
	rated = [r for r in rows if r["lines_received"]]
	summary = [
		{
			"label": _("Suppliers evaluated"),
			"value": len([r for r in rows if r["evaluation"] is not None]),
			"datatype": "Int",
		},
		{
			"label": _("Average on-time %"),
			"value": flt(sum(r["on_time_pct"] for r in rated) / len(rated), 1) if rated else 0,
			"datatype": "Percent",
		},
		{
			"label": _("NCR rate (NCRs per PO)"),
			"value": flt(sum(r["ncrs"] for r in rows) / max(sum(r["pos"] for r in rows), 1), 2),
			"datatype": "Float",
		},
		{
			"label": _("Average lowest-quote share"),
			"value": flt(
				sum(r["lowest_share"] for r in rows if r["quotes"])
				/ max(len([r for r in rows if r["quotes"]]), 1),
				1,
			),
			"datatype": "Percent",
		},
	]
	top = sorted(rows, key=lambda r: r["pos"], reverse=True)[:10]
	chart = {
		"data": {
			"labels": [r["supplier"] for r in top],
			"datasets": [
				{"name": _("On-time %"), "values": [r["on_time_pct"] for r in top]},
				{"name": _("NCRs per PO"), "values": [r["ncr_rate"] for r in top]},
			],
		},
		"type": "bar",
	}
	return columns, rows, None, chart, summary
