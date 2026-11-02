// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-HSE-04: mini matrix with the initial (circle) and residual (diamond) positions.

frappe.ui.form.on("HSE Risk Register", {
	refresh: (frm) => mini_matrix(frm),
	likelihood: (frm) => mini_matrix(frm),
	severity: (frm) => mini_matrix(frm),
	residual_likelihood: (frm) => mini_matrix(frm),
	residual_severity: (frm) => mini_matrix(frm),
});

function mini_matrix(frm) {
	frappe.model.with_doc("Risk Matrix", "Risk Matrix").then((matrix) => {
		const bands = (matrix && matrix.bands) || [];
		const band = (score) => bands.find((b) => score >= b.from_score && score <= b.to_score) || {};
		const d = frm.doc;
		let html = '<table class="table table-bordered" style="width:auto;text-align:center;font-size:11px">';
		for (let l = 5; l >= 1; l--) {
			html += "<tr>";
			for (let s = 1; s <= 5; s++) {
				let mark = "";
				if (+d.likelihood === l && +d.severity === s) mark += "●";
				if (+d.residual_likelihood === l && +d.residual_severity === s) mark += "◆";
				html += `<td style="background:${band(l * s).colour || "#eee"};width:28px;height:24px">${mark}</td>`;
			}
			html += "</tr>";
		}
		frm.get_field("matrix_html").$wrapper.html(html + "</table>");
	});
}
