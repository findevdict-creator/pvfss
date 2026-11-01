# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from pvfss.pvfss_purchasing import project as project_module


class ExpeditingLog(Document):
	"""One per Supplier PO (PRJ-20); status and delivery risk (PRJ-21)."""

	def validate(self):
		if not self.supplier and self.purchase_order:
			self.supplier = frappe.db.get_value("Purchase Order", self.purchase_order, "supplier")
		before = self.get_doc_before_save()
		if before and before.supply_route != self.supply_route:
			if any(r.actual_date for r in self.milestones):
				frappe.throw(_("The supply route cannot change after a milestone has an actual date."))
			ready = frappe.db.get_value("Purchase Order", self.purchase_order, "schedule_date")
			project_module.seed_milestones(self, ready)
		if not self.milestones:
			ready = frappe.db.get_value("Purchase Order", self.purchase_order, "schedule_date")
			project_module.seed_milestones(self, ready)
		project_module.refresh_log(self)

	def on_update(self):
		if self.project:
			sync_route(self)
			project_module.update_project_risk(self.project)


def sync_route(log):
	for name in frappe.get_all(
		"Project Supply Route",
		filters={"parent": log.project, "parenttype": "Project", "purchase_order": log.purchase_order},
		pluck="name",
	):
		frappe.db.set_value(
			"Project Supply Route", name, "supply_route", log.supply_route, update_modified=False
		)
