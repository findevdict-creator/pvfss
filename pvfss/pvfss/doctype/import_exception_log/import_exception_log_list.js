// SCR-GEN-05: default filter Reviewed = No, bulk "Mark reviewed".

frappe.listview_settings["Import Exception Log"] = {
	add_fields: ["reviewed"],
	filters: [["reviewed", "=", 0]],
	get_indicator(doc) {
		return doc.reviewed
			? [__("Reviewed"), "green", "reviewed,=,1"]
			: [__("To review"), "orange", "reviewed,=,0"];
	},
	onload(listview) {
		listview.page.add_action_item(__("Mark reviewed"), () => {
			const names = listview.get_checked_items(true);
			if (!names.length) return;
			frappe
				.xcall(
					"pvfss.pvfss.doctype.import_exception_log.import_exception_log.mark_reviewed",
					{ names }
				)
				.then(() => listview.refresh());
		});
	},
};
