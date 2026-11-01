// Quotation form (SCR-SQ-02): margin badge, approval route, revision.

frappe.ui.form.on("Quotation", {
	refresh(frm) {
		frm.dashboard.clear_headline();
		if (frm.doc.pvfss_costing_sheet || frm.doc.pvfss_approver_role) {
			const route = frm.doc.__onload?.pvfss_approval_route || "";
			const low = frm.doc.pvfss_approver_role === "PVFSS Director";
			frm.dashboard.set_headline_alert(
				`${__("Margin")} ${format_number(frm.doc.pvfss_margin_pct || 0, null, 2)}% · ${frappe.utils.escape_html(route)}`,
				low ? "orange" : "green"
			);
		}
		if (frm.doc.docstatus === 1 && frm.doc.status !== "Lost" && frm.doc.status !== "Ordered") {
			frm.add_custom_button(__("Revise"), () =>
				frappe.confirm(
					__("Cancel {0} and create the next revision?", [frm.doc.name]),
					() =>
						frappe
							.xcall("pvfss.pvfss_crm.quotation.make_revision", { quotation: frm.doc.name })
							.then((name) => frappe.set_route("Form", "Quotation", name))
				)
			);
		}
		if (frm.doc.pvfss_costing_sheet) {
			frm.add_custom_button(
				__("Costing Sheet"),
				() => frappe.set_route("Form", "Costing Sheet", frm.doc.pvfss_costing_sheet),
				__("View")
			);
		}
	},
	pvfss_icv_score_used(frm) {
		frm.trigger("pvfss_recalc_icv");
	},
	pvfss_icv_weightage_pct(frm) {
		frm.trigger("pvfss_recalc_icv");
	},
	pvfss_recalc_icv(frm) {
		const s = (frm.doc.pvfss_icv_score_used || 0) / 100;
		const w = (frm.doc.pvfss_icv_weightage_pct || 0) / 100;
		frm.set_value("pvfss_evaluated_price", (frm.doc.grand_total || 0) * (1 - s * w));
	},
});
