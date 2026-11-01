// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// Project dashboard (PRJ-11, SCR-PRJ-05), closure checklist (PRJ-40).

frappe.ui.form.on("Project", {
	refresh(frm) {
		if (frm.is_new() || !frm.fields_dict.pvfss_dashboard) return;
		if (frm.doc.pvfss_delivery_at_risk) {
			frm.dashboard.set_headline_alert(
				`<span class="indicator red">${__(
					"Delivery at risk"
				)}</span> ${frappe.utils.escape_html(frm.doc.pvfss_risk_reason || "")}`
			);
		}
		frm.add_custom_button(__("Project Cost Sheet"), () =>
			frappe.set_route("query-report", "Project Cost Sheet", { project: frm.doc.name })
		);
		frm.add_custom_button(__("Expediting Logs"), () =>
			frappe.set_route("List", "Expediting Log", { project: frm.doc.name })
		);
		frm.add_custom_button(
			__("Change Register Entry"),
			() => frappe.new_doc("Project Change", { project: frm.doc.name }),
			__("Create")
		);
		frappe
			.xcall("pvfss.pvfss_purchasing.project.get_dashboard", { project: frm.doc.name })
			.then((data) => {
				frm.fields_dict.pvfss_dashboard.$wrapper.html(
					pvfss.project.render_dashboard(frm, data)
				);
			});
	},
});

frappe.provide("pvfss.project");

pvfss.project.render_dashboard = function (frm, data) {
	const esc = frappe.utils.escape_html;
	const money = (v) => format_currency(v || 0, "AED");
	const list = (doctype, filters, label) =>
		`<a href="/app/${frappe.router.slug(doctype)}?${new URLSearchParams(
			filters
		).toString()}">${label}</a>`;
	const rows = (data.purchase_orders || [])
		.map((po) => {
			const status = po.expediting_status
				? `<span class="indicator ${
						{
							"On track": "green",
							"At risk": "orange",
							Late: "red",
							Complete: "blue",
						}[po.expediting_status] || "gray"
				  }">${__(po.expediting_status)}</span>`
				: "-";
			return `<tr>
				<td>${list("Purchase Order", { name: po.purchase_order }, esc(po.purchase_order))}<br><small>${esc(
				po.supplier
			)}</small></td>
				<td>${esc(__(po.status))}</td>
				<td>${po.expediting_log ? list("Expediting Log", { name: po.expediting_log }, status) : status}
					<br><small>${esc(po.next_milestone || "")} ${
				po.next_forecast_date ? frappe.datetime.str_to_user(po.next_forecast_date) : ""
			}</small></td>
				<td class="text-right">${list(
					"Purchase Receipt",
					{ purchase_order: po.purchase_order },
					`${po.received_qty} / ${po.ordered_qty}`
				)}</td>
				<td class="text-right">${list(
					"Purchase Invoice",
					{ purchase_order: po.purchase_order },
					money(po.invoiced_amount)
				)}</td>
				<td class="text-right">${money(po.paid_amount)}</td>
			</tr>`;
		})
		.join("");
	return `<div class="pvfss-dashboard">
		<div class="row">
			<div class="col-sm-4"><div class="text-muted">${__("Delivery")}</div>
				<h4>${
					data.at_risk
						? `<span class="indicator red">${__("At risk")}</span>`
						: `<span class="indicator green">${__("On track")}</span>`
				}</h4></div>
			<div class="col-sm-4"><div class="text-muted">${__("Open changes")}</div>
				<h4>${list(
					"Project Change",
					{ project: frm.doc.name, workflow_state: "Open" },
					data.open_changes
				)}</h4></div>
			<div class="col-sm-4"><div class="text-muted">${__("Closure checklist")}</div>
				<h4>${data.closure_done} / ${data.closure_total}</h4></div>
		</div>
		<table class="table table-bordered table-sm mt-3">
			<thead><tr><th>${__("Supplier PO")}</th><th>${__("Status")}</th><th>${__("Expediting")}</th>
				<th class="text-right">${__("Received / Ordered")}</th><th class="text-right">${__(
		"Invoiced"
	)}</th>
				<th class="text-right">${__("Paid")}</th></tr></thead>
			<tbody>${
				rows ||
				`<tr><td colspan="6" class="text-muted">${__("No Supplier POs yet")}</td></tr>`
			}</tbody>
		</table></div>`;
};
