"""Generate matching email header/body .txt files for every attachment.

Attachments/invoices/X.jpg  -> Email/Header/invoice/X.txt + Email/Body/invoice/X.txt
Attachments/random/Y.ext    -> Email/Header/random/Y.txt  + Email/Body/random/Y.txt
"""
import os, random, sys, re
from datetime import datetime, timedelta
from faker import Faker

ROOT = sys.argv[1]
SEED = 11
random.seed(SEED); fake = Faker(["en_US", "en_GB", "en_IN"]); Faker.seed(SEED)

ATT = os.path.join(ROOT, "Attachments")
EM = os.path.join(ROOT, "Email")
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAILERS = ["Microsoft Outlook 16.0", "Apple Mail (2.3774.500.171)", "Gmail", "Mozilla Thunderbird", "Zoho Mail", "SAP Ariba Notifier", "QuickBooks Online"]


def dom(company_name):
    w = re.sub(r"[^a-z]", "", company_name.split()[0].lower()) or "corp"
    return w + random.choice([".com", ".com", ".co.uk", ".in", ".net", ".io"])


def person(domain=None):
    n = fake.name(); d = domain or fake.domain_name()
    return n, f"{n.split()[0].lower()}.{n.split()[-1].lower()}@{d}"


def header(fr, to, subject, dt, fname, cc=None, reply_to=None, priority=None):
    ext = os.path.splitext(fname)[1].lower()
    lines = [f"From: {fr[0]} <{fr[1]}>", f"To: {to[0]} <{to[1]}>"]
    if cc: lines.append(f"Cc: {cc[0]} <{cc[1]}>")
    if reply_to: lines.append(f"Reply-To: {reply_to}")
    lines += [f"Date: {dt.strftime('%a, %d %b %Y %H:%M:%S')} {random.choice(['+0000', '+0100', '+0530', '-0500', '-0800', '+0200'])}",
              f"Subject: {subject}",
              f"Message-ID: <{fake.uuid4()}@{fr[1].split('@')[1]}>",
              f"X-Mailer: {random.choice(MAILERS)}", "MIME-Version: 1.0"]
    if priority: lines.append(f"X-Priority: {priority}")
    lines += ["Content-Type: multipart/mixed; boundary=\"" + fake.bothify("----=_Part_######_##########") + "\"",
              f"X-Attachment-Name: {fname}", f"X-Attachment-Type: {MIME.get(ext, 'application/octet-stream')}",
              f"X-Attachment-Count: 1"]
    return "\n".join(lines) + "\n"


def sig(name, co):
    return random.choice([
        f"Best regards,\n{name}\n{co}\n{fake.phone_number()}",
        f"Kind regards,\n{name}\n{random.choice(['Accounts Receivable', 'Finance', 'Billing', 'Accounts Payable', 'Procurement', 'Operations', 'HR', 'Payroll'])} | {co}",
        f"Thanks,\n{name}",
        f"Regards,\n\n{name}\n{co}\n{fake.city()}\nwww.{fake.domain_name()}",
        f"--\n{name}\n{co}\nThis email and any attachments are confidential and intended solely for the addressee.",
    ])


def greet(name):
    return random.choice([f"Hi {name.split()[0]},", f"Dear {name},", f"Hello {name.split()[0]},", f"Dear Sir/Madam,", f"Hi,", f"Good morning {name.split()[0]},", "Hello,"])


