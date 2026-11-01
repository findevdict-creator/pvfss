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
	# accounting masters linked from every transaction (read so approvers can save them)
	"Account": everyone(),
	"Cost Center": everyone(),
	"Tax Category": everyone(),
	"Item Tax Template": everyone(),
	"Sales Taxes and Charges Template": everyone(),
	"Purchase Taxes and Charges Template": everyone(),
	"Payment Terms Template": everyone(),
	"Terms and Conditions": everyone(),
	"Customer": everyone(**{PBU: "rwc", PBM: "rwc", POU: "rwc", POM: "rwc", FU: "rw", FM: "rw"}),
	"Item": everyone(**{PBU: "rwc", PBM: "rwc", POU: "rwc", POM: "rwc", QU: "rwc", QM: "rwc"}),
	# Address and Contact are left alone: ERPNext ships its own Custom DocPerm rows for them on
	# install (role "All" reads), and duplicating those here would drift on every fresh site.
	"Supplier Group": everyone(),
	"Country": everyone(),
	# ---- Module 2: Supplier management (screens §21: Supplier, AVL, Supplier Evaluation row)
	"Supplier": everyone(**{PBU: "rwc", PBM: "rwc", POU: "rwc", POM: "rwc"}),
	# ---- Module 1: CRM (screens §21: Inquiry row)
	"Opportunity": {PBU: "rwc", PBM: "rwc", DIR: "r", POU: "r", POM: "r", QU: "r", QM: "r", RO: "r"},
	# ---- Module 4: Quotation and Customer PO (screens §21: Quotation, Customer PO rows)
	"Quotation": {
		PBU: "rwcs",
		PBM: "rwcsxa",
		DIR: "rw",
		POU: "r",
		POM: "r",
		FM: "r",
		RO: "r",
	},
	"Sales Order": {
		PBU: "rwc",
		PBM: "rwc",
		POU: "rwcs",
		POM: "rwcsxa",
		DIR: "r",
		FU: "r",
		FM: "rw",
		LOG: "r",
		QU: "r",
		RO: "r",
	},
	"Competitor": everyone(**{PBU: "rwc", PBM: "rwc"}),
	"Quotation Lost Reason": everyone(**{PBM: "rwc"}),
	# ---- Module 3: RFQ and bid comparison (screens §21: RFQ, Supplier Quotation rows)
	"Incoterm": everyone(),
	"Request for Quotation": {PBU: "rwcsxa", PBM: "rwcsxa", POU: "r", POM: "r", DIR: "r", RO: "r"},
	"Supplier Quotation": {
		PBU: "rwcsxa",
		PBM: "rwcsxa",
		POU: "r",
		POM: "r",
		QU: "r",
		QM: "r",
		DIR: "r",
		RO: "r",
	},
}
