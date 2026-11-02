// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-QA-02: submittal form with "New revision".

frappe.ui.form.on("Quality Document Submittal", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("New revision"), () =>
			frappe
				.xcall(
					"pvfss.pvfss_quality.doctype.quality_document_submittal.quality_document_submittal.new_revision",
					{ submittal: frm.doc.name }
				)
				.then((name) => frappe.set_route("Form", "Quality Document Submittal", name))
		);
	},
});
