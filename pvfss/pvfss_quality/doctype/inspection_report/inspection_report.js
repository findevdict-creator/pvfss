// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-QA-10: Inspection Report. Pass / Fail is computed on save (QA-24); Raise NCR from failures.

frappe.ui.form.on("Inspection Report", {
	refresh(frm) {
		if (frm.doc.sampling_check) {
			const missing = frm.doc.sampling_check.startsWith(__("Heats without"));
			frm.dashboard.set_headline_alert(
				`<span class="indicator ${missing ? "red" : "green"}">${frappe.utils.escape_html(
					frm.doc.sampling_check
				)}</span>`
			);
		}
		const failed =
			(frm.doc.test_results || []).some((r) => r.result === "Fail") ||
			(frm.doc.point_results || []).some((r) => r.result === "Rejected");
		if (!frm.is_new() && failed) {
			frm.add_custom_button(
				__("NCR"),
				() =>
					frappe
						.xcall(
							"pvfss.pvfss_quality.doctype.inspection_report.inspection_report.make_ncr",
							{
								inspection_report: frm.doc.name,
							}
						)
						.then((name) => frappe.set_route("Form", "Non Conformance", name)),
				__("Create")
			);
		}
	},
});
