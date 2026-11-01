// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
frappe.query_reports["Heat Number Register"] = {
	filters: [
		{ fieldname: "manufacturer", label: __("Manufacturer"), fieldtype: "Link", options: "Manufacturer" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "supplier_po", label: __("Supplier PO"), fieldtype: "Link", options: "Purchase Order" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nActive\nOn hold\nRejected" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "heat" && data && data.heat) {
			const url = `/app/heat-trace?${new URLSearchParams({ type: "Heat Number", key: data.heat })}`;
			value += ` <a class="small" href="${url}">${__("Trace")}</a>`;
		}
		return value;
	},
};
