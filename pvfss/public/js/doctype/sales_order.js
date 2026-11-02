// Customer PO (Sales Order) form (SCR-SQ-05): review result badge, re-compare.

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.pvfss_review_status) {
			frm.dashboard.clear_headline();
			const ok = !frm.doc.pvfss_difference_count;
			frm.dashboard.set_headline_alert(
				frappe.utils.escape_html(frm.doc.pvfss_review_status),
				ok ? "green" : "orange"
			);
		}
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Re-compare with quotation"), () => frm.save(), __("Review"));
		}
	},
});

frappe.ui.form.on("Customer PO Review Item", {
	result(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frm.fields_dict.pvfss_po_review.grid.toggle_reqd("remark", row.result === "Deviation");
	},
});

// ---------------------------------------------------------------------------- 08-purchasing (SCR-PUR-03)
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status !== "Closed") {
			frm.add_custom_button(
				__("Supplier PO(s)"),
				() => pvfss.purchasing.create_dialog(frm),
				__("Create")
			);
		}
	},
});

frappe.provide("pvfss.purchasing");

pvfss.purchasing.create_dialog = function (frm) {
	const method = "pvfss.pvfss_purchasing.supplier_po";
	frappe.xcall(`${method}.get_plan`, { sales_order: frm.doc.name }).then((plan) => {
		const d = new frappe.ui.Dialog({
			title: __("Create Supplier PO(s)"),
			size: "extra-large",
			fields: [
				{ fieldname: "summary", fieldtype: "HTML" },
				{
					fieldname: "lines",
					fieldtype: "Table",
					cannot_add_rows: true,
					in_place_edit: true,
					data: plan,
					fields: [
						{ fieldname: "so_item", fieldtype: "Data", hidden: 1 },
						{ fieldname: "sq_item", fieldtype: "Data", hidden: 1 },
						{
							fieldname: "line_ref",
							label: __("Line"),
							fieldtype: "Data",
							read_only: 1,
							in_list_view: 1,
							columns: 1,
						},
						{
							fieldname: "item_code",
							label: __("Item"),
							fieldtype: "Data",
							read_only: 1,
							in_list_view: 1,
							columns: 2,
						},
						{
							fieldname: "qty",
							label: __("CPO qty"),
							fieldtype: "Float",
							read_only: 1,
							in_list_view: 1,
							columns: 1,
						},
						{
							fieldname: "supplier",
							label: __("Supplier"),
							fieldtype: "Link",
							options: "Supplier",
							in_list_view: 1,
							columns: 2,
						},
						{
							fieldname: "supplier_rate",
							label: __("Supplier rate"),
							fieldtype: "Float",
							read_only: 1,
							in_list_view: 1,
							columns: 1,
						},
						{
							fieldname: "lead_time_days",
							label: __("Lead"),
							fieldtype: "Int",
							read_only: 1,
							in_list_view: 1,
							columns: 1,
						},
						{
							fieldname: "ordered",
							label: __("Ordered"),
							fieldtype: "Float",
							read_only: 1,
							in_list_view: 1,
							columns: 1,
						},
						{
							fieldname: "qty_to_order",
							label: __("Qty to order"),
							fieldtype: "Float",
							in_list_view: 1,
							columns: 1,
						},
					],
				},
			],
			primary_action_label: __("Create draft POs"),
			primary_action(values) {
				frappe
					.xcall(`${method}.make_supplier_pos`, {
						sales_order: frm.doc.name,
						lines: values.lines,
					})
					.then((names) => {
						d.hide();
						frappe.show_alert({
							message: __("Created {0}", [names.join(", ")]),
							indicator: "green",
						});
						frappe.set_route("Form", "Purchase Order", names[0]);
					});
			},
		});
		const suppliers = new Set(
			plan.filter((r) => r.supplier && r.qty_to_order > 0).map((r) => r.supplier)
		);
		d.fields_dict.summary.$wrapper.html(
			`<p>${__("{0} Supplier POs will be created", [suppliers.size])}</p>`
		);
		d.show();
	});
};

// ---------------------------------------------------------------------------- 09-project (PRJ-01)
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frappe.model.can_create("Project Handover")) {
			frm.add_custom_button(
				__("Project Handover"),
				() =>
					frappe
						.xcall(
							"pvfss.pvfss_purchasing.doctype.project_handover.project_handover.make_handover",
							{
								sales_order: frm.doc.name,
							}
						)
						.then((name) => frappe.set_route("Form", "Project Handover", name)),
				__("Create")
			);
		}
	},
});

// FIN-60 / SCR-FIN-17: settle a variable consideration row with its actual amount.
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		const open = (frm.doc.pvfss_variable_consideration || []).filter(
			(r) => !r.true_up_journal_entry
		);
		if (frm.doc.docstatus !== 1 || !open.length || !frappe.user.has_role("Finance Manager"))
			return;
		frm.add_custom_button(
			__("Settle variable consideration"),
			() => {
				const d = new frappe.ui.Dialog({
					title: __("Settle variable consideration"),
					fields: [
						{
							fieldname: "row",
							fieldtype: "Select",
							label: __("Row"),
							reqd: 1,
							options: open.map((r) => ({
								value: r.name,
								label: `${r.idx}. ${__(r.vc_type)}`,
							})),
						},
						{
							fieldname: "actual_amount",
							fieldtype: "Currency",
							label: __("Actual Amount"),
							reqd: 1,
						},
					],
					primary_action_label: __("Settle"),
					primary_action(values) {
						frappe
							.xcall("pvfss.pvfss_finance.vc.settle", {
								sales_order: frm.doc.name,
								...values,
							})
							.then(() => {
								d.hide();
								frm.reload_doc();
							});
					},
				});
				d.show();
			},
			__("Finance")
		);
	},
});
