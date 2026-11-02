// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-HSE-06: issue (submit) and close the permit.

frappe.ui.form.on("Permit to Work", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && ["Issued", "Expired"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Close permit"), () =>
				frappe.prompt(
					[
						{ fieldname: "area_safe", fieldtype: "Check", label: __("Area left safe"), reqd: 1 },
						{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
					],
					(v) => {
						if (!v.area_safe) return frappe.msgprint(__("Confirm that the area is left safe."));
						frm.set_value("area_safe", 1);
						frm.save("Update").then(() =>
							frappe
								.xcall("pvfss.pvfss_hse.doctype.permit_to_work.permit_to_work.close", {
									permit: frm.doc.name,
									remarks: v.remarks,
								})
								.then(() => frm.reload_doc())
						);
					},
					__("Close permit")
				)
			);
		}
	},
});
