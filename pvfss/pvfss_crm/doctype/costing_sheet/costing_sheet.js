// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// Costing Sheet (SCR-RFQ-10): margin badge, refresh from selection, apply allocations.

frappe.ui.form.on("Costing Sheet", {
	refresh(frm) {
		const min = frm.doc.__onload?.min_margin || 0;
		if (!frm.is_new()) {
			const ok = (frm.doc.margin_pct || 0) >= min;
			frm.dashboard.clear_headline();
			frm.dashboard.set_headline_alert(
				`${__("Margin")} ${format_number(frm.doc.margin_pct || 0, null, 2)}% (${__("minimum")} ${min}%)`,
				ok ? "green" : "red"
			);
			if (frm.doc.non_compliant_lines) {
				frm.dashboard.add_comment(
					__("{0} line(s) are Not compliant on the Technical Evaluation.", [frm.doc.non_compliant_lines]),
					"red",
					true
				);
			}
		}
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Refresh from selection"), () =>
				frm.call("refresh_from_selection").then(() => frm.dirty() || frm.refresh_fields())
			);
			frm.add_custom_button(__("Apply allocations"), () => frm.save());
		}
		if (frm.doc.docstatus === 1 && !frm.doc.quotation) {
			const btn = frm.add_custom_button(__("Create Quotation"), () =>
				frappe
					.xcall("pvfss.pvfss_crm.quotation.make_quotation", { costing_sheet: frm.doc.name })
					.then((doc) => {
						frappe.model.sync(doc);
						frappe.set_route("Form", doc.doctype, doc.name);
					})
			);
			if (frm.doc.non_compliant_lines) {
				btn.prop("disabled", true).attr(
					"title",
					__("Lines are not technically compliant. Re-select suppliers on the Competitive Statement.")
				);
			}
		}
		if (frm.doc.quotation) {
			frm.add_custom_button(
				__("Quotation"),
				() => frappe.set_route("Form", "Quotation", frm.doc.quotation),
				__("View")
			);
		}
		if (frm.doc.inquiry) {
			frm.add_custom_button(
				__("Competitive Statement"),
				() => frappe.set_route("query-report", "Competitive Statement", { inquiry: frm.doc.inquiry }),
				__("View")
			);
		}
	},
	onload(frm) {
		if (frm.is_new() && frm.doc.target_margin_pct == null && frm.doc.__onload) {
			frm.set_value("target_margin_pct", frm.doc.__onload.min_margin);
		}
	},
});

frappe.ui.form.on("Costing Sheet Item", {
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.technical_status === "Not compliant") {
			frm.fields_dict.items.grid.grid_rows_by_docname[cdn]?.wrapper.addClass("pvfss-row-danger");
		}
	},
});
