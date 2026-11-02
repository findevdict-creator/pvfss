"""Risk matrix lookups (HSE-02)."""

import frappe
from frappe.utils import cint

DEFAULT_BANDS = [
	(1, 4, "Low", "#22c55e"),
	(5, 9, "Medium", "#eab308"),
	(10, 16, "High", "#f97316"),
	(17, 25, "Extreme", "#ef4444"),
]


def bands():
	rows = frappe.get_cached_doc("Risk Matrix").bands
	if rows:
		return [(cint(r.from_score), cint(r.to_score), r.rating, r.colour) for r in rows]
	return DEFAULT_BANDS


def rate(likelihood, severity):
	"""(score, rating) for a likelihood and severity of 1 to 5."""
	likelihood, severity = cint(likelihood), cint(severity)
	if not (likelihood and severity):
		return 0, None
	score = likelihood * severity
	for low, high, rating, _colour in bands():
		if low <= score <= high:
			return score, rating
	return score, None


def seed():
	doc = frappe.get_single("Risk Matrix")
	if doc.bands:
		return
	for low, high, rating, colour in DEFAULT_BANDS:
		doc.append("bands", {"from_score": low, "to_score": high, "rating": rating, "colour": colour})
	doc.flags.ignore_permissions = True
	doc.save()
