// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// Technical Evaluation (SCR-RFQ-12): load shortlist, selected lines flagged.

frappe.ui.form.on("Technical Evaluation", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.inquiry) {
			frm.add_custom_button(__("Load shortlist"), () =>
				frm.call("load_shortlist").then(() => frm.dirty())
			);
		}
		if (frm.doc.inquiry) {
			frm.add_custom_button(
				__("Competitive Statement"),
				() =>
					frappe.set_route("query-report", "Competitive Statement", {
						inquiry: frm.doc.inquiry,
					}),
				__("View")
			);
		}
		if (frm.doc.not_compliant_count) {
			frm.dashboard.clear_headline();
			frm.dashboard.set_headline_alert(
				__("{0} line(s) Not compliant", [frm.doc.not_compliant_count]),
				"red"
			);
		}
	},
	inquiry(frm) {
		if (frm.doc.inquiry && !(frm.doc.items || []).length) {
			frm.call("load_shortlist").then(() => frm.refresh_field("items"));
		}
	},
});
