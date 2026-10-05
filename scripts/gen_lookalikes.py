"""Generate synthetic invoice-lookalike documents (NOT invoices) as PDF and DOCX.

Document types: purchase order, quotation, delivery note, packing slip, payslip,
bank statement, expense report, remittance advice, timesheet, credit application.
All names, addresses and numbers are fictional (Faker).
"""
import random, sys, os
from datetime import timedelta
from faker import Faker
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, KeepTogether)
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUT = sys.argv[1]
N = int(sys.argv[2])
SEED = 7
random.seed(SEED)
fake = Faker(["en_US", "en_GB", "en_IN", "de_DE", "fr_FR"])
Faker.seed(SEED)
os.makedirs(OUT, exist_ok=True)

FONTS = ["Helvetica", "Times-Roman", "Courier"]
ACCENTS = [colors.HexColor(c) for c in
           ["#1f3b73", "#8b0000", "#006400", "#444444", "#b35900", "#2e2e2e", "#4b0082", "#008080"]]
CURR = ["$", "€", "£", "₹", "CHF ", "AUD "]


def money(v, c):
    return f"{c}{v:,.2f}"


def company():
    return dict(name=fake.company(), addr=fake.address().replace("\n", ", "),
                phone=fake.phone_number(), email=fake.company_email(), web=fake.domain_name())


def line_items(n=None, qty_max=20, price_max=900):
    n = n or random.randint(2, 9)
    items = []
    for _ in range(n):
        q = random.randint(1, qty_max)
        p = round(random.uniform(3, price_max), 2)
        items.append((fake.bs().title() if random.random() < .5 else fake.catch_phrase(), q, p, round(q * p, 2)))
    return items


# ----------------------------------------------------------------------------
# Content builders: return dict(title, meta[(k,v)], parties[(label, company)],
#                               table(header, rows), totals[(k,v)], notes[str])
# ----------------------------------------------------------------------------
def doc_purchase_order():
    c = random.choice(CURR); items = line_items()
    sub = sum(i[3] for i in items)
    d = fake.date_this_year()
    return dict(title=random.choice(["PURCHASE ORDER", "Purchase Order", "P.O."]),
                meta=[("PO Number", f"PO-{random.randint(10000, 99999)}"), ("Order Date", d.isoformat()),
                      ("Required By", (d + timedelta(days=random.randint(7, 45))).isoformat()),
                      ("Payment Terms", random.choice(["Net 30", "Net 45", "Net 60", "2/10 Net 30"])),
                      ("Shipping Method", random.choice(["Ground", "Air Freight", "Courier", "Sea"]))],
                parties=[("Buyer", company()), ("Vendor", company()), ("Ship To", company())],
                table=(["Item", "Description", "Qty", "Unit Price", "Amount"],
                       [[str(i + 1), it[0], it[1], money(it[2], c), money(it[3], c)] for i, it in enumerate(items)]),
                totals=[("Subtotal", money(sub, c)), ("Shipping", money(random.uniform(0, 200), c)),
                        ("Order Total", money(sub * 1.05, c))],
                notes=["This purchase order is subject to the buyer's standard terms and conditions.",
                       "Please confirm receipt and expected delivery date.",
                       "Quote PO number on all correspondence and packing documents."])


def doc_quotation():
    c = random.choice(CURR); items = line_items()
    sub = sum(i[3] for i in items); d = fake.date_this_year()
    return dict(title=random.choice(["QUOTATION", "Quote", "PRICE QUOTE", "Sales Quotation", "ESTIMATE"]),
                meta=[("Quote No.", f"Q-{random.randint(1000, 9999)}"), ("Date", d.isoformat()),
                      ("Valid Until", (d + timedelta(days=30)).isoformat()),
                      ("Prepared By", fake.name()), ("Reference", fake.bothify("REF-??##??"))],
                parties=[("Prepared For", company()), ("From", company())],
                table=(["#", "Description", "Qty", "Rate", "Total"],
                       [[str(i + 1), it[0], it[1], money(it[2], c), money(it[3], c)] for i, it in enumerate(items)]),
                totals=[("Subtotal", money(sub, c)), ("Discount", f"-{money(sub * 0.05, c)}"),
                        ("Estimated Tax", money(sub * 0.08, c)), ("Estimated Total", money(sub * 1.03, c))],
                notes=["This is a quotation only and does not constitute a bill.",
                       "Prices are valid for 30 days from the date above.",
                       "To accept this quote, sign below and return a copy."])


