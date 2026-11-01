// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Import Exception Log", {
	refresh(frm) {
		if (!frm.doc.reviewed && frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Mark reviewed"), () => {
				frappe
					.xcall(
						"pvfss.pvfss.doctype.import_exception_log.import_exception_log.mark_reviewed",
						{ names: [frm.doc.name], remark: frm.doc.remark }
					)
					.then(() => frm.reload_doc());
			}).addClass("btn-primary");
		}
	},
});
