// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-FIN-15: Petty Cash Voucher with Finance Manager approval above the threshold.

frappe.ui.form.on("Petty Cash Voucher", {
	setup(frm) {
		frm.set_query("cash_account", () => ({
			filters: { company: frm.doc.company, account_type: "Cash", is_group: 0 },
		}));
		frm.set_query("expense_account", () => ({
			filters: { company: frm.doc.company, root_type: "Expense", is_group: 0 },
		}));
	},
	refresh(frm) {
		if (
			frm.doc.docstatus === 0 &&
			!frm.is_new() &&
			frm.doc.approval_required &&
			!frm.doc.approved_by
		) {
			frm.dashboard.set_headline_alert(
				__("Needs Finance Manager approval before submit."),
				"orange"
			);
			if (frappe.user.has_role("Finance Manager")) {
				frm.add_custom_button(__("Approve"), () =>
					frappe
						.xcall(
							"pvfss.pvfss_finance.doctype.petty_cash_voucher.petty_cash_voucher.approve",
							{
								voucher: frm.doc.name,
							}
						)
						.then(() => frm.reload_doc())
				);
			}
		}
	},
});