def doc_delivery_note():
    items = line_items(qty_max=50); d = fake.date_this_year()
    return dict(title=random.choice(["DELIVERY NOTE", "Packing Slip", "PACKING LIST", "Goods Received Note", "Despatch Note"]),
                meta=[("Delivery No.", f"DN-{random.randint(100000, 999999)}"), ("Date", d.isoformat()),
                      ("Order Ref", f"SO-{random.randint(10000, 99999)}"), ("Carrier", random.choice(["DHL", "FedEx", "UPS", "DPD", "Own fleet"])),
                      ("Tracking", fake.bothify("??########??")), ("Packages", str(random.randint(1, 12)))],
                parties=[("Deliver To", company()), ("Shipped From", company())],
                table=(["Line", "SKU", "Description", "Ordered", "Shipped", "Backorder"],
                       [[str(i + 1), fake.bothify("SKU-####-??"), it[0], it[1], it[1] - random.randint(0, min(2, it[1] - 1)) if it[1] > 1 else it[1], random.choice([0, 0, 0, 1, 2])] for i, it in enumerate(items)]),
                totals=[("Total Packages", str(random.randint(1, 12))), ("Gross Weight", f"{random.uniform(2, 400):.1f} kg")],
                notes=["Goods received in good condition: ______________________  Date: __________",
                       "Please check contents against this note before signing.", "No prices shown. This is not a tax document."])


def doc_payslip():
    c = random.choice(CURR); gross = round(random.uniform(1800, 9000), 2)
    tax = round(gross * random.uniform(.1, .3), 2); ni = round(gross * .08, 2); pens = round(gross * .05, 2)
    d = fake.date_this_year()
    return dict(title=random.choice(["PAYSLIP", "Pay Statement", "SALARY SLIP", "Earnings Statement"]),
                meta=[("Employee ID", fake.bothify("EMP####")), ("Pay Period", f"{(d - timedelta(days=30)).isoformat()} to {d.isoformat()}"),
                      ("Pay Date", d.isoformat()), ("Department", random.choice(["Finance", "Operations", "Engineering", "Sales", "HR"])),
                      ("Tax Code", fake.bothify("####L")), ("Payment Method", "Bank Transfer")],
                parties=[("Employer", company()), ("Employee", dict(name=fake.name(), addr=fake.address().replace("\n", ", "), phone="", email="", web=""))],
                table=(["Earnings", "Hours", "Rate", "Amount", "Deductions", "Amount "],
                       [["Basic Salary", "160", money(gross / 160, c), money(gross, c), "Income Tax", money(tax, c)],
                        ["Overtime", str(random.randint(0, 20)), money(gross / 160 * 1.5, c), money(random.uniform(0, 500), c), "Social Insurance", money(ni, c)],
                        ["Allowance", "", "", money(random.uniform(0, 300), c), "Pension", money(pens, c)]]),
                totals=[("Gross Pay", money(gross, c)), ("Total Deductions", money(tax + ni + pens, c)), ("NET PAY", money(gross - tax - ni - pens, c)),
                        ("YTD Gross", money(gross * random.randint(1, 11), c))],
                notes=["This document is a statement of earnings, not a request for payment.", "Retain for your records."])


def doc_bank_statement():
    c = random.choice(CURR); d = fake.date_this_year(); bal = round(random.uniform(500, 20000), 2)
    rows = []; running = bal
    for i in range(random.randint(8, 18)):
        amt = round(random.uniform(-900, 600), 2); running = round(running + amt, 2)
        rows.append([(d + timedelta(days=i * 2)).isoformat(), random.choice(["POS", "TFR", "DD", "ATM", "BGC", "SO"]),
                     fake.company()[:28], money(-amt, c) if amt < 0 else "", money(amt, c) if amt >= 0 else "", money(running, c)])
    return dict(title=random.choice(["BANK STATEMENT", "Account Statement", "Statement of Account"]),
                meta=[("Account No.", fake.bban()), ("Sort Code / IBAN", fake.iban()), ("Statement Period", f"{d.isoformat()} – {(d + timedelta(days=30)).isoformat()}"),
                      ("Statement No.", str(random.randint(1, 240))), ("Currency", c.strip() or "USD")],
                parties=[("Account Holder", company()), ("Branch", company())],
                table=(["Date", "Type", "Description", "Paid Out", "Paid In", "Balance"], rows),
                totals=[("Opening Balance", money(bal, c)), ("Closing Balance", money(running, c))],
                notes=["Please check your statement carefully and report any discrepancies within 60 days.",
                       "Interest rates and charges are shown in our published tariff."])


