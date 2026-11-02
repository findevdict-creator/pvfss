// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-HSE-02: 5 x 5 grid recoloured live from the bands.

frappe.ui.form.on("Risk Matrix", {
	refresh: (frm) => pvfss_draw_matrix(frm),
	bands_on_form_rendered: (frm) => pvfss_draw_matrix(frm),
});
frappe.ui.form.on("Risk Matrix Band", {
	from_score: (frm) => pvfss_draw_matrix(frm),
	to_score: (frm) => pvfss_draw_matrix(frm),
	colour: (frm) => pvfss_draw_matrix(frm),
	rating: (frm) => pvfss_draw_matrix(frm),
});

function pvfss_draw_matrix(frm) {
	const band = (score) => (frm.doc.bands || []).find((b) => score >= b.from_score && score <= b.to_score) || {};
	let html = `<table class="table table-bordered" style="width:auto;text-align:center"><tr><th>${__("L × S")}</th>`;
	for (let s = 1; s <= 5; s++) html += `<th>${s}</th>`;
	html += "</tr>";
	for (let l = 5; l >= 1; l--) {
		html += `<tr><th>${l}</th>`;
		for (let s = 1; s <= 5; s++) {
			const b = band(l * s);
			html += `<td style="background:${b.colour || "#eee"};min-width:48px" title="${frappe.utils.escape_html(__(b.rating || ""))}">${l * s}</td>`;
		}
		html += "</tr>";
	}
	frm.get_field("matrix_html").$wrapper.html(html + "</table>");
}
