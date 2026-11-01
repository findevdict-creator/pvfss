// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-PRJ-02: handover checklist; G4 blocks submit while mandatory rows are outstanding.

frappe.ui.form.on("Project Handover", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.sales_order) {
			frm.add_custom_button(__("Refresh from Customer PO"), () =>
				frm.call("pull_from_sales_order").then(() => frm.dirty())
			);
		}
		if (frm.doc.project) {
			frm.add_custom_button(__("Open Project"), () => frappe.set_route("Form", "Project", frm.doc.project));
		}
		const outstanding = frm.doc.outstanding_count || 0;
		if (frm.doc.docstatus === 0) {
			frm.dashboard.set_headline_alert(
				outstanding
					? `<span class="indicator orange">${__("{0} mandatory item(s) outstanding", [outstanding])}</span>`
					: `<span class="indicator green">${__("All mandatory items received")}</span>`
			);
		}
		frm.toggle_reqd("return_reason", frm.doc.workflow_state === "Pending Acceptance");
	},
	sales_order(frm) {
		if (frm.doc.sales_order) {
			frm.clear_table("items");
			frm.call("pull_from_sales_order").then(() => frm.refresh_fields());
		}
	},
});