def doc_expense_report():
    c = random.choice(CURR); d = fake.date_this_year()
    rows = [[(d + timedelta(days=random.randint(0, 20))).isoformat(), random.choice(["Travel", "Meals", "Lodging", "Mileage", "Supplies", "Client Entertainment"]),
             fake.sentence(nb_words=5), random.choice(["Yes", "No"]), money(random.uniform(5, 600), c)] for _ in range(random.randint(4, 12))]
    tot = sum(float(r[4].replace(c, "").replace(",", "")) for r in rows)
    return dict(title=random.choice(["EXPENSE REPORT", "Expense Claim Form", "Travel & Expense Statement", "Reimbursement Request"]),
                meta=[("Report No.", f"EXP-{random.randint(1000, 9999)}"), ("Employee", fake.name()), ("Cost Centre", fake.bothify("CC-###")),
                      ("Submitted", d.isoformat()), ("Approver", fake.name()), ("Purpose", fake.catch_phrase())],
                parties=[("Submitted To", company())],
                table=(["Date", "Category", "Description", "Receipt?", "Amount"], rows),
                totals=[("Total Expenses", money(tot, c)), ("Less Advance", money(random.uniform(0, 300), c)), ("Amount Due to Employee", money(tot * .9, c))],
                notes=["Employee signature: ______________________   Manager approval: ______________________",
                       "Attach original receipts for all items above 25."])


def doc_remittance():
    c = random.choice(CURR); d = fake.date_this_year()
    rows = [[f"INV-{random.randint(10000, 99999)}", (d - timedelta(days=random.randint(10, 80))).isoformat(), money(random.uniform(50, 5000), c),
             money(random.uniform(0, 50), c), money(random.uniform(50, 5000), c)] for _ in range(random.randint(3, 10))]
    return dict(title=random.choice(["REMITTANCE ADVICE", "Payment Advice", "Payment Notification", "Remittance Statement"]),
                meta=[("Payment Ref", fake.bothify("PAY########")), ("Payment Date", d.isoformat()), ("Method", random.choice(["ACH", "Wire", "BACS", "SEPA", "Cheque"])),
                      ("Bank Ref", fake.bothify("##########")), ("Currency", c.strip() or "USD")],
                parties=[("Payee", company()), ("Payer", company())],
                table=(["Your Reference", "Doc Date", "Gross", "Discount", "Paid"], rows),
                totals=[("Total Remitted", money(sum(float(r[4].replace(c, "").replace(",", "")) for r in rows), c))],
                notes=["This advice confirms payment already made. No action is required.",
                       "Queries: accounts.payable@" + fake.domain_name()])


def doc_timesheet():
    d = fake.date_this_year(); rows = []
    for i in range(random.randint(5, 14)):
        h = random.choice([0, 4, 7.5, 8, 8, 8, 9, 10])
        rows.append([(d + timedelta(days=i)).strftime("%a %d %b"), fake.bothify("PRJ-###"), fake.bs().title()[:30], f"{h:.1f}", f"{max(0, h - 8):.1f}", random.choice(["Approved", "Pending", "Approved"])])
    return dict(title=random.choice(["TIMESHEET", "Weekly Timesheet", "Time Record", "Labour Hours Report"]),
                meta=[("Employee", fake.name()), ("Employee No.", fake.bothify("E#####")), ("Week Ending", (d + timedelta(days=6)).isoformat()),
                      ("Manager", fake.name()), ("Contract", random.choice(["Full-time", "Part-time", "Contractor"]))],
                parties=[("Company", company()), ("Client / Site", company())],
                table=(["Day", "Project", "Task", "Hours", "Overtime", "Status"], rows),
                totals=[("Total Hours", f"{sum(float(r[3]) for r in rows):.1f}"), ("Total Overtime", f"{sum(float(r[4]) for r in rows):.1f}")],
                notes=["Submitted hours are subject to manager approval.", "Signature: ______________________  Date: __________"])


