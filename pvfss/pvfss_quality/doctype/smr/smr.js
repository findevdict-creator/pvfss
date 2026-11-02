// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-SMR-02: SMR form. Annexure chips, tally matching, MTC age, receipt from an accepted SMR.

const SMR_RESULT_COLOURS = {
	Match: "green",
	"Heat not on MTC": "red",
	"Grade mismatch": "red",
	"Qty mismatch": "orange",
};

frappe.ui.form.on("SMR", {
	setup(frm) {
		frm.set_query("supplier_po", () => ({ filters: { docstatus: 1 } }));
		frm.set_query("reference_name", "annexures", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return row.reference_doctype === "MTC" || row.reference_doctype === "Tally Sheet"
				? { filters: { supplier_po: doc.supplier_po } }
				: {};
		});
	},
	refresh(frm) {
		smr_headline(frm);
		if (frm.is_new()) return;
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Import Tally Sheet"),
				() =>
					frappe
						.xcall("pvfss.pvfss_quality.doctype.smr.smr.make_tally_sheet", {
							smr: frm.doc.name,
						})
						.then((name) => frappe.set_route("Form", "Tally Sheet", name)),
				__("Actions")
			);
			frm.add_custom_button(
				__("Run matching"),
				() => frm.call("run_matching").then(() => frm.dirty() || frm.save()),
				__("Actions")
			);
			if (frappe.user.has_role("PVFSS Director")) {
				frm.add_custom_button(__("Waive MTC age"), () => smr_waive(frm), __("Actions"));
			}
		}
		if (
			frm.doc.docstatus === 1 &&
			["Accepted", "Partially accepted"].includes(frm.doc.workflow_state) &&
			!frm.doc.purchase_receipt
		) {
			frm.add_custom_button(
				__("Purchase Receipt"),
				() =>
					frappe
						.xcall("pvfss.pvfss_quality.doctype.smr.smr.make_purchase_receipt", {
							smr: frm.doc.name,
						})
						.then((name) => frappe.set_route("Form", "Purchase Receipt", name)),
				__("Create")
			);
		}
	},
	supplier_po(frm) {
		if (frm.doc.supplier_po) {
			frm.clear_table("items");
			frm.call("pull_lines").then(() => frm.refresh_field("items"));
		}
	},
});

frappe.ui.form.on("SMR Match", {
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frm.fields_dict.matching.grid.grid_rows_by_docname[cdn]?.toggle_editable(
			"remark",
			row.result !== "Match"
		);
	},
});

function smr_headline(frm) {
	if (frm.is_new()) return;
	const chips = [];
	chips.push(
		`<span class="indicator blue">${__("Annexures {0}", [
			frm.doc.annexure_progress || "0/0",
		])}</span>`
	);
	const issues = frm.doc.match_issues || 0;
	chips.push(
		issues
			? `<span class="indicator orange">${__("Tally match: {0} issues", [issues])}</span>`
			: `<span class="indicator green">${__("Tally match: OK")}</span>`
	);
	const over = (frm.doc.items || []).filter((r) => r.over_age).length;
	if (over) {
		chips.push(`<span class="indicator red">${__("MTCs: {0} over age", [over])}</span>`);
	}
	frm.dashboard.set_headline_alert(chips.join("&nbsp;&nbsp;"));
	frm.fields_dict.matching?.grid?.wrapper.find(".grid-row").each(function () {
		const name = $(this).attr("data-name");
		const row = (frm.doc.matching || []).find((r) => r.name === name);
		if (row)
			$(this)
				.find('[data-fieldname="result"]')
				.css("color", `var(--${SMR_RESULT_COLOURS[row.result] || "gray"}-600)`);
	});
}

function smr_waive(frm) {
	const lines = (frm.doc.items || []).filter((r) => r.over_age).map((r) => r.line_ref);
	if (!lines.length) {
		frappe.msgprint(__("No line has an over-age MTC."));
		return;
	}
	frappe.prompt(
		[
			{
				fieldname: "line_ref",
				label: __("PO Line"),
				fieldtype: "Select",
				options: lines,
				reqd: 1,
			},
			{
				fieldname: "customer_ref",
				label: __("Customer Approval Ref"),
				fieldtype: "Data",
				reqd: 1,
			},
		],
		(values) =>
			frappe
				.xcall("pvfss.pvfss_quality.doctype.smr.smr.waive_age", {
					smr: frm.doc.name,
					...values,
				})
				.then(() => frm.reload_doc()),
		__("Director waiver (SMR-20)"),
		__("Waive")
	);
}

frappe.ui.form.on("SMR Annexure", {
	annexure_type(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (["MTC", "Tally Sheet"].includes(row.annexure_type)) {
			frappe.model.set_value(cdt, cdn, "reference_doctype", row.annexure_type);
		}
	},
});
