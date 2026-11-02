// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-QA-18 / SCR-QA-19: IRN form with releasable heats and the live G5 gate panel.

frappe.ui.form.on("IRN", {
	setup(frm) {
		frm.set_query("supplier_po", () => ({ filters: { docstatus: 1 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.supplier_po) {
			frm.add_custom_button(__("Load releasable heats"), () =>
				frappe
					.xcall("pvfss.pvfss_quality.doctype.irn.irn.releasable_heats", {
						supplier_po: frm.doc.supplier_po,
					})
					.then((rows) => {
						frm.clear_table("lines");
						rows.forEach((r) => frm.add_child("lines", r));
						frm.refresh_field("lines");
					})
			);
		}
		if (!frm.is_new() && frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Check gate"), () => irn_gate(frm));
			irn_gate(frm);
		}
	},
});

function irn_gate(frm) {
	frappe
		.xcall("pvfss.pvfss_quality.doctype.irn.irn.check_gate", { irn: frm.doc.name })
		.then((r) => {
			const esc = frappe.utils.escape_html;
			const items = r.failures.length
				? r.failures
						.map(
							(f) =>
								`<li class="text-danger">✗ ${esc(f.message)} ${
									f.url ? `<a href="${f.url}">${__("Open")}</a>` : ""
								} <small class="text-muted">${esc(f.rule || "")}</small></li>`
						)
						.join("")
				: `<li class="text-success">✓ ${__("All IRN gate conditions pass")}</li>`;
			frm.get_field("gate_html").$wrapper.html(`<ul class="list-unstyled">${items}</ul>`);
		});
}
