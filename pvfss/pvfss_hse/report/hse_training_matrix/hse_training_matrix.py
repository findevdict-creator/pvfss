"""HSE Training Matrix (HSE-20, SCR-HSE-08): employees x required courses."""

import frappe
from frappe import _

from pvfss.pvfss_hse.doctype.hse_training_record.hse_training_record import training_status


def execute(filters=None):
	filters = frappe._dict(filters or {})
	course_filters = {"name": filters.course} if filters.course else {}
	courses = [
		frappe.get_doc("HSE Course", c)
		for c in frappe.get_all("HSE Course", filters=course_filters, pluck="name", order_by="name")
	]
	emp_filters = {"status": "Active"}
	if filters.department:
		emp_filters["department"] = filters.department
	employees = frappe.get_all(
		"Employee",
		filters=emp_filters,
		fields=["name", "employee_name", "department", "designation"],
		order_by="employee_name",
	)
	latest = {}
	for row in frappe.get_all(
		"HSE Training Record",
		filters={"employee": ["in", [e.name for e in employees] or [""]]},
		fields=["employee", "course", "training_date", "expiry_date"],
		order_by="training_date asc",
	):
		latest[(row.employee, row.course)] = row
	columns = [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 110,
		},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Data", "width": 120},
	]
	keys = {}
	for course in courses:
		key = frappe.scrub(course.name)
		keys[course.name] = key
		columns.append({"fieldname": key, "label": course.name, "fieldtype": "Data", "width": 150})
	data = []
	for emp in employees:
		row = {"employee": emp.name, "employee_name": emp.employee_name, "department": emp.department}
		for course in courses:
			record = latest.get((emp.name, course.name))
			if record:
				status = training_status(record.expiry_date)
				label = _(status) + (
					f" ({frappe.utils.formatdate(record.expiry_date)})" if record.expiry_date else ""
				)
			elif course.required_for(emp):
				status, label = "Missing", _("Missing")
			else:
				continue
			row[keys[course.name]] = label
			row[keys[course.name] + "_status"] = status
		data.append(row)
	return columns, data