# ----------------------------------------------------------------------------
# INVOICE emails
# ----------------------------------------------------------------------------
def invoice_email(fname):
    stem = os.path.splitext(fname)[0]
    inv_no = re.sub(r"\D", "", stem)[-8:] or str(random.randint(100000, 999999))
    inv_no = random.choice([inv_no, f"INV-{inv_no}", stem, f"#{inv_no}"])
    vendor = fake.company(); client = fake.company()
    fr = person(dom(vendor)); to = person(dom(client)); dt = fake.date_time_this_year()
    amount = f"{random.choice(['$', '€', '£', '₹'])}{random.uniform(80, 25000):,.2f}"
    due = (dt + timedelta(days=random.choice([14, 30, 45, 60]))).strftime("%d %b %Y")
    kind = random.choices(["new", "reminder", "overdue", "resend", "approval", "auto", "query"], [40, 15, 10, 10, 10, 10, 5])[0]
    if kind in ("approval", "query"):  # sender is on the client side in these cases
        fr, to = person(dom(client)), person(dom(client) if kind == "approval" else dom(vendor))
    if kind == "new":
        subj = random.choice([f"Invoice {inv_no} from {vendor}", f"Invoice {inv_no} – {client}", f"Your invoice {inv_no} is attached",
                              f"{vendor}: Invoice {inv_no} for {fake.month_name()} services", f"Invoice {inv_no} | Due {due}", f"Tax Invoice {inv_no}"])
        body = f"""{greet(to[0])}

Please find attached invoice {inv_no} for {random.choice(['the services rendered', 'goods delivered', 'the consulting engagement', 'the recent order', 'work completed'])} {random.choice(['last month', 'in ' + fake.month_name(), 'under PO ' + fake.bothify('PO-#####'), 'as per our agreement'])}.

Invoice number: {inv_no}
Invoice date: {dt.strftime('%d %b %Y')}
Amount due: {amount}
Due date: {due}
Payment terms: {random.choice(['Net 30', 'Net 45', 'Due on receipt', '30 days from invoice date'])}

{random.choice(['Payment can be made by bank transfer to the account details shown on the invoice.', 'Please remit payment to the bank account listed at the bottom of the invoice.', 'Kindly process this invoice for payment at your earliest convenience.', 'Our bank details have not changed; please pay to the account on the invoice.'])}
{random.choice(['Let me know if you need anything else to process this.', 'Do not hesitate to contact me if you have any questions regarding this invoice.', 'Please quote the invoice number with your payment.', ''])}

{sig(fr[0], vendor)}"""
    elif kind == "reminder":
        subj = random.choice([f"Payment reminder: Invoice {inv_no}", f"Friendly reminder – invoice {inv_no} due {due}", f"RE: Invoice {inv_no}", f"Reminder: outstanding invoice {inv_no}"])
        body = f"""{greet(to[0])}

This is a friendly reminder that invoice {inv_no} for {amount} {random.choice(['is due on ' + due, 'falls due shortly', 'remains unpaid'])}. A copy of the invoice is attached for your reference.

If payment has already been made, please disregard this message. Otherwise, we would appreciate settlement by the due date.

{sig(fr[0], vendor)}"""
    elif kind == "overdue":
        subj = random.choice([f"OVERDUE: Invoice {inv_no}", f"Second notice – invoice {inv_no} past due", f"Urgent: unpaid invoice {inv_no}", f"Invoice {inv_no} – {random.randint(5, 60)} days overdue"])
        body = f"""{greet(to[0])}

Our records show that invoice {inv_no} for {amount}, dated {dt.strftime('%d %b %Y')}, is now {random.randint(5, 60)} days past its due date. The invoice is attached again for your convenience.

Please arrange payment within {random.choice(['5 business days', '7 days', '48 hours'])} or let us know if there is a dispute with this invoice. {random.choice(['Late payment charges may apply as per our terms.', 'Continued non-payment may result in suspension of services.', ''])}

{sig(fr[0], vendor)}"""
    elif kind == "resend":
        subj = random.choice([f"FW: Invoice {inv_no}", f"Re-sending invoice {inv_no}", f"Copy of invoice {inv_no} as requested", f"Invoice {inv_no} – corrected copy"])
        body = f"""{greet(to[0])}

As requested, I am re-sending invoice {inv_no}. {random.choice(['Apologies, the previous attachment did not come through.', 'The earlier copy had the wrong PO number; this version is corrected.', 'Please use this copy for your records.', 'This replaces the version sent on ' + fake.date_this_year().strftime('%d %b') + '.'])}

Total: {amount}
Due: {due}

{sig(fr[0], vendor)}"""
    elif kind == "approval":
        cc = person(to[1].split("@")[1])
        subj = random.choice([f"Invoice {inv_no} for approval", f"Please approve: {vendor} invoice {inv_no}", f"[Action required] Invoice {inv_no} – {vendor}", f"AP: new vendor invoice {inv_no}"])
        body = f"""{greet(to[0])}

We have received the attached invoice {inv_no} from {vendor} for {amount}. {random.choice(['It has been matched to PO ' + fake.bothify('PO-#####') + '.', 'There is no PO reference on it; can you confirm this was ordered by your team?', 'Please confirm the goods/services were received so we can release payment.'])}

Could you review and approve by {due} so it can be included in the next payment run?

{sig(fr[0], client)}"""
        return subj, body, dict(fr=fr, to=to, dt=dt, cc=cc)
    elif kind == "auto":
        fr = (f"{vendor} Billing", f"no-reply@{fake.domain_name()}")
        subj = random.choice([f"[Automated] Invoice {inv_no} is now available", f"Your {vendor} invoice {inv_no}", f"New invoice {inv_no} generated", f"Billing notification – invoice {inv_no}"])
        body = f"""Dear Customer,

A new invoice has been generated for your account.

Invoice number: {inv_no}
Account: {fake.bothify('ACC-######')}
Amount: {amount}
Due date: {due}

The invoice is attached to this email in {random.choice(['PDF', 'image'])} format. You can also view and pay it online at https://billing.{fake.domain_name()}/invoices/{inv_no.strip('#')}.

This is an automated message; please do not reply to this email.

{vendor} Billing Team"""
        return subj, body, dict(fr=fr, to=to, dt=dt, reply_to=f"billing@{fr[1].split('@')[1]}")
    else:  # query
        subj = random.choice([f"Query on invoice {inv_no}", f"Invoice {inv_no} – amount does not match PO", f"Question about attached invoice {inv_no}"])
        body = f"""{greet(to[0])}

I'm attaching invoice {inv_no} which we received from you. {random.choice(['The total of ' + amount + ' does not match our purchase order.', 'The VAT line appears to be calculated at the wrong rate.', 'The billing address is incorrect; it should be our head office.', 'Line 3 was not delivered as far as I can tell.'])}

Could you check and issue a corrected invoice or credit note?

{sig(fr[0], client)}"""
    return subj, body, dict(fr=fr, to=to, dt=dt)


