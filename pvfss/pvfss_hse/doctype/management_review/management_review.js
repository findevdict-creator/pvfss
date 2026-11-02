// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors

frappe.ui.form.on("Management Review", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Snapshot KPIs"), () =>
			frappe
				.xcall("pvfss.pvfss_hse.doctype.management_review.management_review.snapshot_kpis", { review: frm.doc.name })
				.then(() => frm.reload_doc())
		);
	},
});
