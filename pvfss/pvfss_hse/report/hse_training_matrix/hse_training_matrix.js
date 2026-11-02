// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors

const PVFSS_TRAINING_COLOURS = {
	Valid: "green",
	Expiring: "orange",
	Expired: "red",
	Missing: "gray",
};

frappe.query_reports["HSE Training Matrix"] = {
	filters: [
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{ fieldname: "course", label: __("Course"), fieldtype: "Link", options: "HSE Course" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const status = data && data[column.fieldname + "_status"];
		if (status)
			value = `<span class="indicator-pill ${PVFSS_TRAINING_COLOURS[status]}">${value}</span>`;
		return value;
	},
};
