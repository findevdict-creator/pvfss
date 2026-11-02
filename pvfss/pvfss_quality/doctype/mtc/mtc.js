// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-QA-14: MTC form with age and authenticity badges; review and approval by workflow (QA-23).

frappe.ui.form.on("MTC", {
	setup(frm) {
		frm.set_query("supplier_po", () => ({ filters: { docstatus: 1 } }));
	},
	refresh(frm) {
		const chips = [];
		if (frm.doc.age_check) {
			chips.push(
				`<span class="indicator ${
					frm.doc.age_over ? "red" : "blue"
				}">${frappe.utils.escape_html(frm.doc.age_check)}</span>`
			);
		}
		if (frm.doc.authenticity) {
			chips.push(
				`<span class="indicator ${
					frm.doc.authenticity === __("Verified") ? "green" : "orange"
				}">${frappe.utils.escape_html(frm.doc.authenticity)}</span>`
			);
		}
		if (chips.length) frm.dashboard.set_headline_alert(chips.join("&nbsp;&nbsp;"));
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Trace heats"), () =>
				frappe.set_route("heat-trace", { type: "MTC No", key: frm.doc.certificate_no })
			);
		}
	},
});
