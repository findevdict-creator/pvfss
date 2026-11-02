/* global root_element */
// "Needs your action" strip (screens §19.1). `root_element` is provided by the Custom HTML Block.
const route = frappe.get_route() || [];
const workspace = route[route.length - 1];
const title = root_element.querySelector(".pvfss-actions-title");
const list = root_element.querySelector(".pvfss-actions-list");
title.textContent = __("Needs your action");

frappe.xcall("pvfss.pvfss_reports.actions.get", { workspace }).then((items) => {
	list.innerHTML = "";
	if (!items || !items.length) {
		const empty = document.createElement("span");
		empty.className = "pvfss-actions-empty";
		empty.textContent = __("Nothing is waiting for you.");
		list.appendChild(empty);
		return;
	}
	items.forEach((item) => {
		const chip = document.createElement("span");
		chip.className = "pvfss-action";
		const count = document.createElement("span");
		count.className = "count";
		count.textContent = item.count;
		const label = document.createElement("span");
		label.textContent = item.label;
		chip.appendChild(count);
		chip.appendChild(label);
		chip.addEventListener("click", () => {
			frappe.route_options = item.route_options || {};
			frappe.set_route(item.route);
		});
		list.appendChild(chip);
	});
});
