// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-ICV-04: estimate head, refresh, drill-down, export and mark final.

const ICV = "pvfss.pvfss_icv.doctype.icv_period_data.icv_period_data";
const ICV_DRILL = [
	"procurement_spend",
	"uae_spend",
	"icv_weighted_spend",
	"headcount",
	"uae_nationals",
];

frappe.ui.form.on("ICV Period Data", {
	refresh(frm) {
		draw_estimate(frm);
		if (frm.is_new()) return;
		const call = (method) =>
			frappe
				.xcall(`${ICV}.${method}`, { period: frm.doc.name })
				.then(() => frm.reload_doc());
		if (frm.doc.status === "Draft") {
			frm.add_custom_button(__("Refresh auto values"), () => call("refresh"));
			frm.add_custom_button(__("Mark final"), () => call("mark_final"));
		}
		frm.add_custom_button(__("Export to ICV template"), () =>
			window.open(`/api/method/${ICV}.export?period=${encodeURIComponent(frm.doc.name)}`)
		);
		ICV_DRILL.forEach((metric) =>
			frm.add_custom_button(
				__(frappe.meta.get_label(frm.doctype, metric)),
				() => drill(frm, metric),
				__("Drill down")
			)
		);
	},
});

function draw_estimate(frm) {
	const $w = frm.get_field("estimate_html").$wrapper;
	$w.html(
		`<div style="font-size:28px;font-weight:600">${__("Estimated ICV {0}%", [
			format_number(frm.doc.estimated_icv_pct || 0, null, 1),
		])}</div>
		<div class="text-muted">${__(
			"Estimates only. The official score comes from the certifying body."
		)}</div><div class="icv-chart"></div>`
	);
	const rows = frm.doc.component_scores || [];
	if (!rows.length) return;
	new frappe.Chart($w.find(".icv-chart")[0], {
		type: "bar",
		height: 180,
		data: {
			labels: rows.map((r) => r.component),
			datasets: [
				{ name: __("Contribution %"), values: rows.map((r) => r.contribution_pct) },
			],
		},
	});
}

function drill(frm, metric) {
	frappe.xcall(`${ICV}.drill_down`, { period: frm.doc.name, metric }).then((r) => {
		const esc = frappe.utils.escape_html;
		const head = r.columns.map((c) => `<th>${esc(c)}</th>`).join("");
		const body = r.rows
			.map(
				(row) =>
					`<tr>${r.columns
						.map((c) => `<td>${esc(String(row[c] ?? ""))}</td>`)
						.join("")}</tr>`
			)
			.join("");
		frappe.msgprint({
			title: __(frappe.meta.get_label(frm.doctype, metric)),
			message: `<table class="table table-bordered table-condensed"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`,
			wide: true,
		});
	});
}