def doc_credit_application():
    d = fake.date_this_year()
    return dict(title=random.choice(["CREDIT APPLICATION", "Trade Account Application", "Customer Account Form", "Supplier Registration Form"]),
                meta=[("Application No.", fake.bothify("APP-#####")), ("Date", d.isoformat()), ("Requested Limit", money(random.choice([5000, 10000, 25000, 50000]), random.choice(CURR))),
                      ("Trading Since", str(random.randint(1980, 2023))), ("Company Reg. No.", fake.bothify("########")), ("VAT / Tax ID", fake.bothify("??#########"))],
                parties=[("Applicant", company()), ("Trade Reference 1", company()), ("Trade Reference 2", company())],
                table=(["Director / Owner", "Title", "Date of Birth", "Share %"],
                       [[fake.name(), random.choice(["Director", "CEO", "CFO", "Partner", "Owner"]), fake.date_of_birth(minimum_age=30, maximum_age=70).isoformat(), str(random.choice([100, 50, 33, 25]))] for _ in range(random.randint(1, 4))]),
                totals=[],
                notes=["I/We authorise the supplier to obtain credit references and bank reports.",
                       "Signed: ______________________  Position: ______________  Date: __________",
                       fake.paragraph(nb_sentences=3)])


BUILDERS = [doc_purchase_order, doc_quotation, doc_delivery_note, doc_payslip, doc_bank_statement,
            doc_expense_report, doc_remittance, doc_timesheet, doc_credit_application]


