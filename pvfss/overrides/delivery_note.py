"""Delivery Note doc events: dispatch gate G7 with TRC-04, documents and POD (Module 10)."""

from pvfss.pvfss_logistics import dispatch
from pvfss.pvfss_quality import traceability


def validate(doc, method=None):
	dispatch.validate(doc)


def before_submit(doc, method=None):
	dispatch.before_submit(doc)


def on_submit(doc, method=None):
	traceability.refresh_for_document(doc)


def on_update_after_submit(doc, method=None):
	dispatch.on_update_after_submit(doc)


def on_cancel(doc, method=None):
	traceability.refresh_for_document(doc)
