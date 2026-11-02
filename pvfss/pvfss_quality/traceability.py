"""Heat number traceability (TRC-01 to TRC-13).

Movements come from ``Serial and Batch Entry`` rows, which carry the voucher, item, qty and
posting time for every batch in a bundle, so one indexed query answers a trace.
Later modules register extra stages (MTC, tally sheet, inspection, NCR, IRN) in ``STAGES``.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

BLOCKED = ("On hold", "Rejected")

# Extra trace stages added by later modules: dotted path -> fn(heats: list[str], batches: list[str])
# returning a list of node dicts {"stage", "doctype", "name", "status", "facts", "heat", "batch"}.
STAGES = [
	"pvfss.pvfss_quality.doctype.mtc.mtc.trace_nodes",  # 11-smr: MTC and Tally Sheet stages
]


# ----------------------------------------------------------------------------- TRC-01
def get_or_create_heat(heat_no, manufacturer, item_code, grade=None, mtc=None):
	"""Used by MTC heat rows and tally imports: the existing heat, or a new Active one."""
	from pvfss.pvfss_quality.doctype.heat_number.heat_number import clean_heat_no

	heat_no = clean_heat_no(heat_no)
	name = frappe.db.get_value("Heat Number", {"manufacturer": manufacturer, "heat_no": heat_no})
	if name:
		return name
	doc = frappe.get_doc(
		{
			"doctype": "Heat Number",
			"heat_no": heat_no,
			"manufacturer": manufacturer,
			"item_code": item_code,
			"grade": grade,
			"primary_mtc": mtc,
		}
	).insert(ignore_permissions=True)
	return doc.name


def is_heat_traceable(item_code):
	return cint(frappe.get_cached_value("Item", item_code, "pvfss_heat_traceable"))


# ----------------------------------------------------------------------------- batches on a document row
def row_batches(row):
	"""[(batch_no, qty)] for a stock transaction row (bundle or the legacy batch_no field)."""
	if row.get("serial_and_batch_bundle"):
		return [
			(r.batch_no, abs(flt(r.qty)))
			for r in frappe.get_all(
				"Serial and Batch Entry",
				filters={"parent": row.serial_and_batch_bundle},
				fields=["batch_no", "qty"],
			)
			if r.batch_no
		]
	if row.get("batch_no"):
		return [(row.batch_no, flt(row.stock_qty or row.qty))]
	return []


def batch_heats(batches):
	if not batches:
		return {}
	return {
		r.name: r
		for r in frappe.get_all(
			"Batch",
			filters={"name": ["in", list(set(batches))]},
			fields=["name", "item", "pvfss_heat_number", "pvfss_lot_no", "pvfss_supplier_po"],
		)
	}


# ----------------------------------------------------------------------------- TRC-03 / G6
def check_receipt(doc, result):
	"""G6: heat-traceable lines need batches, and every batch needs a heat number."""
	for row in doc.items:
		if not is_heat_traceable(row.item_code):
			continue
		ref = row.get("pvfss_customer_line_ref") or row.idx
		batches = row_batches(row)
		if not batches:
			result.fail(_("Line {0} ({1}): no batch.").format(ref, row.item_code), rule="TRC-03")
			continue
		info = batch_heats([b for b, _q in batches])
		missing = [b for b, _q in batches if not (info.get(b) and info[b].pvfss_heat_number)]
		if missing:
			result.fail(
				_("Line {0} ({1}): batch {2} has no heat number.").format(
					ref, row.item_code, ", ".join(missing)
				),
				rule="TRC-03",
			)


# ----------------------------------------------------------------------------- TRC-04
def blocked_heats(batches):
	"""{heat: status} for batches whose heat is On hold or Rejected."""
	heats = {r.pvfss_heat_number for r in batch_heats(batches).values() if r.pvfss_heat_number}
	if not heats:
		return {}
	return {
		r.name: r.status
		for r in frappe.get_all(
			"Heat Number",
			filters={"name": ["in", list(heats)], "status": ["in", BLOCKED]},
			fields=["name", "status"],
		)
	}


def check_release(doc, result, rule="TRC-04"):
	for row in doc.items:
		batches = [b for b, _q in row_batches(row)]
		for heat, status in blocked_heats(batches).items():
			result.fail(_("Line {0}: heat {1} is {2}.").format(row.idx, heat, _(status)), rule=rule)


def set_heat_status(heat, status, reason=None):
	"""Called by NCRs (12-quality): Major / Critical puts the heat On hold, closure returns it."""
	doc = frappe.get_doc("Heat Number", heat)
	doc.status = status
	doc.status_reason = reason
	doc.flags.ignore_permissions = True
	doc.save()


# ----------------------------------------------------------------------------- movements
def movements(batches):
	"""Every live Serial and Batch Entry for ``batches``."""
	if not batches:
		return []
	return frappe.db.sql(
		"""select batch_no, item_code, warehouse, qty, voucher_type, voucher_no, voucher_detail_no,
			type_of_transaction, posting_datetime
		from `tabSerial and Batch Entry`
		where batch_no in %(b)s and is_cancelled = 0 and docstatus = 1
		order by posting_datetime""",
		{"b": tuple(set(batches))},
		as_dict=True,
	)


def heat_summary(heat):
	batches = frappe.get_all("Batch", filters={"pvfss_heat_number": heat}, pluck="name")
	received = shipped = balance = 0.0
	for m in movements(batches):
		qty = flt(m.qty)
		balance += qty
		if m.voucher_type == "Purchase Receipt" and qty > 0:
			received += qty
		if m.voucher_type == "Delivery Note":
			shipped -= qty
	return {
		"batches": len(batches),
		"received": received,
		"shipped": shipped,
		"balance": balance,
		"open_ncrs": 0,  # 12-quality
	}


def refresh_heat_totals(heats):
	for heat in set(h for h in heats if h):
		s = heat_summary(heat)
		frappe.db.set_value(
			"Heat Number",
			heat,
			{
				"batch_count": s["batches"],
				"qty_received": s["received"],
				"qty_shipped": s["shipped"],
				"balance_qty": s["balance"],
			},
			update_modified=False,
		)


def refresh_for_document(doc, method=None):
	"""on_submit / on_cancel of stock documents: keep the heat totals in the list current."""
	batches = [b for row in doc.items for b, _q in row_batches(row)]
	refresh_heat_totals(r.pvfss_heat_number for r in batch_heats(batches).values())


# ----------------------------------------------------------------------------- TRC-10
SEARCH_TYPES = {
	"Heat Number": "forward",
	"Batch": "forward",
	"MTC No": "forward",
	"Supplier PO": "forward",
	"Customer PO": "backward",
	"Delivery Note": "backward",
	"Sales Invoice": "backward",
}


def _batches_for(search_type, key):
	"""Resolve a search key to (batches, heats)."""
	if search_type == "Heat Number":
		return frappe.get_all("Batch", filters={"pvfss_heat_number": key}, pluck="name"), [key]
	if search_type == "Batch":
		return [key], []
	if search_type == "MTC No":
		heats = frappe.get_all("Heat Number", filters={"primary_mtc": key}, pluck="name")
		return frappe.get_all(
			"Batch", filters={"pvfss_heat_number": ["in", heats or [""]]}, pluck="name"
		), heats
	if search_type == "Supplier PO":
		batches = set(frappe.get_all("Batch", filters={"pvfss_supplier_po": key}, pluck="name"))
		receipts = frappe.get_all(
			"Purchase Receipt Item",
			filters={"purchase_order": key, "docstatus": 1},
			pluck="parent",
			distinct=True,
		)
		batches |= set(_voucher_batches("Purchase Receipt", receipts))
		return list(batches), []
	if search_type == "Customer PO":
		dns = frappe.get_all(
			"Delivery Note Item",
			filters={"against_sales_order": key, "docstatus": 1},
			pluck="parent",
			distinct=True,
		)
		return _voucher_batches("Delivery Note", dns), []
	if search_type == "Delivery Note":
		return _voucher_batches("Delivery Note", [key]), []
	if search_type == "Sales Invoice":
		dns = frappe.get_all(
			"Sales Invoice Item", filters={"parent": key}, pluck="delivery_note", distinct=True
		)
		batches = _voucher_batches("Delivery Note", [d for d in dns if d])
		batches += _voucher_batches("Sales Invoice", [key])  # invoice that updates stock
		return batches, []
	frappe.throw(_("Unsupported search type {0}").format(search_type))


def _voucher_batches(voucher_type, names):
	names = [n for n in names or [] if n]
	if not names:
		return []
	return frappe.db.sql_list(
		"""select distinct batch_no from `tabSerial and Batch Entry`
		where voucher_type = %s and voucher_no in %s and is_cancelled = 0 and ifnull(batch_no, '') != ''""",
		(voucher_type, tuple(names)),
	)


def _node(stage, doctype, name, status=None, facts=None, **kw):
	return {"stage": stage, "doctype": doctype, "name": name, "status": status, "facts": facts or {}, **kw}


@frappe.whitelist()
def trace(search_type: str, key: str, direction: str | None = None):
	"""TRC-10: nodes per stage plus a flat table (one row per heat x lot x delivery)."""
	frappe.has_permission("Heat Number", "read", throw=True)
	started = frappe.utils.now_datetime()
	direction = direction or SEARCH_TYPES.get(search_type, "forward")
	batches, heats = _batches_for(search_type, key)
	info = batch_heats(batches)
	heats = sorted(set(heats) | {r.pvfss_heat_number for r in info.values() if r.pvfss_heat_number})
	moves = movements(list(info))
	stages = {}

	def add(node):
		stages.setdefault(node["stage"], {})[(node["doctype"], node["name"])] = node

	heat_rows = {
		h.name: h
		for h in frappe.get_all(
			"Heat Number",
			filters={"name": ["in", heats or [""]]},
			fields=[
				"name",
				"heat_no",
				"manufacturer",
				"item_code",
				"grade",
				"primary_mtc",
				"mtc_date",
				"status",
			],
		)
	}
	for h in heat_rows.values():
		add(
			_node(
				"Heat",
				"Heat Number",
				h.name,
				h.status,
				{"Mill": h.manufacturer, "Item": h.item_code, "Grade": h.grade},
			)
		)
		if h.primary_mtc and not frappe.db.exists("MTC Heat", {"heat_number": h.name, "docstatus": 1}):
			add(
				_node(
					"MTC",
					"Heat Number",
					h.name,
					None,
					{"MTC": h.primary_mtc, "Date": h.mtc_date},
					label=h.primary_mtc,
				)
			)
		add(_node("Supplier / mill", "Manufacturer", h.manufacturer))
	for b in info.values():
		add(
			_node(
				"Lot",
				"Batch",
				b.name,
				None,
				{"Heat": b.pvfss_heat_number, "Lot": b.pvfss_lot_no, "Item": b.item},
			)
		)
		if b.pvfss_supplier_po:
			add(_node("Supplier PO", "Purchase Order", b.pvfss_supplier_po))

	stock = {}
	deliveries = {}
	receipts = {}
	for m in moves:
		stock.setdefault((m.batch_no, m.warehouse), 0.0)
		stock[(m.batch_no, m.warehouse)] += flt(m.qty)
		if m.voucher_type == "Purchase Receipt":
			receipts.setdefault(m.voucher_no, set()).add(m.batch_no)
		if m.voucher_type in ("Delivery Note", "Sales Invoice"):
			deliveries.setdefault((m.voucher_type, m.voucher_no), {}).setdefault(m.batch_no, 0.0)
			deliveries[(m.voucher_type, m.voucher_no)][m.batch_no] += -flt(m.qty)

	for (batch, warehouse), qty in stock.items():
		if abs(qty) > 1e-9:
			add(
				_node(
					"Stock",
					"Warehouse",
					warehouse,
					None,
					{"Lot": batch, "Balance": qty},
					key=f"{batch}:{warehouse}",
				)
			)
	for pr in receipts:
		head = frappe.db.get_value(
			"Purchase Receipt", pr, ["supplier", "posting_date", "status"], as_dict=True
		)
		add(
			_node(
				"Receipt",
				"Purchase Receipt",
				pr,
				head.status,
				{"Supplier": head.supplier, "Date": head.posting_date},
			)
		)
		for po in frappe.get_all(
			"Purchase Receipt Item", filters={"parent": pr}, pluck="purchase_order", distinct=True
		):
			if po:
				add(_node("Supplier PO", "Purchase Order", po))
				supplier = frappe.db.get_value("Purchase Order", po, "supplier")
				add(_node("Supplier / mill", "Supplier", supplier))

	table = []
	for (vtype, vno), lots in deliveries.items():
		if vtype == "Delivery Note":
			head = frappe.db.get_value(
				"Delivery Note", vno, ["customer", "posting_date", "status"], as_dict=True
			)
			add(
				_node(
					"Delivery Note",
					"Delivery Note",
					vno,
					head.status,
					{"Customer": head.customer, "Date": head.posting_date},
				)
			)
			add(_node("Customer", "Customer", head.customer))
			sos = frappe.get_all(
				"Delivery Note Item", filters={"parent": vno}, pluck="against_sales_order", distinct=True
			)
			invoices = frappe.get_all(
				"Sales Invoice Item",
				filters={"delivery_note": vno, "docstatus": 1},
				pluck="parent",
				distinct=True,
			)
		else:
			head = frappe.db.get_value(
				"Sales Invoice", vno, ["customer", "posting_date", "status"], as_dict=True
			)
			sos = frappe.get_all(
				"Sales Invoice Item", filters={"parent": vno}, pluck="sales_order", distinct=True
			)
			invoices = [vno]
			add(_node("Customer", "Customer", head.customer))
		for so in sos:
			if so:
				add(
					_node(
						"Customer PO",
						"Sales Order",
						so,
						None,
						{"PO No": frappe.db.get_value("Sales Order", so, "po_no")},
					)
				)
		for si in invoices:
			add(
				_node(
					"Sales Invoice", "Sales Invoice", si, frappe.db.get_value("Sales Invoice", si, "status")
				)
			)
		for lot, qty in lots.items():
			b = info.get(lot) or frappe._dict()
			h = heat_rows.get(b.get("pvfss_heat_number")) or frappe._dict()
			table.append(
				{
					"heat": b.get("pvfss_heat_number"),
					"lot": lot,
					"mtc": h.get("primary_mtc"),
					"mtc_date": h.get("mtc_date"),
					"delivery": vno if vtype == "Delivery Note" else None,
					"customer": head.customer,
					"customer_po": ", ".join(s for s in sos if s),
					"invoice": ", ".join(invoices),
					"qty": qty,
				}
			)
	delivered_lots = {lot for lots in deliveries.values() for lot in lots}
	for lot, b in info.items():
		if lot not in delivered_lots:
			h = heat_rows.get(b.pvfss_heat_number) or frappe._dict()
			table.append(
				{
					"heat": b.pvfss_heat_number,
					"lot": lot,
					"mtc": h.get("primary_mtc"),
					"mtc_date": h.get("mtc_date"),
				}
			)

	for path in STAGES:
		for node in frappe.get_attr(path)(heats, list(info)) or []:
			add(node)

	order = FORWARD if direction == "forward" else BACKWARD
	columns = [{"stage": s, "nodes": list(stages.get(s, {}).values())} for s in order]
	missing = []
	if info and not receipts:
		missing.append(_("No receipt found"))
	return {
		"search_type": search_type,
		"key": key,
		"direction": direction,
		"heats": len(heats),
		"lots": len(info),
		"deliveries": len(deliveries),
		"columns": columns,
		"table": table,
		"missing": missing,
		"seconds": (frappe.utils.now_datetime() - started).total_seconds(),
	}


FORWARD = [
	"Heat",
	"MTC",
	"Lot",
	"Stock",
	"Receipt",
	"IRN",
	"Delivery Note",
	"Customer",
	"Customer PO",
	"Sales Invoice",
]
BACKWARD = [
	"Sales Invoice",
	"Delivery Note",
	"Lot",
	"Heat",
	"MTC",
	"Tally Sheet",
	"Inspection",
	"NCR",
	"IRN",
	"Receipt",
	"Supplier PO",
	"Supplier / mill",
	"Customer",
	"Customer PO",
]


# ----------------------------------------------------------------------------- TRC-11
def report_html(result):
	# The template is a file shipped with this app, never user input; values are escaped by Jinja.
	return frappe.render_template(  # nosemgrep: frappe-ssti
		"pvfss/templates/print/traceability_report.html",
		{"r": result, "user": frappe.session.user, "now": frappe.utils.now_datetime()},
	)


@frappe.whitelist()
def download_report(search_type: str, key: str, direction: str | None = None):
	from frappe.utils.pdf import get_pdf

	result = trace(search_type, key, direction)
	frappe.local.response.filename = f"Traceability-{frappe.scrub(key)}.pdf"
	frappe.local.response.filecontent = get_pdf(report_html(result))
	frappe.local.response.type = "download"


def certificate_files(result):
	"""Attachments of every document in the trace (MTCs, reports, IRNs and dispatch documents)."""
	docs = {(n["doctype"], n["name"]) for c in result["columns"] for n in c["nodes"]}
	docs = {d for d in docs if d[0] not in ("Warehouse", "Customer", "Supplier", "Manufacturer")}
	files = []
	for doctype, name in sorted(docs):
		for f in frappe.get_all(
			"File",
			filters={"attached_to_doctype": doctype, "attached_to_name": name, "is_folder": 0},
			fields=["name", "file_name", "file_url", "is_private"],
		):
			files.append(frappe._dict(f, doctype=doctype, docname=name))
	return files


def build_zip(result, pdf=None):
	import io
	import zipfile

	buf = io.BytesIO()
	heat_of = {}
	for c in result["columns"]:
		for n in c["nodes"]:
			heat = (n.get("facts") or {}).get("Heat") or (
				n["name"] if n["doctype"] == "Heat Number" else None
			)
			if heat:
				heat_of[(n["doctype"], n["name"])] = heat
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
		if pdf:
			z.writestr("00-index.pdf", pdf)
		for f in certificate_files(result):
			folder = heat_of.get((f.doctype, f.docname)) or f.doctype
			try:
				content = frappe.get_doc("File", f.name).get_content()
			except Exception:
				continue
			if isinstance(content, str):
				content = content.encode()
			z.writestr(f"{folder}/{f.docname}/{f.file_name}", content)
	return buf.getvalue()


@frappe.whitelist()
def download_certificate_pack(search_type: str, key: str, direction: str | None = None):
	from frappe.utils.pdf import get_pdf

	result = trace(search_type, key, direction)
	frappe.local.response.filename = f"Certificates-{frappe.scrub(key)}.zip"
	frappe.local.response.filecontent = build_zip(result, get_pdf(report_html(result)))
	frappe.local.response.type = "download"
