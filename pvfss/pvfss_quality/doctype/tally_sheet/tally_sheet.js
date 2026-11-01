// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-SMR-04: tally sheet form and import dialog (saved column mapping per supplier).

frappe.ui.form.on("Tally Sheet", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Import from Excel"), () => tally_import_dialog(frm));
		frm.add_custom_button(__("Download template"), () =>
			window.open(
				"/api/method/pvfss.pvfss_quality.tally_import.download_template",
				"_blank"
			)
		);
	},
});

frappe.ui.form.on("Tally Line", {
	pieces: tally_total,
	length_per_piece: tally_total,
});

function tally_total(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (row.pieces && row.length_per_piece) {
		frappe.model.set_value(cdt, cdn, "total_length", row.pieces * row.length_per_piece);
	}
}

function tally_import_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Import supplier tally sheet"),
		size: "large",
		fields: [
			{
				fieldname: "template",
				label: __("Column mapping"),
				fieldtype: "Link",
				options: "Tally Template",
				default: frm.doc.tally_template,
				description: __("Leave empty to use the PVFSS column headings."),
			},
			{ fieldname: "file_url", label: __("File"), fieldtype: "Attach", reqd: 1 },
			{ fieldname: "preview", fieldtype: "HTML" },
		],
		primary_action_label: __("Preview"),
		primary_action(values) {
			frappe
				.xcall("pvfss.pvfss_quality.tally_import.preview", {
					tally_sheet: frm.doc.name,
					file_url: values.file_url,
					template: values.template,
				})
				.then((r) => {
					const rows = r.rows
						.map(
							(row) =>
								`<tr class="${row.status === "OK" ? "" : "text-danger"}"><td>${
									row._row
								}</td><td>${frappe.utils.escape_html(row.heat_no || "")}</td><td>${
									frappe.utils.escape_html(row.lot_no || "")
								}</td><td>${row.pieces ?? ""}</td><td>${row.total_length ?? ""}</td><td>${
									row.status
								} ${frappe.utils.escape_html(row.message || "")}</td></tr>`
						)
						.join("");
					d.fields_dict.preview.$wrapper.html(
						`<p>${__("{0} rows OK, {1} with errors", [r.ok, r.errors])}</p>
						<table class="table table-bordered table-sm"><thead><tr><th>#</th><th>${__(
							"Heat"
						)}</th><th>${__("Lot")}</th><th>${__("Pieces")}</th><th>${__(
							"Length"
						)}</th><th>${__("Status")}</th></tr></thead><tbody>${rows}</tbody></table>`
					);
					d.set_primary_action(__("Import {0} rows", [r.ok]), () =>
						frappe
							.xcall("pvfss.pvfss_quality.tally_import.import_lines", {
								tally_sheet: frm.doc.name,
								file_url: values.file_url,
								template: values.template,
							})
							.then(() => {
								d.hide();
								frm.reload_doc();
							})
					);
				});
		},
	});
	d.show();
}
