// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors

frappe.query_reports["Revenue and VC by Project"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date" },
	],
	onload(report) {
		report.page.add_inner_button(__("Settle VC"), () => {
			const row = report.datatable && report.datatable.rowmanager.getCheckedRows()[0];
			const so = row !== undefined ? report.data[row].sales_order : null;
			if (!so)
				return frappe.msgprint(
					__("Open the Customer PO and use Finance ▸ Settle variable consideration.")
				);
			frappe.set_route("Form", "Sales Order", so);
		});
	},
};