# ----------------------------------------------------------------------------
# Renderers
# ----------------------------------------------------------------------------
def render_pdf(d, path):
    font = random.choice(FONTS); bold = font + ("-Bold" if font != "Times-Roman" else "-Bold")
    if font == "Times-Roman": bold = "Times-Bold"
    accent = random.choice(ACCENTS); pagesize = random.choice([A4, LETTER])
    ss = getSampleStyleSheet()
    base = ParagraphStyle("b", parent=ss["Normal"], fontName=font, fontSize=random.choice([8.5, 9, 10]), leading=12)
    small = ParagraphStyle("s", parent=base, fontSize=7.5, leading=9, textColor=colors.grey)
    h = ParagraphStyle("h", parent=base, fontName=bold, fontSize=random.choice([16, 20, 24]), textColor=accent,
                       alignment=random.choice([0, 2]), spaceAfter=6)
    lab = ParagraphStyle("l", parent=base, fontName=bold, textColor=accent, fontSize=base.fontSize)
    doc = SimpleDocTemplate(path, pagesize=pagesize, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    W = pagesize[0] - 36 * mm
    story = []
    # header: company block + title
    co = d["parties"][random.randint(0, len(d["parties"]) - 1)][1]
    hdr_left = Paragraph(f"<b>{co['name']}</b><br/>{co['addr']}<br/>{co['phone']} · {co['email']}", base)
    hdr_right = Paragraph(d["title"], h)
    if random.random() < .5:
        story.append(Table([[hdr_left, hdr_right]], colWidths=[W * .55, W * .45], style=[("VALIGN", (0, 0), (-1, -1), "TOP")]))
    else:
        story += [hdr_right, hdr_left]
    story.append(Spacer(1, 4)); story.append(HRFlowable(width="100%", thickness=random.choice([0.5, 1.5, 3]), color=accent)); story.append(Spacer(1, 8))
    # meta
    meta_rows = [[Paragraph(k, lab), Paragraph(v, base)] for k, v in d["meta"]]
    half = (len(meta_rows) + 1) // 2
    mt = Table([(meta_rows[i] + (meta_rows[i + half] if i + half < len(meta_rows) else ["", ""])) for i in range(half)],
               colWidths=[W * .17, W * .33, W * .17, W * .33])
    if random.random() < .5: mt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke), ("BOX", (0, 0), (-1, -1), .5, colors.lightgrey)]))
    story += [mt, Spacer(1, 10)]
    # parties
    pcells = [Paragraph(f"<font color='{accent.hexval()}'><b>{lbl}</b></font><br/>{c['name']}<br/>{c['addr']}" + (f"<br/>{c['email']}" if c['email'] else ""), base) for lbl, c in d["parties"]]
    story += [Table([pcells], colWidths=[W / len(pcells)] * len(pcells), style=[("VALIGN", (0, 0), (-1, -1), "TOP")]), Spacer(1, 12)]
    # table
    header, rows = d["table"]
    data = [[Paragraph(f"<b>{x}</b>", base) for x in header]] + [[Paragraph(str(x), base) for x in r] for r in rows]
    t = Table(data, repeatRows=1, colWidths=[W / len(header)] * len(header))
    style = [("BACKGROUND", (0, 0), (-1, 0), accent if random.random() < .6 else colors.lightgrey),
             ("TEXTCOLOR", (0, 0), (-1, 0), colors.white if random.random() < .6 else colors.black),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    style += random.choice([[("GRID", (0, 0), (-1, -1), .4, colors.grey)],
                            [("LINEBELOW", (0, 0), (-1, -1), .3, colors.lightgrey)],
                            [("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]), ("BOX", (0, 0), (-1, -1), .5, colors.grey)]])
    t.setStyle(TableStyle(style)); story += [t, Spacer(1, 8)]
    # totals
    if d["totals"]:
        tt = Table([[Paragraph(k, lab if i == len(d["totals"]) - 1 else base), Paragraph(v, lab if i == len(d["totals"]) - 1 else base)] for i, (k, v) in enumerate(d["totals"])],
                   colWidths=[W * .25, W * .2], hAlign="RIGHT", style=[("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEABOVE", (0, -1), (-1, -1), 1, accent)])
        story += [tt, Spacer(1, 14)]
    for n in d["notes"]: story.append(Paragraph(n, small))
    story += [Spacer(1, 6), Paragraph(f"{co['web']} · Generated document, fictional data · Page 1", small)]
    doc.build(story)


def render_docx(d, path):
    doc = Document(); sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Inches(random.choice([0.7, 0.9, 1.0]))
    font = random.choice(["Calibri", "Arial", "Times New Roman", "Georgia", "Cambria", "Consolas"])
    accent = random.choice(["1F3B73", "8B0000", "006400", "444444", "B35900", "4B0082", "008080"])
    st = doc.styles["Normal"]; st.font.name = font; st.font.size = Pt(random.choice([9, 10, 11]))
    co = d["parties"][random.randint(0, len(d["parties"]) - 1)][1]
    p = doc.add_paragraph(); r = p.add_run(d["title"]); r.bold = True; r.font.size = Pt(random.choice([18, 22, 26])); r.font.color.rgb = RGBColor.from_string(accent)
    p.alignment = random.choice([WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.CENTER])
    p = doc.add_paragraph(); r = p.add_run(co["name"]); r.bold = True; p.add_run(f"\n{co['addr']}\n{co['phone']}  {co['email']}")
    # meta table
    half = (len(d["meta"]) + 1) // 2
    t = doc.add_table(rows=half, cols=4); t.style = random.choice(["Table Grid", "Light Shading", "Light List", "Medium Shading 1"])
    for i in range(half):
        for j, idx in enumerate([i, i + half]):
            if idx < len(d["meta"]):
                k, v = d["meta"][idx]; c1 = t.cell(i, j * 2); c2 = t.cell(i, j * 2 + 1)
                c1.text = k; c1.paragraphs[0].runs[0].bold = True; c2.text = v
    doc.add_paragraph()
    pt = doc.add_table(rows=1, cols=len(d["parties"]))
    for j, (lbl, c) in enumerate(d["parties"]):
        cell = pt.cell(0, j); rr = cell.paragraphs[0].add_run(lbl); rr.bold = True; rr.font.color.rgb = RGBColor.from_string(accent)
        cell.add_paragraph(f"{c['name']}\n{c['addr']}" + (f"\n{c['email']}" if c["email"] else ""))
    doc.add_paragraph()
    header, rows = d["table"]
    t = doc.add_table(rows=1 + len(rows), cols=len(header)); t.style = random.choice(["Table Grid", "Light Grid Accent 1", "Medium Grid 1 Accent 1", "Light List Accent 1", "Medium List 1"])
    for j, hcell in enumerate(header):
        c = t.cell(0, j); c.text = str(hcell); c.paragraphs[0].runs[0].bold = True
    for i, row in enumerate(rows):
        for j, v in enumerate(row): t.cell(i + 1, j).text = str(v)
    doc.add_paragraph()
    for i, (k, v) in enumerate(d["totals"]):
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r = p.add_run(f"{k}:    {v}"); r.bold = (i == len(d["totals"]) - 1)
    doc.add_paragraph()
    for n in d["notes"]:
        p = doc.add_paragraph(n); p.runs[0].font.size = Pt(8); p.runs[0].font.color.rgb = RGBColor(0x80, 0x80, 0x80)
    doc.save(path)


# ----------------------------------------------------------------------------
pdf_share = 0.75
counts = {}
for i in range(N):
    b = random.choice(BUILDERS); d = b()
    kind = b.__name__.replace("doc_", "")
    ext = "pdf" if random.random() < pdf_share else "docx"
    path = os.path.join(OUT, f"lookalike_{kind}_{i + 1:03d}.{ext}")
    (render_pdf if ext == "pdf" else render_docx)(d, path)
    counts[(kind, ext)] = counts.get((kind, ext), 0) + 1
for k in sorted(counts): print(k, counts[k])
print("total", sum(counts.values()))
