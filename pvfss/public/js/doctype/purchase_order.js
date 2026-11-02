// Supplier PO form (SCR-PUR-02): compliance and margin badges, re-run check.

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		frm.dashboard.clear_headline();
		if (frm.doc.pvfss_compliance_status) {
			const ok = !frm.doc.pvfss_deviation_count;
			let msg = frappe.utils.escape_html(frm.doc.pvfss_compliance_status);
			if (frm.doc.pvfss_flag_count)
				msg += ` · ${__("{0} flags", [frm.doc.pvfss_flag_count])}`;
			if (frm.doc.pvfss_negative_margin_lines) {
				msg += ` · ${__("Negative margin on lines {0}", [
					frappe.utils.escape_html(frm.doc.pvfss_negative_margin_lines),
				])}`;
			}
			if (frm.doc.pvfss_approval_route) msg += ` · ${__(frm.doc.pvfss_approval_route)}`;
			frm.dashboard.set_headline_alert(
				msg,
				ok && !frm.doc.pvfss_negative_margin_lines ? "green" : "orange"
			);
		}
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Re-run check"), () => frm.save(), __("Compliance"));
		}
		if (frm.doc.pvfss_sales_order) {
			frm.add_custom_button(
				__("Customer PO"),
				() => frappe.set_route("Form", "Sales Order", frm.doc.pvfss_sales_order),
				__("View")
			);
		}
	},
});

frappe.ui.form.on("PO Compliance Line", {
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frm.fields_dict.pvfss_compliance.grid.toggle_reqd(
			"justification",
			row.result === "Deviation"
		);
	},
});

// DMS-01 / SCR-DMS-01: open the project's document folders
frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("Open project folder"),
			() =>
				frappe
					.xcall("pvfss.pvfss_dms.filing.project_folder", {
						doctype: frm.doctype,
						name: frm.doc.name,
					})
					.then((folder) =>
						folder
							? frappe.set_route(["List", "File", ...folder.split("/")])
							: frappe.msgprint(__("This document is not linked to a project yet."))
					),
			__("View")
		);
	},
});
