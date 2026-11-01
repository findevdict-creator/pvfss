// Customer PO (Sales Order) form (SCR-SQ-05): review result badge, re-compare.

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.pvfss_review_status) {
			frm.dashboard.clear_headline();
			const ok = !frm.doc.pvfss_difference_count;
			frm.dashboard.set_headline_alert(
				frappe.utils.escape_html(frm.doc.pvfss_review_status),
				ok ? "green" : "orange"
			);
		}
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Re-compare with quotation"), () => frm.save(), __("Review"));
		}
	},
});

frappe.ui.form.on("Customer PO Review Item", {
	result(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frm.fields_dict.pvfss_po_review.grid.toggle_reqd("remark", row.result === "Deviation");
	},
});
