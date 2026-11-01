// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-QA-08: RFI form. Schedule (QA-12 hold rule on the server), reschedule, cancel, inspect.

const RFI_API = "pvfss.pvfss_quality.doctype.rfi.rfi.";

frappe.ui.form.on("RFI", {
	setup(frm) {
		frm.set_query("itp", () => ({
			filters: { docstatus: 1, supplier_po: frm.doc.supplier_po },
		}));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		const status = frm.doc.status;
		if (status === "Raised") {
			frm.add_custom_button(__("Schedule"), () =>
				frappe.prompt(
					[
						{
							fieldname: "scheduled_date",
							label: __("Date"),
							fieldtype: "Date",
							default: frm.doc.proposed_date,
							reqd: 1,
						},
					],
					(v) =>
						frappe
							.xcall(RFI_API + "schedule", { rfi: frm.doc.name, ...v })
							.then(() => frm.reload_doc()),
					__("Schedule inspection")
				)
			);
		}
		if (["Scheduled", "Rescheduled"].includes(status)) {
			frm.add_custom_button(__("Reschedule"), () =>
				frappe.prompt(
					[
						{
							fieldname: "new_date",
							label: __("New date"),
							fieldtype: "Date",
							reqd: 1,
						},
						{
							fieldname: "reason",
							label: __("Reason"),
							fieldtype: "Small Text",
							reqd: 1,
						},
					],
					(v) =>
						frappe
							.xcall(RFI_API + "reschedule", { rfi: frm.doc.name, ...v })
							.then(() => frm.reload_doc()),
					__("Reschedule")
				)
			);
			frm.add_custom_button(
				__("Inspection Report"),
				() =>
					frappe
						.xcall(RFI_API + "make_inspection_report", { rfi: frm.doc.name })
						.then((name) => frappe.set_route("Form", "Inspection Report", name)),
				__("Create")
			);
		}
		if (!["Closed", "Cancelled"].includes(status)) {
			frm.add_custom_button(__("Cancel RFI"), () =>
				frappe.prompt(
					[
						{
							fieldname: "reason",
							label: __("Reason"),
							fieldtype: "Small Text",
							reqd: 1,
						},
					],
					(v) =>
						frappe
							.xcall(RFI_API + "cancel_rfi", { rfi: frm.doc.name, ...v })
							.then(() => frm.reload_doc()),
					__("Cancel RFI")
				)
			);
		}
	},
});
