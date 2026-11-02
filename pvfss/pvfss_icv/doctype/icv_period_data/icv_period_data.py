# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from pvfss.pvfss_icv import icv


class ICVPeriodData(Document):
	"""Inputs and estimate for one financial year (ICV-10)."""

	def validate(self):
		before = self.get_doc_before_save()
		if before and before.status == "Final" and self.status == "Final":
			frappe.throw(_("Final ICV data cannot be changed. Set it back to Draft first."))
		for key in icv.AUTO_METRICS:
			override = self.get(f"{key}_override")
			self.set(
				key, override if override not in (None, "") and flt(override) else self.get(f"{key}_auto")
			)
		self.compute()

	def compute(self):
		weights = {r.component: flt(r.weight_pct) for r in frappe.get_single("ICV Settings").components}
		scores = icv.component_scores(self)
		self.set("component_scores", [])
		total = 0.0
		for component, weight in weights.items():
			score = flt(scores.get(component), 2)
			contribution = flt(score * weight / 100, 2)
			total += contribution
			self.append(
				"component_scores",
				{
					"component": component,
					"score_pct": score,
					"weight_pct": weight,
					"contribution_pct": contribution,
				},
			)
		self.estimated_icv_pct = flt(total, 2)

	def refresh_auto(self):
		for key, value in icv.collect(self).items():
			self.set(f"{key}_auto", value)
		self.last_refreshed = now_datetime()


def _period(name, ptype="write"):
	doc = frappe.get_doc("ICV Period Data", name)
	doc.check_permission(ptype)
	return doc


@frappe.whitelist()
def refresh(period: str):
	doc = _period(period)
	if doc.status == "Final":
		frappe.throw(_("Final ICV data is not refreshed."))
	doc.refresh_auto()
	doc.save()
	return doc.estimated_icv_pct


@frappe.whitelist()
def mark_final(period: str):
	doc = _period(period)
	doc.status = "Final"
	doc.save()
	return doc.status


@frappe.whitelist()
def drill_down(period: str, metric: str):
	"""Source rows behind an auto value."""
	doc = _period(period, "read")
	if metric in ("procurement_spend", "uae_spend", "icv_weighted_spend"):
		rows = icv.supplier_spend(doc.from_date, doc.to_date, doc.company)
		if metric == "uae_spend":
			rows = [r for r in rows if r["uae_based"]]
		return {"columns": ["supplier_name", "uae_based", "spend", "icv_score", "weighted"], "rows": rows}
	if metric in ("headcount", "uae_nationals"):
		rows = icv.employees_at(doc.to_date, doc.company)
		if metric == "uae_nationals":
			rows = [r for r in rows if r.pvfss_nationality_uae]
		return {"columns": ["name", "employee_name", "pvfss_nationality_uae"], "rows": rows}
	return {"columns": [], "rows": []}


@frappe.whitelist()
def export(period: str):
	"""ICV-12: the period values as an Excel sheet (layout per the certifying body template, Q-10)."""
	from frappe.utils.xlsxutils import make_xlsx

	doc = _period(period, "read")
	rows = [[_("Field"), _("Auto value"), _("Override"), _("Used value"), _("Note")]]
	for key in icv.AUTO_METRICS:
		label = doc.meta.get_label(key)
		rows.append(
			[
				_(label),
				doc.get(f"{key}_auto"),
				doc.get(f"{key}_override"),
				doc.get(key),
				doc.get(f"{key}_note"),
			]
		)
	rows += [
		[_("Payroll Total"), None, None, doc.payroll_total, None],
		[_("Emirati Payroll"), None, None, doc.emirati_payroll, None],
	]
	rows += [[_("Bonus: {0}").format(r.factor), None, None, r.score_pct, r.note] for r in doc.bonus_factors]
	rows.append([])
	rows.append([_("Component"), _("Score %"), _("Weight %"), _("Contribution %")])
	rows += [[r.component, r.score_pct, r.weight_pct, r.contribution_pct] for r in doc.component_scores]
	rows.append([_("Estimated ICV %"), None, None, doc.estimated_icv_pct])
	xlsx = make_xlsx(rows, "ICV")
	frappe.response["filename"] = f"{doc.name}.xlsx"
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"
