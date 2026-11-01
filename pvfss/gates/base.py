"""Shared gate framework for hard gates G1-G7 and every [RULE] (GEN-05, screens §2.6).

All gates behave the same way on screen: one red dialog titled with the gate, one bullet
per failed condition, each with a link to the record that needs fixing.

Usage in a gate module::

    def check(doc) -> GateResult:
        result = GateResult(_("IRN gate failed"), doc=doc, gate="G5")
        for line in doc.items:
            result.check(line.batch, _("Row {0}: batch is missing").format(line.idx), rule="QA-33")
        return result


    def before_submit(doc, method=None):
        check(doc).throw_if_failed()

Rules:

* collect every failure before throwing, never stop at the first;
* read thresholds from ``pvfss.utils.settings`` (GEN-06);
* during a PVFSS import (IMP-01) failures are logged to Import Exception Log instead;
* expose the same ``check`` through a whitelisted endpoint so the form can show it as a live
  panel before submit (``GateResult.as_dict``).
"""

import frappe
from frappe import _
from frappe.utils import escape_html, get_link_to_form

from pvfss.utils.importing import is_import, log_exception


class GateFailedError(frappe.ValidationError):
	pass


class GateResult:
	def __init__(self, title, doc=None, gate=None):
		self.title = title
		self.doc = doc
		self.gate = gate
		self.failures = []
		self.passes = []

	# ------------------------------------------------------------------ collect
	def fail(self, message, doctype=None, name=None, rule=None):
		self.failures.append(frappe._dict(message=message, doctype=doctype, name=name, rule=rule))
		return self

	def check(self, condition, message, doctype=None, name=None, rule=None):
		"""Record ``message`` as a failure when ``condition`` is falsy; return the condition."""
		if condition:
			self.passes.append(frappe._dict(message=message, rule=rule))
		else:
			self.fail(message, doctype=doctype, name=name, rule=rule)
		return bool(condition)

	@property
	def ok(self):
		return not self.failures

	# ------------------------------------------------------------------ output
	def _failure_html(self, failure):
		text = escape_html(failure.message)
		if failure.doctype and failure.name:
			text += " " + get_link_to_form(failure.doctype, failure.name)
		if failure.rule:
			text += f' <span class="text-muted small">({escape_html(failure.rule)})</span>'
		return f"<li>{text}</li>"

	def as_html(self):
		return (
			'<ul class="pvfss-gate-failures">'
			+ "".join(self._failure_html(f) for f in self.failures)
			+ "</ul>"
		)

	def as_dict(self):
		"""Payload for the live gate-check panel on the form."""
		return {
			"title": self.title,
			"gate": self.gate,
			"ok": self.ok,
			"failures": [
				{
					**f,
					"url": frappe.utils.get_url_to_form(f.doctype, f.name) if f.doctype and f.name else None,
				}
				for f in self.failures
			],
			"passes": list(self.passes),
		}

	def throw_if_failed(self, warn_only=False):
		"""Raise one dialog listing every failure.

		During a PVFSS import each failure is logged instead and nothing is raised (IMP-01).
		With ``warn_only`` the same list is shown as an orange warning and saving continues.
		"""
		if self.ok:
			return

		if is_import(self.doc):
			for f in self.failures:
				log_exception(self.doc, rule=f.rule or self.gate, message=f.message, gate=self.gate)
			return

		if warn_only:
			frappe.msgprint(self.as_html(), title=self.title, indicator="orange")
			return

		frappe.throw(self.as_html(), exc=GateFailedError, title=self.title)
