// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-PRJ-03: expediting log per Supplier PO.

frappe.ui.form.on("Expediting Log", {
	refresh(frm) {
		const colour = { "On track": "green", "At risk": "orange", Late: "red", Complete: "blue" }[
			frm.doc.status
		];
		if (colour) frm.page.set_indicator(__(frm.doc.status), colour);
		if (frm.doc.project) {
			frm.add_custom_button(__("Project"), () =>
				frappe.set_route("Form", "Project", frm.doc.project)
			);
		}
	},
});
