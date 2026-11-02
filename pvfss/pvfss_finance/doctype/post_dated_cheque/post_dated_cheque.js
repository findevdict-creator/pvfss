// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-FIN-10: Post-Dated Cheque actions by status.

const PDC = "pvfss.pvfss_finance.doctype.post_dated_cheque.post_dated_cheque";

frappe.ui.form.on("Post-Dated Cheque", {
	setup(frm) {
		frm.set_query("bank_account", () => ({
			filters: { company: frm.doc.company, account_type: "Bank", is_group: 0 },
		}));
		frm.set_query("invoice", "invoices", () => ({
			filters: {
				docstatus: 1,
				outstanding_amount: [">", 0],
				[frm.doc.direction === "Issued" ? "supplier" : "customer"]: frm.doc.party,
			},
		}));
	},
	direction(frm) {
		frm.set_value("party_type", frm.doc.direction === "Issued" ? "Supplier" : "Customer");
	},
	refresh(frm) {
		if (!frm.doc.party_type && frm.doc.direction) frm.trigger("direction");
		if (frm.doc.docstatus !== 1) return;
		const call = (method, args) =>
			frappe.xcall(`${PDC}.${method}`, { pdc: frm.doc.name, ...(args || {}) }).then((r) => {
				frm.reload_doc();
				if (method === "replace") frappe.set_route("Form", "Post-Dated Cheque", r);
			});
		const bank = (method, label) =>
			frappe.prompt(
				[
					{
						fieldname: "bank_account",
						fieldtype: "Link",
						options: "Account",
						label: __("Bank Account"),
						reqd: 1,
						default: frm.doc.bank_account,
						get_query: () => ({ filters: { company: frm.doc.company, account_type: "Bank", is_group: 0 } }),
					},
				],
				(v) => call(method, v),
				label
			);
		const s = frm.doc.status;
		if (s === "In hand") frm.add_custom_button(__("Deposit"), () => bank("deposit", __("Deposit")));
		if (s === "Deposited") {
			frm.add_custom_button(__("Mark cleared"), () => call("clear"));
			frm.add_custom_button(__("Mark bounced"), () => call("bounce"));
		}
		if (s === "Bounced") frm.add_custom_button(__("Replace"), () => call("replace"));
		if (s === "Issued") frm.add_custom_button(__("Presented"), () => call("present"));
		if (["Issued", "Presented"].includes(s)) {
			frm.add_custom_button(__("Mark cleared"), () => bank("clear", __("Cleared")));
			frm.add_custom_button(__("Stop"), () => call("stop"));
		}
	},
});
