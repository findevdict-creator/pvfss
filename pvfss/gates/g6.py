"""G6: Purchase Receipt of heat-traceable items needs batches with heat numbers (TRC-03)."""

from frappe import _

from pvfss.gates.base import GateResult
from pvfss.pvfss_quality import traceability


def check(doc):
	result = GateResult(_("Receipt cannot be submitted"), doc=doc, gate="G6")
	traceability.check_receipt(doc, result)
	return result
