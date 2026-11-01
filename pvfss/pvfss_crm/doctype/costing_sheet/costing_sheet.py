# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from pvfss.pvfss_crm import inquiry as inq
from pvfss.pvfss_crm import selection
from pvfss.pvfss_crm.doctype.technical_evaluation import technical_evaluation as te_module
from pvfss.utils import settings

# Cost type (Costing Allocation.cost_type) -> per-unit field on Costing Sheet Item
COST_FIELDS = {
	"Freight": "freight",
	"Inspection / TPI": "inspection",
	"Documentation": "documentation",
	"Testing": "testing",
	"Finance cost": "finance_cost",
	"Contingency": "contingency",
}
TE_LABEL = {
	"Compliant": "Compliant",
	"Compliant with deviation": "Deviation",
	"Not compliant": "Not compliant",
}
KEEP_ON_REFRESH = ("weight_per_unit", "selling_price", *COST_FIELDS.values())


class CostingSheet(Document):
	"""Landed cost, target price and selling price per inquiry (RFQ-10, SCR-RFQ-10)."""

	def onload(self):
		self.set_onload("min_margin", settings.get_float("min_target_margin_pct"))

	def before_insert(self):
		if self.amended_from:
			self.revision = cint(frappe.db.get_value("Costing Sheet", self.amended_from, "revision")) + 1

	def validate(self):
		if self.target_margin_pct in (None, ""):
			self.target_margin_pct = settings.get_float("min_target_margin_pct")
		if flt(self.target_margin_pct) >= 100:
			frappe.throw(_("Target margin must be below 100%."))
		self.check_one_per_inquiry()
		if not self.items:
			self.refresh_from_selection()
		self.calculate()

	def after_insert(self):
		inq.advance(self.inquiry, inq.UNDER_EVALUATION, source=self.name)

	def check_one_per_inquiry(self):
		other = frappe.db.get_value(
			"Costing Sheet",
			{"inquiry": self.inquiry, "docstatus": ["<", 2], "name": ["!=", self.name or ""]},
			"name",
		)
		if other:
			frappe.throw(
				_("Inquiry {0} already has Costing Sheet {1}. Amend it to make a new revision.").format(
					self.inquiry, other
				)
			)

	@frappe.whitelist()
	def refresh_from_selection(self):
		"""Rebuild the lines from the selected supplier quotation lines, keeping manual inputs."""
		previous = {r.supplier_quotation_item: r for r in self.items}
		inquiry_lines = {
			r.pvfss_customer_line_ref: r
			for r in frappe.get_all(
				"Opportunity Item",
				filters={"parent": self.inquiry, "parenttype": "Opportunity"},
				fields=[
					"pvfss_customer_line_ref",
					"pvfss_specification",
					"description",
					"qty",
					"uom",
					"item_code",
					"pvfss_material_type",
					"pvfss_product_category",
					"pvfss_inspection_req",
					"pvfss_doc_req",
					"idx",
				],
				order_by="idx",
			)
		}
		chosen = selection.selected_lines(self.inquiry)
		if not chosen:
			frappe.throw(
				_(
					"No supplier lines are selected for inquiry {0}. Select them on the Competitive Statement."
				).format(self.inquiry)
			)
		self.set("items", [])
		order = sorted(
			chosen,
			key=lambda ref: (
				inquiry_lines.get(ref).idx if inquiry_lines.get(ref) else 10**6,
				selection._ref_key(ref),
			),
		)
		for ref in order:
			line = chosen[ref]
			src = inquiry_lines.get(ref) or frappe._dict()
			row = {
				"line_ref": ref,
				"item_code": line.item_code,
				"specification": src.pvfss_specification or src.description,
				"qty": src.qty or line.qty,
				"uom": src.uom or line.uom,
				"material_type": src.pvfss_material_type,
				"product_category": src.pvfss_product_category,
				"inspection_req": src.pvfss_inspection_req,
				"doc_req": src.pvfss_doc_req,
				"supplier": line.supplier,
				"supplier_quotation": line.supplier_quotation,
				"supplier_quotation_item": line.sq_item,
				"supplier_currency": line.currency,
				"supplier_rate": flt(line.rate),
				"exchange_rate": flt(line.conversion_rate) or 1,
				"lead_time_days": cint(line.lead_time_days),
				"weight_per_unit": frappe.db.get_value("Item", line.item_code, "weight_per_unit") or 0,
			}
			old = previous.get(line.sq_item)
			if old:
				for field in KEEP_ON_REFRESH:
					row[field] = old.get(field)
			self.append("items", row)
		if not self.is_new():
			self.calculate()

	def calculate(self):
		_te, status = te_module.status_by_sq_item(self.inquiry)
		for row in self.items:
			row.currency = self.currency or "AED"
			row.exchange_rate = flt(row.exchange_rate) or 1
			row.unit_cost = flt(row.supplier_rate) * flt(row.exchange_rate)
			row.technical_status = TE_LABEL.get(status.get(row.supplier_quotation_item)) or ""
		self.apply_allocations()

		margin = flt(self.target_margin_pct) / 100.0
		totals = frappe._dict(supplier=0.0, alloc=0.0, landed=0.0, selling=0.0)
		for row in self.items:
			extras = sum(flt(row.get(f)) for f in COST_FIELDS.values())
			row.landed_unit_cost = flt(row.unit_cost) + extras
			previous_target = flt(row.target_price)
			row.target_price = flt(row.landed_unit_cost / (1 - margin), 4)
			# The selling price follows the target until the user overrides it
			if not flt(row.selling_price) or abs(flt(row.selling_price) - previous_target) < 0.00005:
				row.selling_price = row.target_price
			row.line_margin = (flt(row.selling_price) - flt(row.landed_unit_cost)) * flt(row.qty)
			row.line_margin_pct = (
				(flt(row.selling_price) - flt(row.landed_unit_cost)) * 100.0 / flt(row.selling_price)
				if flt(row.selling_price)
				else 0
			)
			totals.supplier += flt(row.unit_cost) * flt(row.qty)
			totals.alloc += extras * flt(row.qty)
			totals.landed += flt(row.landed_unit_cost) * flt(row.qty)
			totals.selling += flt(row.selling_price) * flt(row.qty)
		self.total_supplier_cost = flt(totals.supplier, 2)
		self.total_allocations = flt(totals.alloc, 2)
		self.total_landed_cost = flt(totals.landed, 2)
		self.selling_value = flt(totals.selling, 2)
		self.margin_amount = flt(totals.selling - totals.landed, 2)
		self.margin_pct = flt(self.margin_amount * 100.0 / totals.selling, 2) if totals.selling else 0
		self.non_compliant_lines = sum(1 for r in self.items if r.technical_status == "Not compliant")

	@frappe.whitelist()
	def apply_allocations(self):
		"""Spread each allocation over the lines by value or weight; Manual leaves lines alone."""
		total_value = sum(flt(r.unit_cost) * flt(r.qty) for r in self.items)
		total_weight = sum(flt(r.weight_per_unit) * flt(r.qty) for r in self.items)
		amounts = {}
		for alloc in self.allocations or []:
			field = COST_FIELDS[alloc.cost_type]
			if alloc.method == "Manual":
				amounts.setdefault(field, None)
				alloc.allocated_amount = sum(flt(r.get(field)) * flt(r.qty) for r in self.items)
				continue
			amount = flt(alloc.value) if alloc.basis == "Amount" else total_value * flt(alloc.value) / 100.0
			alloc.allocated_amount = flt(amount, 2)
			method = alloc.method
			if method == "By weight" and not total_weight:
				frappe.msgprint(
					_("{0}: no line weights entered, allocated by value instead.").format(_(alloc.cost_type)),
					indicator="orange",
					alert=True,
				)
				method = "By value"
			current = amounts.get(field) or {}
			for row in self.items:
				if not flt(row.qty):
					continue
				if method == "By weight":
					share = flt(row.weight_per_unit) * flt(row.qty) / total_weight
				else:
					share = flt(row.unit_cost) * flt(row.qty) / total_value if total_value else 0
				current[row.name or row.idx] = current.get(row.name or row.idx, 0) + amount * share / flt(
					row.qty
				)
			amounts[field] = current
		for field, per_row in amounts.items():
			if per_row is None:
				continue
			for row in self.items:
				row.set(field, flt(per_row.get(row.name or row.idx, 0), 4))


@frappe.whitelist()
def make_or_refresh(inquiry):
	"""Open the inquiry's Costing Sheet: refresh a draft, return a submitted one, or create one."""
	frappe.has_permission("Costing Sheet", "create", throw=True)
	existing = frappe.db.get_value(
		"Costing Sheet", {"inquiry": inquiry, "docstatus": ["<", 2]}, ["name", "docstatus"], as_dict=True
	)
	if existing and existing.docstatus == 1:
		return existing.name
	if existing:
		doc = frappe.get_doc("Costing Sheet", existing.name)
		doc.refresh_from_selection()
		doc.save()
		return doc.name
	doc = frappe.new_doc("Costing Sheet")
	doc.inquiry = inquiry
	doc.refresh_from_selection()
	doc.insert()
	return doc.name
