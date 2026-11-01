frappe.ui.form.on("Supplier Evaluation", {
	onload(frm) {
		if (frm.is_new() && !(frm.doc.scores || []).length) {
			frappe.db.get_doc("PVFSS Settings").then((s) => {
				(s.supplier_evaluation_criteria || []).forEach((c) =>
					frm.add_child("scores", { criterion: c.criterion, weight_pct: c.weight_pct })
				);
				frm.refresh_field("scores");
			});
		}
	},
});
