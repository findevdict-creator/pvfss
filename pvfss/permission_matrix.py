"""Role permission matrix (GEN-21, screens §21). Pure data: imported by hooks.py.

Rights: r = read, w = write, c = create, s = submit, x = cancel, a = amend, d = delete,
e = export/print/email/report (always added with r).
Each module branch adds the DocTypes it owns. ``pvfss.setup.permissions.apply`` writes these
as Custom DocPerm rows on a developer site; they ship as fixtures.
"""

DIR = "PVFSS Director"
PBU = "Pre-Bidding User"
PBM = "Pre-Bidding Manager"
POU = "Post-Bidding User"
POM = "Post-Bidding Manager"
QU = "Quality User"
QM = "Quality Manager"
LOG = "Logistics User"
FU = "Finance User"
FM = "Finance Manager"
HSEU = "HSE User"
HSEM = "HSE Manager"
ICV = "ICV User"
RO = "PVFSS Read Only"

ALL = (DIR, PBU, PBM, POU, POM, QU, QM, LOG, FU, FM, HSEU, HSEM, ICV, RO)


def everyone(rights="r", **overrides):
	out = dict.fromkeys(ALL, rights)
	out.update(overrides)
	return out


MATRIX = {
	# ---- shared masters every PVFSS user reads (link fields on every form)
	"Company": everyone(),
	"Currency": everyone(),
	"Item Group": everyone(),
	"UOM": everyone(),
	"Item Attribute": everyone(),
	"Territory": everyone(),
	"Customer Group": everyone(),
	"Price List": everyone(),
	"Warehouse": everyone(),
	"Opportunity Lost Reason": everyone(**{PBM: "rwc"}),
	"Customer": everyone(**{PBU: "rwc", PBM: "rwc", POU: "rwc", POM: "rwc", FU: "rw", FM: "rw"}),
	"Item": everyone(**{PBU: "rwc", PBM: "rwc", POU: "rwc", POM: "rwc", QU: "rwc", QM: "rwc"}),
	# Address and Contact are left alone: ERPNext ships its own Custom DocPerm rows for them on
	# install (role "All" reads), and duplicating those here would drift on every fresh site.
	# ---- Module 1: CRM (screens §21: Inquiry row)
	"Opportunity": {PBU: "rwc", PBM: "rwc", DIR: "r", POU: "r", POM: "r", QU: "r", QM: "r", RO: "r"},
}