# ----------------------------------------------------------------------------
# RANDOM (non-invoice) emails, by attachment type
# ----------------------------------------------------------------------------
def random_email(fname):
    stem = os.path.splitext(fname)[0]
    co = fake.company(); fr = person(dom(co)); to = person(); dt = fake.date_time_this_year()
    g = greet(to[0]); s = sig(fr[0], co)
    kind = stem.split("_")[0]
    sub = stem.split("_")[1] if kind == "lookalike" else None
    amount = f"{random.choice(['$', '€', '£', '₹'])}{random.uniform(5, 2000):,.2f}"

    if kind == "receipt":
        subj = random.choice(["Receipt for expense claim", "Expenses – " + fake.month_name(), "Lunch receipt", f"Receipt from {fake.company()}", "Fwd: your receipt", "Reimbursement – attached receipt",
                              "Receipt for team dinner", "Taxi receipt for last week's client visit", "Here's that receipt you asked for"])
        body = random.choice([
            f"{g}\n\nAttached is the receipt for {random.choice(['the client lunch on ' + fake.day_of_week(), 'the office supplies I picked up', 'the taxi from the airport', 'the team dinner', 'the printer toner'])}. Total was {amount}. Could you add it to this month's expense claim?\n\n{s}",
            f"{g}\n\nPlease see the attached receipt for my reimbursement. {random.choice(['Paid by personal card.', 'I used my own cash so let me know if a bank transfer works.', 'Cost centre is ' + fake.bothify('CC-###') + '.'])}\n\n{s}",
            f"{g}\n\nForwarding the receipt from {fake.company()} as proof of purchase for the warranty claim. Let me know if you need the original.\n\n{s}",
            f"Hi,\n\nScanned receipt attached. {random.choice(['Sorry about the quality, it was crumpled in my bag.', 'The total is a bit hard to read, it says ' + amount + '.', ''])}\n\n{fr[0].split()[0]}",
        ])
    elif sub == "purchase":
        subj = random.choice([f"Purchase Order {fake.bothify('PO-#####')}", f"New PO from {co}", f"PO {fake.bothify('#####')} – please confirm", "Purchase order for your review"])
        body = f"{g}\n\nPlease find attached our purchase order {fake.bothify('PO-#####')} for {random.choice(['the items discussed', 'the Q' + str(random.randint(1, 4)) + ' order', 'the replacement parts'])}. Kindly confirm receipt and advise the expected delivery date.\n\n{random.choice(['Please quote the PO number on your delivery documents and invoice.', 'Delivery to our warehouse as per the ship-to address on the order.', ''])}\n\n{s}"
    elif sub == "quotation":
        subj = random.choice([f"Quotation {fake.bothify('Q-####')} from {co}", "Quote as requested", f"RE: pricing request – quote attached", f"Estimate for {fake.catch_phrase().lower()}"])
        body = f"{g}\n\nThank you for your enquiry. Attached is our quotation for {random.choice(['the requested items', 'the project scope we discussed', 'the annual maintenance contract'])}. {random.choice(['Prices are valid for 30 days.', 'The quote is valid until the end of the month.', 'Lead time is approximately ' + str(random.randint(1, 8)) + ' weeks from order.'])}\n\nPlease let me know if you would like to proceed or if any changes are needed.\n\n{s}"
    elif sub == "delivery":
        subj = random.choice([f"Delivery note – shipment {fake.bothify('DN-######')}", "Your order has shipped", f"Packing list for order {fake.bothify('SO-#####')}", "Despatch confirmation"])
        body = f"{g}\n\nYour order has been despatched today via {random.choice(['DHL', 'FedEx', 'UPS', 'our own fleet'])}. The delivery note / packing list is attached. Tracking: {fake.bothify('??########')}.\n\nPlease check the goods against the note on arrival and report any discrepancies within 48 hours.\n\n{s}"
    elif sub == "payslip":
        fr = ("Payroll", f"payroll@{fake.domain_name()}")
        subj = random.choice([f"Your payslip for {fake.month_name()}", "Payslip attached – confidential", f"Pay statement {dt.strftime('%b %Y')}", "Monthly salary slip"])
        body = f"Dear {to[0].split()[0]},\n\nPlease find attached your payslip for {fake.month_name()} {dt.year}. {random.choice(['Your salary will be credited on the last working day of the month.', 'The document is password protected with your employee ID.', 'Please review and raise any queries with HR within 7 days.'])}\n\nThis email is confidential and intended only for the named employee.\n\nPayroll Team\n{co}"
    elif sub == "bank":
        fr = (f"{random.choice(['First National', 'Meridian', 'Northgate', 'Union Trust'])} Bank", f"statements@{fake.domain_name()}")
        subj = random.choice(["Your monthly statement is ready", f"Account statement – {dt.strftime('%B %Y')}", "e-Statement attached", "Statement of account"])
        body = f"Dear Customer,\n\nYour account statement for the period ending {dt.strftime('%d %b %Y')} is attached. Please review all transactions and contact us within 60 days if you notice anything unfamiliar.\n\nWe will never ask for your full password or PIN by email.\n\n{fr[0]}\nThis is an automated message."
        return subj, body, dict(fr=fr, to=to, dt=dt)
    elif sub == "expense":
        subj = random.choice([f"Expense report {fake.bothify('EXP-####')} for approval", f"{fake.month_name()} expenses", "Travel expense claim – " + fake.city(), "Expense claim submitted"])
        body = f"{g}\n\nAttached is my expense report for {random.choice(['the ' + fake.city() + ' trip', 'last month', 'the conference', 'client visits in ' + fake.month_name()])}. Total claimed is {amount}. Receipts are {random.choice(['attached to the report', 'in the shared drive', 'with the hard copy on your desk'])}.\n\nCould you approve so it can go into the next payroll run?\n\n{s}"
    elif sub == "remittance":
        subj = random.choice([f"Remittance advice – payment {fake.bothify('PAY########')}", "Payment advice", f"Payment made – {amount}", "Remittance for your invoices"])
        body = f"{g}\n\nPlease find attached our remittance advice for the payment of {amount} made today by {random.choice(['bank transfer', 'ACH', 'BACS', 'wire'])}. The advice lists the documents settled by this payment.\n\nNo action is required. Please allocate accordingly.\n\n{s}"
    elif sub == "timesheet":
        subj = random.choice([f"Timesheet w/e {dt.strftime('%d %b')}", "Weekly timesheet for approval", f"Hours for {fake.month_name()} – {fr[0]}", "Timesheet attached"])
        body = f"{g}\n\nAttached is my timesheet for the week ending {dt.strftime('%d %b')}. {random.choice(['Total ' + str(random.choice([37.5, 40, 42.5, 45])) + ' hours including ' + str(random.randint(0, 6)) + ' overtime.', 'All hours booked to ' + fake.bothify('PRJ-###') + '.', 'Please let me know if anything needs adjusting.'])}\n\n{s}"
    elif sub == "credit":
        subj = random.choice(["Trade account application", "Credit application form – completed", f"Account opening – {co}", "New customer account form"])
        body = f"{g}\n\nPlease find attached our completed credit application form along with the required details. {random.choice(['Our trade references are listed on page 2.', 'We would like to request 30-day terms.', 'Let me know if you need our latest accounts as well.'])}\n\nLooking forward to working with you.\n\n{s}"
    else:  # doc_ misc pdfs
        subj = random.choice(["Document for review", "FYI – attached file", "Updated draft", f"RE: {fake.catch_phrase()}", "Please see attached", "Minutes from today's meeting", "Form to fill in", "Slides from the session", "Reference document"])
        body = random.choice([
            f"{g}\n\n{fake.paragraph(nb_sentences=3)} The document is attached.\n\n{s}",
            f"{g}\n\nSharing the attached as discussed. {random.choice(['Let me know your thoughts by Friday.', 'No action needed, just for reference.', 'Comments welcome.'])}\n\n{s}",
            f"Hi all,\n\nPlease find the attached {random.choice(['report', 'presentation', 'form', 'brochure', 'guide', 'summary'])}. {fake.sentence()}\n\n{fr[0].split()[0]}",
        ])
    return subj, body, dict(fr=fr, to=to, dt=dt)


# ----------------------------------------------------------------------------
def run(src_dir, label, builder):
    n = 0
    for fname in sorted(os.listdir(src_dir)):
        stem = os.path.splitext(fname)[0]
        subj, body, m = builder(fname)
        hdr = header(m["fr"], m["to"], subj, m["dt"], fname, cc=m.get("cc"), reply_to=m.get("reply_to"),
                     priority=random.choice([None, None, None, "1 (Highest)", "3 (Normal)"]))
        with open(os.path.join(EM, "Header", label, stem + ".txt"), "w", encoding="utf-8") as f: f.write(hdr)
        with open(os.path.join(EM, "Body", label, stem + ".txt"), "w", encoding="utf-8") as f: f.write(body.strip() + "\n")
        n += 1
    print(label, n)


run(os.path.join(ATT, "invoices"), "invoice", invoice_email)
run(os.path.join(ATT, "random"), "random", random_email)
