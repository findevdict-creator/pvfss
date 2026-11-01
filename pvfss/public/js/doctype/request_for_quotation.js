// RFQ form (SCR-RFQ-02/03): Suggest Suppliers dialog, supplier price sheet, AVL flag pills.

frappe.ui.form.on("Request for Quotation", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Suggest Suppliers"), () => pvfss.rfq.suggest_dialog(frm));
		}
		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Download supplier Excel"),
				() =>
					window.open(
						`/api/method/pvfss.pvfss_crm.rfq.download_supplier_excel?rfq=${encodeURIComponent(
							frm.doc.name
						)}`
					),
				__("Tools")
			);
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

frappe.provide("pvfss.rfq");

pvfss.rfq.suggest_dialog = function (frm) {
	const categories = [
		...new Set(
			(frm.doc.items || []).map((r) => r.pvfss_product_category || r.item_group).filter(Boolean)
		),
	];
	const already = new Set((frm.doc.suppliers || []).map((r) => r.supplier));
	const esc = frappe.utils.escape_html;
	let rows = [];

	const d = new frappe.ui.Dialog({
		title: __("Suggest Suppliers"),
		size: "extra-large",
		fields: [
			{
				fieldname: "categories",
				label: __("Product categories"),
				fieldtype: "MultiSelectList",
				default: categories,
				get_data: (txt) => frappe.db.get_link_options("Item Group", txt),
			},
			{ fieldtype: "Column Break" },
			{ fieldname: "only_approved", label: __("Only approved"), fieldtype: "Check" },
			{ fieldname: "only_avl", label: __("Only on AVL"), fieldtype: "Check" },
			{ fieldtype: "Section Break" },
			{ fieldname: "grid", fieldtype: "HTML" },
		],
		primary_action_label: __("Add selected suppliers"),
		primary_action() {
			const picked = d.$wrapper
				.find("input.pvfss-pick:checked")
				.map((i, el) => $(el).attr("data-supplier"))
				.get();
			picked.forEach((supplier) => {
				if (already.has(supplier)) return;
				const row = frm.add_child("suppliers", { supplier });
				frappe.model.set_value(row.doctype, row.name, "supplier", supplier);
			});
			frm.refresh_field("suppliers");
			d.hide();
		},
	});

	const load = () => {
		const v = d.get_values(true);
		frappe
			.xcall("pvfss.pvfss_crm.rfq.suggest_suppliers", {
				categories: v.categories || [],
				client_project: frm.doc.__onload?.client_project || null,
				only_approved: v.only_approved ? 1 : 0,
				only_avl: v.only_avl ? 1 : 0,
			})
			.then((r) => {
				rows = r;
				const body = rows
					.map((s) => {
						const cats = s.categories
							.map((c) => `${esc(c.category)} ${c.covered ? "✓" : "✗"}`)
							.join(", ");
						const lock = s.blocked ? "🔒 " : "";
						const avl = { "On AVL": "✓", "Not on AVL": "⚠", "Not required": "–" }[s.avl] || "";
						return `<tr class="${s.blocked ? "text-muted" : ""}">
							<td><input type="checkbox" class="pvfss-pick" data-supplier="${esc(s.supplier)}"
								${s.blocked || already.has(s.supplier) ? "disabled" : ""}></td>
							<td>${lock}${esc(s.supplier_name || s.supplier)}</td>
							<td>${cats}</td><td>${s.covered} / ${s.total}</td>
							<td><span class="indicator-pill ${s.blocked ? "red" : s.approval_status === "Approved" ? "green" : "orange"}">${esc(
								__(s.approval_status || "")
							)}</span></td>
							<td title="${esc(__(s.avl))}">${avl}</td>
							<td>${s.last_quote ? frappe.datetime.str_to_user(s.last_quote) : ""}</td>
							<td>${s.lowest_share || 0}%</td></tr>`;
					})
					.join("");
				d.fields_dict.grid.$wrapper.html(
					rows.length
						? `<div style="max-height:420px;overflow:auto"><table class="table table-bordered table-sm">
						<thead><tr><th></th><th>${__("Supplier")}</th><th>${__("Categories covered")}</th>
						<th>${__("Lines covered")}</th><th>${__("Approval")}</th><th>${__("AVL")}</th>
						<th>${__("Last quote")}</th><th>${__("Lowest-quote share")}</th></tr></thead>
						<tbody>${body}</tbody></table></div>`
						: `<p class="text-muted">${__("No supplier covers these categories.")}</p>`
				);
			});
	};
	["categories", "only_approved", "only_avl"].forEach((f) => {
		d.fields_dict[f].df.onchange = load;
	});
	d.show();
	load();
};
