// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-FIN-07 / SCR-FIN-08: Letter of Credit actions and presentation checklist.

const LC = "pvfss.pvfss_finance.doctype.letter_of_credit.letter_of_credit";

frappe.ui.form.on("Letter of Credit", {
	setup(frm) {
		frm.set_query("bank_account", () => ({
			filters: { company: frm.doc.company, account_type: "Bank", is_group: 0 },
		}));
	},
	direction(frm) {
		frm.set_value("party_type", frm.doc.direction === "Import" ? "Supplier" : "Customer");
	},
	refresh(frm) {
		if (!frm.doc.party_type && frm.doc.direction) frm.trigger("direction");
		if (frm.doc.docstatus !== 1 || ["Paid", "Expired", "Cancelled"].includes(frm.doc.status))
			return;
		const call = (method, args) =>
			frappe
				.xcall(`${LC}.${method}`, { lc: frm.doc.name, ...(args || {}) })
				.then(() => frm.reload_doc());
		frm.add_custom_button(
			__("Amendment"),
			() =>
				frappe.prompt(
					[
						{
							fieldname: "change",
							fieldtype: "Small Text",
							label: __("Change"),
							reqd: 1,
						},
						{
							fieldname: "amount_change",
							fieldtype: "Currency",
							label: __("Amount Change"),
						},
						{
							fieldname: "new_expiry_date",
							fieldtype: "Date",
							label: __("New Expiry"),
						},
					],
					(v) => call("amend", v),
					__("LC amendment")
				),
			__("Actions")
		);
		frm.add_custom_button(
			__("Presentation checklist"),
			() => checklist(frm, call),
			__("Actions")
		);
		if (frm.doc.status === "Documents presented")
			frm.add_custom_button(
				__("Accepted"),
				() => call("set_status", { status: "Accepted" }),
				__("Actions")
			);
		if (["Accepted", "Documents presented"].includes(frm.doc.status))
			frm.add_custom_button(
				__("Paid"),
				() => call("set_status", { status: "Paid" }),
				__("Actions")
			);
		frm.add_custom_button(
			__("Expired"),
			() => call("set_status", { status: "Expired" }),
			__("Actions")
		);
		if (!frm.doc.charges_journal_entry)
			frm.add_custom_button(
				__("Post margin / charges JE"),
				() => call("post_charges"),
				__("Actions")
			);
	},
});

function checklist(frm, call) {
	frappe.xcall(`${LC}.presentation_checklist`, { lc: frm.doc.name }).then((rows) => {
		const esc = frappe.utils.escape_html;
		const body = rows
			.map(
				(r) =>
					`<tr><td>${esc(r.document)}</td><td>${r.available ? "✓" : "✗"} ${esc(
						r.dn_status
					)}</td><td>${esc(r.discrepancy || "")}</td></tr>`
			)
			.join("");
		const d = new frappe.ui.Dialog({
			title: __("LC document presentation checklist"),
			fields: [{ fieldtype: "HTML", fieldname: "table" }],
			primary_action_label: __("Mark presented"),
			primary_action() {
				d.hide();
				call("mark_presented");
			},
		});
		d.fields_dict.table.$wrapper.html(
			`<table class="table table-bordered"><thead><tr><th>${__("Document")}</th><th>${__(
				"On Delivery Note"
			)}</th><th>${__("Discrepancy")}</th></tr></thead><tbody>${body}</tbody></table>`
		);
		d.show();
	});
}
