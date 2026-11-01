// Supplier list (SCR-SUP-01): approval status pills.

const PVFSS_SUPPLIER_COLOURS = {
	Prospect: "gray",
	Approved: "green",
	"Conditionally approved": "orange",
	Suspended: "red",
	Blacklisted: "red",
};

frappe.listview_settings["Supplier"] = {
	add_fields: ["pvfss_approval_status", "disabled"],
	get_indicator(doc) {
		if (doc.disabled) return [__("Disabled"), "gray", "disabled,=,1"];
		const status = doc.pvfss_approval_status || "Prospect";
		return [__(status), PVFSS_SUPPLIER_COLOURS[status] || "gray", `pvfss_approval_status,=,${status}`];
	},
};
