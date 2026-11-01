"""Delivery Note doc events (TRC-04; the dispatch gate G7 joins in 13-dispatch)."""

from frappe import _

from pvfss.gates.base import GateResult
from pvfss.pvfss_quality import traceability


def before_submit(doc, method=None):
	result = GateResult(_("Delivery cannot be submitted"), doc=doc, gate="TRC-04")
	traceability.check_release(doc, result)
	result.throw_if_failed()


def on_submit(doc, method=None):
	traceability.refresh_for_document(doc)


def on_cancel(doc, method=None):
	traceability.refresh_for_document(doc)
