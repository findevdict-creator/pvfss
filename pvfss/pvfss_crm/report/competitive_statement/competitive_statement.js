// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// Competitive Statement (RFQ-07, RFQ-08, SCR-RFQ-08)

frappe.query_reports["Competitive Statement"] = {
	filters: [
		{
			fieldname: "inquiry",
			label: __("Inquiry"),
			fieldtype: "Link",
			options: "Opportunity",
			reqd: 1,
		},
		{
			fieldname: "show_in",
			label: __("Show in"),
			fieldtype: "Select",
			options: "AED\nOriginal currency",
			default: "AED",
		},
		{ fieldname: "only_compliant", label: __("Only compliant"), fieldtype: "Check" },
		{
			fieldname: "include_cancelled",
			label: __("Include cancelled quotations"),
			fieldtype: "Check",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		const formatted = default_formatter(value, row, column, data);
		if (!data || data.is_footer) {
			return data && data.is_footer ? `<b>${formatted}</b>` : formatted;
		}
		const fn = column.fieldname || "";
		const key = fn.replace(/_(price|lead|avail|comp|sel)$/, "");
		if (fn.endsWith("_price") && data[`${key}_lowest`]) {
			return `<span class="pvfss-cs-lowest">${formatted}</span>`;
		}
		if (fn.endsWith("_lead") && data[`${key}_bestlead`]) {
			return `<span class="pvfss-cs-bestlead">${formatted}</span>`;
		}
		if (fn.endsWith("_comp") && value) {
			const cls = { C: "green", D: "orange", NC: "red" }[value] || "gray";
			return `<span class="indicator-pill ${cls}">${formatted}</span>`;
		}
		if (fn.endsWith("_sel") && data[`${key}_item`]) {
			const on = data[`${key}_sel`];
			return `<a class="pvfss-cs-select" data-item="${data[`${key}_item`]}" data-on="${
				on ? 1 : 0
			}" title="${__("Select this supplier for the line")}">${on ? "◉" : "○"}</a>`;
		}
		return formatted;
	},

	onload(report) {
		const inquiry = () => report.get_filter_value("inquiry");
		const refresh = () => report.refresh();

		report.page.add_inner_button(__("Select lowest compliant for all lines"), () => {
			if (!inquiry()) return;
			frappe
				.xcall("pvfss.pvfss_crm.selection.select_lowest", { inquiry: inquiry(), preview: 1 })
				.then((rows) => {
					if (!rows.length) {
						frappe.msgprint(__("No compliant submitted quotation lines."));
						return;
					}
					const body = rows
						.map(
							(r) =>
								`<tr><td>${frappe.utils.escape_html(r.line_ref)}</td><td>${frappe.utils.escape_html(
									r.supplier
								)}</td><td>${format_currency(r.base_rate, "AED")}</td></tr>`
						)
						.join("");
					frappe.confirm(
						`<table class="table table-bordered"><tr><th>${__("Line")}</th><th>${__(
							"Supplier"
						)}</th><th>${__("Price AED")}</th></tr>${body}</table>`,
						() =>
							frappe
								.xcall("pvfss.pvfss_crm.selection.select_lowest", {
									inquiry: inquiry(),
									preview: 0,
								})
								.then(refresh)
					);
				});
		});
		report.page.add_inner_button(__("Clear selection"), () => {
			if (!inquiry()) return;
			frappe.confirm(__("Clear every selected line for this inquiry?"), () =>
				frappe
					.xcall("pvfss.pvfss_crm.selection.clear_selection", { inquiry: inquiry() })
					.then(refresh)
			);
		});
		report.page.add_inner_button(__("Create / Update Costing Sheet"), () => {
			if (!inquiry()) return;
			frappe
				.xcall("pvfss.pvfss_crm.doctype.costing_sheet.costing_sheet.make_or_refresh", {
					inquiry: inquiry(),
				})
				.then((name) => frappe.set_route("Form", "Costing Sheet", name));
		});

		$(report.page.wrapper).on("click", ".pvfss-cs-select", function (e) {
			e.preventDefault();
			const item = $(this).attr("data-item");
			const method = $(this).attr("data-on") === "1" ? "unselect_line" : "select_line";
			frappe
				.xcall(`pvfss.pvfss_crm.selection.${method}`, { sq_item: item })
				.then(refresh);
		});
	},
};
