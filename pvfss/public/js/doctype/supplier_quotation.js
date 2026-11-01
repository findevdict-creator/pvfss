// Supplier Quotation form (SCR-RFQ-06/07): validity banner, Excel import, negotiation round.

const PVFSS_SQ_IMPORT = "pvfss.pvfss_crm.sq_import";

frappe.ui.form.on("Supplier Quotation", {
	refresh(frm) {
		frm.dashboard.clear_headline();
		if (frm.doc.valid_till && frm.doc.valid_till < frappe.datetime.now_date()) {
			frm.dashboard.set_headline_alert(__("Validity date has passed"), "orange");
		}
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Import from Excel"), () => pvfss.sq.import_dialog(frm), __("Tools"));
			frm.add_custom_button(__("Add Negotiation Round"), () => pvfss.sq.round_dialog(frm), __("Tools"));
		}
		if (frm.doc.opportunity) {
			frm.add_custom_button(
				__("Competitive Statement"),
				() =>
					frappe.set_route("query-report", "Competitive Statement", {
						inquiry: frm.doc.opportunity,
					}),
				__("View")
			);
		}
	},
});

frappe.ui.form.on("Supplier Quotation Item", {
	pvfss_no_quote(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.pvfss_no_quote) frappe.model.set_value(cdt, cdn, "rate", 0);
	},
});

frappe.provide("pvfss.sq");

pvfss.sq.import_dialog = function (frm) {
	const esc = frappe.utils.escape_html;
	const d = new frappe.ui.Dialog({
		title: __("Import from Excel"),
		size: "extra-large",
		fields: [
			{ fieldname: "file", label: __("Supplier's priced Excel"), fieldtype: "Attach", reqd: 1 },
			{ fieldname: "preview", fieldtype: "HTML" },
		],
		primary_action_label: __("Preview"),
		primary_action(values) {
			const args = { supplier_quotation: frm.doc.name, file_url: values.file };
			if (d.previewed) {
				frappe.xcall(`${PVFSS_SQ_IMPORT}.apply`, args).then((n) => {
					d.hide();
					frappe.show_alert({ message: __("{0} lines updated", [n]), indicator: "green" });
					frm.reload_doc();
				});
				return;
			}
			frappe.xcall(`${PVFSS_SQ_IMPORT}.preview`, args).then((r) => {
				const body = r.rows
					.map(
						(row) => `<tr><td>${esc(row.pvfss_customer_line_ref || "")}</td>
						<td>${row.matched ? "✓" : "✗"}</td><td>${row.rate ?? ""}</td>
						<td>${row.lead_time_days ?? ""}</td><td>${esc(row.pvfss_availability || "")}</td>
						<td>${esc(row.pvfss_manufacturer || "")}</td><td>${esc(row.pvfss_origin || "")}</td>
						<td>${esc(row.pvfss_compliance || "")}</td><td>${esc(row.pvfss_deviation_note || "")}</td>
						<td><span class="indicator-pill ${row.status === "OK" ? "green" : "red"}">${esc(
							row.status === "OK" ? __("OK") : row.message
						)}</span></td></tr>`
					)
					.join("");
				const unquoted = r.unquoted_lines.length
					? `<p class="text-muted">${__("Lines not in the file")}: ${esc(r.unquoted_lines.join(", "))}</p>`
					: "";
				d.fields_dict.preview.$wrapper.html(`<p>${__("{0} rows OK, {1} errors", [r.ok, r.errors])}</p>
					${unquoted}<div style="max-height:400px;overflow:auto"><table class="table table-bordered table-sm">
					<thead><tr><th>${__("Line ref")}</th><th>${__("Matched")}</th><th>${__("Rate")}</th>
					<th>${__("Lead time")}</th><th>${__("Availability")}</th><th>${__("Manufacturer")}</th>
					<th>${__("Origin")}</th><th>${__("Compliance")}</th><th>${__("Deviation note")}</th>
					<th>${__("Status")}</th></tr></thead><tbody>${body}</tbody></table></div>`);
				d.previewed = r.ok > 0;
				d.set_primary_action(__("Apply to quotation"), d.primary_action);
				d.get_primary_btn().prop("disabled", !r.ok);
			});
		},
	});
	d.show();
};

pvfss.sq.round_dialog = function (frm) {
	const data = (frm.doc.items || [])
		.filter((r) => !r.pvfss_no_quote)
		.map((r) => ({
			line_ref: r.pvfss_customer_line_ref,
			current_price: r.rate,
			revised_price: r.rate,
			current_lead: r.lead_time_days,
			revised_lead_time: r.lead_time_days,
		}));
	const d = new frappe.ui.Dialog({
		title: __("Add Negotiation Round"),
		size: "extra-large",
		fields: [
			{ fieldname: "notes", label: __("Notes"), fieldtype: "Small Text" },
			{
				fieldname: "lines",
				fieldtype: "Table",
				cannot_add_rows: true,
				in_place_edit: true,
				data,
				fields: [
					{ fieldname: "line_ref", label: __("Line"), fieldtype: "Data", read_only: 1, in_list_view: 1 },
					{ fieldname: "current_price", label: __("Current price"), fieldtype: "Float", read_only: 1, in_list_view: 1 },
					{ fieldname: "revised_price", label: __("Revised price"), fieldtype: "Float", in_list_view: 1 },
					{ fieldname: "current_lead", label: __("Current lead time"), fieldtype: "Int", read_only: 1, in_list_view: 1 },
					{ fieldname: "revised_lead_time", label: __("Revised lead time"), fieldtype: "Int", in_list_view: 1 },
				],
			},
		],
		primary_action_label: __("Apply"),
		primary_action(values) {
			let added = 0;
			(values.lines || []).forEach((l) => {
				const price_changed = l.revised_price && l.revised_price !== l.current_price;
				const lead_changed = l.revised_lead_time && l.revised_lead_time !== l.current_lead;
				if (!price_changed && !lead_changed) return;
				frm.add_child("pvfss_negotiation_rounds", {
					line_ref: l.line_ref,
					round_date: frappe.datetime.now_date(),
					revised_price: price_changed ? l.revised_price : 0,
					revised_lead_time: lead_changed ? l.revised_lead_time : 0,
					notes: values.notes,
				});
				added++;
			});
			d.hide();
			if (added) frm.save();
			else frappe.show_alert(__("Nothing changed"));
		},
	});
	d.show();
};
