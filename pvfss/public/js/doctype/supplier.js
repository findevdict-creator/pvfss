// Supplier form (SCR-SUP-02): approval banner, expiring documents, + Supplier Evaluation.

frappe.ui.form.on("Supplier", {
	refresh(frm) {
		frm.dashboard.clear_headline();
		const status = frm.doc.pvfss_approval_status;
		if (["Suspended", "Blacklisted"].includes(status)) {
			frm.dashboard.set_headline_alert(
				__("{0}: cannot receive RFQs or POs", [__(status)]),
				"red"
			);
		} else if (status === "Conditionally approved") {
			frm.dashboard.set_headline_alert(
				__("Conditionally approved: warning shown on RFQ and PO") +
					(frm.doc.pvfss_approval_remarks
						? ` (${frappe.utils.escape_html(frm.doc.pvfss_approval_remarks)})`
						: ""),
				"orange"
			);
		} else {
			const expiring = (frm.doc.pvfss_documents || []).filter(
				(d) => d.status !== "Valid"
			).length;
			if (expiring) {
				frm.dashboard.set_headline_alert(
					__("{0} documents expire soon or have expired", [expiring]),
					"orange"
				);
			}
		}
		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Supplier Evaluation"),
				() => frappe.new_doc("Supplier Evaluation", { supplier: frm.doc.name }),
				__("Create")
			);
		}
	},
});
