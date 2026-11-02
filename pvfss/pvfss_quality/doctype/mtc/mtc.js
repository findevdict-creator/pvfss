// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// QA-20: MTC form. Review and approval are added in 12-quality.

frappe.ui.form.on("MTC", {
	setup(frm) {
		frm.set_query("supplier_po", () => ({ filters: { docstatus: 1 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Trace heats"), () =>
				frappe.set_route("heat-trace", { type: "MTC No", key: frm.doc.certificate_no })
			);
		}
	},
});
