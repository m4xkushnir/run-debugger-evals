"""Build data/cases.jsonl: 40 synthetic failed Duvo Runs with ground truth.

Every case is hand-written (setting, AOP, transcript, ground truth). No model wrote
or labelled any of it. Run: python data/build_dataset.py
"""

import json
from pathlib import Path

PROVENANCE = (
    "synthetic; hand-authored for this eval from the failure modes described in "
    "duvoai/skills run-debugger SKILL.md @ 04dc340; not derived from any real Duvo Run"
)

# Transcript DSL: ("agent", text) | ("call", tool, args) | ("result", tool, text)
# | ("system", text)
A, C, R, S = "agent", "call", "result", "system"

CASES = []


def case(id, slice, setting, run, aop, transcript, gt, context=None):
    CASES.append(
        {
            "id": id,
            "slice": slice,
            "setting": setting,
            "synthetic": True,
            "provenance": PROVENANCE,
            "run": run,
            "aop": aop.strip(),
            "transcript": [list(t) for t in transcript],
            "context": context or [],
            "ground_truth": gt,
        }
    )


def gt(mode, fix, decision, acceptable=None, fix_ok=None):
    return {
        "failure_mode": mode,
        "acceptable": acceptable or [mode],
        "fix_target": fix,
        "fix_acceptable": fix_ok or [fix],
        "decision_point": decision,
    }


def run(run_id, status, build_id, case_id=None, case_state=None, error=None):
    r = {"run_id": run_id, "status": status, "build_id": build_id}
    if case_id:
        r["case_id"] = case_id
        r["case_state"] = case_state
    if error:
        r["error_summary"] = error
    return r


# ---------------------------------------------------------------- connection_failure

case(
    "C01", "clean", "AP invoice intake from a shared Gmail inbox",
    run("run_c01", "failed", "bld_7a1", error="Tool call failed: gmail.search_messages"),
    """
# GOAL
Capture one new supplier invoice email from the AP inbox and register it in NetSuite.

# STEPS
1. Use **Gmail** to find the newest unread email in the AP inbox with a PDF attachment.
   - If none: stop.
2. Read the PDF and extract supplier name, invoice number, invoice date, net amount, VAT and currency.
3. Use **NetSuite** to create a vendor bill with those fields.
4. Use **Gmail** to label the email "registered".
""",
    [
        (C, "gmail.search_messages", '{"query": "is:unread has:attachment filename:pdf"}'),
        (R, "gmail.search_messages", 'ERROR 401: {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}'),
        (A, "I could not read the AP inbox: Gmail rejected the request with an expired-token error. I can't continue without inbox access."),
    ],
    gt("connection_failure", "connection_change", "Token has been expired or revoked.",
       fix_ok=["connection_change", "aop_change"]),
    ["Gmail Connection 'AP inbox' last authorised 2026-07-30 (91 days before this Run)."],
)

case(
    "C02", "clean", "Supplier purchase-order reminders",
    run("run_c02", "failed", "bld_2c9", error="Tool call failed: gmail.send_message"),
    """
# GOAL
Send one overdue-PO reminder to the supplier and log it.

# STEPS
1. Read the PO number, supplier email and original due date from the run input.
2. Use **Gmail** to send the supplier a reminder: subject "Reminder: PO [number] overdue", body with the due date.
3. Use **Google Sheets** to append a row to "PO reminders": PO number, supplier, date sent.
""",
    [
        (A, "PO 4500918821 for Kovotech s.r.o. was due on 2026-10-20. Sending the reminder."),
        (C, "gmail.send_message", '{"to": "orders@kovotech.cz", "subject": "Reminder: PO 4500918821 overdue"}'),
        (R, "gmail.send_message", "ERROR 403: Request had insufficient authentication scopes. Required: https://www.googleapis.com/auth/gmail.send"),
        (A, "Sending failed because of missing permissions. The reminder was not sent and no row was logged."),
    ],
    gt("connection_failure", "connection_change", "Request had insufficient authentication scopes"),
    ["Gmail Connection 'Purchasing' granted scopes: gmail.readonly, gmail.labels."],
)

case(
    "C03", "clean", "Store replenishment orders on a supplier portal (multi-market)",
    run("run_c03", "failed", "bld_51e", error="Portal returned access denied"),
    """
# GOAL
Place one replenishment order for a store on the Alpenfrisch supplier portal.

# STEPS
1. Read store ID, market and SKU quantities from the run input.
2. Use **Enterprise Browser** to sign in to the Alpenfrisch portal with the Login **Alpenfrisch portal**.
3. Open "New order", choose the store's market, enter each SKU and quantity, and submit.
4. Record the portal order number in **Google Sheets** "Replenishment log".
""",
    [
        (A, "Store AT-114 (market AT), 6 SKUs. Signing in to the portal."),
        (C, "browser.login", '{"login": "Alpenfrisch portal"}'),
        (R, "browser.login", "Signed in as svc-replen-cz@retailco.eu"),
        (C, "browser.select", '{"field": "Market", "value": "AT"}'),
        (R, "browser.select", 'Page message: "Access denied: this account is not authorised for market AT."'),
        (A, "The portal refused market AT for this account. The order was not placed."),
    ],
    gt("connection_failure", "connection_change", "this account is not authorised for market AT"),
    ["Login 'Alpenfrisch portal' is the CZ service account svc-replen-cz."],
)

# ---------------------------------------------------------------- aop_ambiguity

case(
    "A01", "clean", "E-commerce refund requests",
    run("run_a01", "completed", "bld_a01", error=None),
    """
# GOAL
Resolve one damaged-item refund request.

# STEPS
1. Use **Shopify** to look up the order and item.
2. Look at the customer's photos.
   - If the damage looks significant, use your judgment on whether to refund in full or offer a partial refund.
3. Use **Stripe** to issue the refund.
4. Use **Gmail** to confirm the refund to the customer.
""",
    [
        (C, "shopify.get_order", '{"order": "#88213"}'),
        (R, "shopify.get_order", '{"item": "Oak dining table", "price_eur": 480.00}'),
        (A, "The photos show a 3 cm surface scratch on one leg. It looks significant enough to the customer, so I'll refund in full."),
        (C, "stripe.refund", '{"order": "#88213", "amount_eur": 480.00}'),
        (R, "stripe.refund", '{"status": "succeeded"}'),
        (C, "gmail.send_message", '{"to": "customer", "subject": "Your refund of EUR 480.00"}'),
        (R, "gmail.send_message", '{"status": "sent"}'),
    ],
    gt("aop_ambiguity", "aop_change", "It looks significant enough to the customer, so I'll refund in full."),
    ["User report: 'The Agent refunded a full EUR 480 table for a small scratch. Policy is 15% for cosmetic damage.'"],
)

case(
    "A02", "clean", "Freight invoice audit against carrier rate card",
    run("run_a02", "completed", "bld_f02"),
    """
# GOAL
Audit one carrier freight invoice and flag overcharges.

# STEPS
1. Read the invoice lines from the run input.
2. Open the rate card in Files ("DHL Freight rate card 2026").
3. Flag any line where the charge seems too high compared with the rate card.
4. Use **Google Sheets** to append the audit result to "Freight audit".
""",
    [
        (A, "Line 1 Prague-Brno pallet: charged 2,140 CZK vs rate 2,100 CZK (+1.9%). Seems too high, flagging."),
        (A, "Line 2 Prague-Vienna FTL: charged 31,600 CZK vs rate 29,000 CZK (+9.0%). Fuel surcharges vary, this seems reasonably close, not flagging."),
        (C, "sheets.append_row", '{"sheet": "Freight audit", "flags": ["line 1"]}'),
        (R, "sheets.append_row", '{"status": "ok"}'),
    ],
    gt("aop_ambiguity", "aop_change", "this seems reasonably close, not flagging"),
    ["User report: 'It flagged a 40 CZK difference and missed a 2,600 CZK overcharge.'"],
)

case(
    "A03", "clean", "DESADV (despatch advice) exception handling",
    run("run_a03", "completed", "bld_d03"),
    """
# GOAL
Resolve one DESADV quantity exception for an inbound delivery.

# STEPS
1. Read the DESADV and the matching purchase order from the run input.
2. If quantities don't match, handle it appropriately.
3. Post a summary to **Slack** #inbound.
""",
    [
        (A, "DESADV shows 480 units of SKU 77120, the PO says 500. The quantities don't match."),
        (A, "I'll handle it by asking the supplier to explain the shortfall."),
        (C, "gmail.send_message", '{"to": "edi@supplier.example", "subject": "Shortfall on SKU 77120"}'),
        (R, "gmail.send_message", '{"status": "sent"}'),
        (C, "slack.post", '{"channel": "#inbound", "text": "Asked supplier about 20-unit shortfall on SKU 77120"}'),
        (R, "slack.post", '{"ok": true}'),
    ],
    gt("aop_ambiguity", "aop_change", "If quantities don't match, handle it appropriately."),
    ["User report: 'Shortfalls under 5% should just be adjusted on the goods receipt in the WMS, not emailed to the supplier.'"],
)

# ---------------------------------------------------------------- missing_terminal_closure

case(
    "T01", "clean", "AP invoice intake queue consumer",
    run("run_t01", "completed", "bld_t01", case_id="case_t01",
        case_state="Completed — reason: auto-completed on clean run end; evaluation: 1 issue (critical)"),
    """
# GOAL
Process one invoice case: match it to a PO and post it, or route it for review.

# STEPS
1. Call `claim_case` to get the invoice data.
2. Use **NetSuite** to find the PO referenced on the invoice.
   - If the PO is not found: post the invoice number to **Slack** #ap-exceptions.
3. Match invoice lines to PO lines; if they match within 1%, post the vendor bill in **NetSuite**.
4. Call `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"invoice_number": "INV-20931", "po_reference": "PO-778812"}'),
        (C, "netsuite.find_po", '{"po": "PO-778812"}'),
        (R, "netsuite.find_po", '{"results": []}'),
        (C, "slack.post", '{"channel": "#ap-exceptions", "text": "INV-20931: PO-778812 not found"}'),
        (R, "slack.post", '{"ok": true}'),
        (A, "The PO was not found, so I posted the invoice to #ap-exceptions as instructed."),
    ],
    gt("missing_terminal_closure", "aop_change", "post the invoice number to **Slack** #ap-exceptions."),
    ["Case evaluation comment: 'Invoice was never posted, but the case shows Completed.'"],
)

case(
    "T02", "clean", "Supplier reminder chain (queue consumer)",
    run("run_t02", "completed", "bld_t02", case_id="case_t02",
        case_state="Completed — reason: auto-completed on clean run end"),
    """
# GOAL
Send the second reminder for one outstanding PO.

# STEPS
1. Call `claim_case` to get the PO number, supplier and Slack thread.
2. Use **Slack** to read the PO thread.
   - If the supplier has replied asking for more time: note the new date in the thread.
3. Use **Gmail** to send the second reminder.
4. Call `update_case` with `second_reminder_sent_at`, then `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"po": "PO-55120", "supplier": "Textima a.s."}'),
        (C, "slack.read_thread", '{"thread": "po-55120"}'),
        (R, "slack.read_thread", '"Textima: We need until 12 Nov to ship, sorry for the delay."'),
        (C, "slack.post", '{"thread": "po-55120", "text": "Supplier asked for more time: new date 12 Nov"}'),
        (R, "slack.post", '{"ok": true}'),
        (A, "Noted the new date of 12 Nov in the thread."),
    ],
    gt("missing_terminal_closure", "aop_change", "note the new date in the thread."),
    ["User report: 'Nobody followed up on 12 Nov. The PO fell out of the reminder chain.'"],
)

case(
    "T03", "clean", "Returns processing queue consumer",
    run("run_t03", "completed", "bld_t03", case_id="case_t03",
        case_state="Completed — reason: auto-completed on clean run end; evaluation: stuck in evaluating"),
    """
# GOAL
Process one customer return: create the carrier label and email it.

# STEPS
1. Call `claim_case` to get the order and customer details.
2. Use **Packeta** to create a return label.
   - If the label can't be generated: post the order number to **Slack** #returns-ops.
3. Use **Gmail** to email the label to the customer.
4. Call `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"order": "R-30112", "country": "SK"}'),
        (C, "packeta.create_return_label", '{"order": "R-30112"}'),
        (R, "packeta.create_return_label", 'ERROR 422: "Return service not available for destination SK."'),
        (C, "slack.post", '{"channel": "#returns-ops", "text": "R-30112: no return label"}'),
        (R, "slack.post", '{"ok": true}'),
        (A, "Label could not be created; I alerted #returns-ops."),
    ],
    gt("missing_terminal_closure", "aop_change", "post the order number to **Slack** #returns-ops."),
)

# ---------------------------------------------------------------- missing_hitl

case(
    "H01", "clean", "Supplier master-data updates from email",
    run("run_h01", "completed", "bld_h01"),
    """
# GOAL
Apply one supplier master-data change request received by email.

# STEPS
1. Use **Gmail** to read the change request.
2. Identify the supplier in **SAP** and the field to change.
3. Update the field in **SAP**.
4. Reply to the sender confirming the change.
""",
    [
        (C, "gmail.get_message", '{"id": "msg_8812"}'),
        (R, "gmail.get_message", '"From: accounts@sunfield-foods.co\\nPlease update our bank account to IBAN DE89 3704 0044 0532 0130 00 effective immediately."'),
        (C, "sap.update_vendor", '{"vendor": "100482 Sunfield Foods", "field": "bank_iban", "value": "DE89370400440532013000"}'),
        (R, "sap.update_vendor", '{"status": "updated"}'),
        (C, "gmail.reply", '{"text": "Your bank details have been updated."}'),
        (R, "gmail.reply", '{"status": "sent"}'),
    ],
    gt("missing_hitl", "aop_change", "sap.update_vendor"),
    ["Security report: the email came from a look-alike domain (sunfield-foods.co vs sunfieldfoods.com). Next payment run: EUR 212,000 to Sunfield."],
)

case(
    "H02", "clean", "Markdown pricing for end-of-season stock",
    run("run_h02", "completed", "bld_h02"),
    """
# GOAL
Apply this week's recommended markdowns for one product category.

# STEPS
1. Use **Snowflake** to read the markdown recommendations for the category in the run input.
2. Apply the recommended markdown in the **Pricing** system for all stores.
3. Post a summary to **Slack** #merchandising.
""",
    [
        (C, "snowflake.query", '{"category": "Outdoor furniture"}'),
        (R, "snowflake.query", '{"rows": 38, "markdown_pct": 30}'),
        (C, "pricing.apply_markdown", '{"category": "Outdoor furniture", "pct": 30, "stores": "all (140)"}'),
        (R, "pricing.apply_markdown", '{"updated_prices": 5320}'),
        (C, "slack.post", '{"channel": "#merchandising", "text": "Applied 30% markdown to Outdoor furniture in 140 stores"}'),
        (R, "slack.post", '{"ok": true}'),
    ],
    gt("missing_hitl", "aop_change", "Apply the recommended markdown in the **Pricing** system for all stores."),
    ["User report: 'The recommendation table had a bad row; 30% went live in every store before anyone looked.'"],
)

case(
    "H03", "clean", "Late-delivery handling for purchase orders",
    run("run_h03", "completed", "bld_h03"),
    """
# GOAL
Handle one late inbound purchase order.

# STEPS
1. Read the PO and the supplier's new delivery date from the run input.
2. If the delivery is more than 1 day late: cancel the PO in **SAP** and reorder the same lines from the backup supplier listed in Files ("Backup suppliers").
3. Email both suppliers via **Gmail**.
""",
    [
        (A, "PO 4500921177 (EUR 62,400) is now 2 days late. Cancelling and reordering from the backup supplier."),
        (C, "sap.cancel_po", '{"po": "4500921177"}'),
        (R, "sap.cancel_po", '{"status": "cancelled"}'),
        (C, "sap.create_po", '{"supplier": "Backup: Nordpack AB", "value_eur": 66100}'),
        (R, "sap.create_po", '{"po": "4500921240"}'),
    ],
    gt("missing_hitl", "aop_change", "Cancelling and reordering from the backup supplier.",
       acceptable=["missing_hitl", "aop_ambiguity"]),
    ["User report: 'We lost our main supplier's slot and paid EUR 3,700 more over a 2-day slip.'"],
)

# ---------------------------------------------------------------- missing_data

case(
    "D01", "clean", "Freight invoice audit",
    run("run_d01", "completed", "bld_d01"),
    """
# GOAL
Audit one freight invoice against the carrier rate card.

# STEPS
1. Read the invoice lines from the run input.
2. Open the rate card in Files ("Carrier rate card 2026.xlsx").
3. Flag every line more than 3% above the rate card.
4. Append the result to **Google Sheets** "Freight audit".
""",
    [
        (C, "files.search", '{"name": "Carrier rate card 2026.xlsx"}'),
        (R, "files.search", '{"results": []}'),
        (A, "The rate card isn't available. I'll compare against typical market rates for these lanes instead."),
        (A, "All lines are within typical market range. No flags."),
        (C, "sheets.append_row", '{"sheet": "Freight audit", "flags": []}'),
        (R, "sheets.append_row", '{"status": "ok"}'),
    ],
    gt("missing_data", "setup_or_file", '{"results": []}', fix_ok=["setup_or_file", "aop_change"]),
)

case(
    "D02", "clean", "Store replenishment quantity calculation",
    run("run_d02", "completed", "bld_d02"),
    """
# GOAL
Calculate and submit one store's weekly replenishment order.

# STEPS
1. Read 28-day sales and current stock for the store from **Snowflake**.
2. Order quantity = forecast weekly demand + (daily demand × Setup input `safety_stock_days`) − current stock.
3. Submit the order in the **Replenishment portal**.
""",
    [
        (C, "snowflake.query", '{"store": "CZ-031"}'),
        (R, "snowflake.query", '{"daily_demand": {"SKU-1101": 42}, "stock": {"SKU-1101": 260}}'),
        (A, "Setup inputs: safety_stock_days = (not set). Treating it as 0."),
        (A, "SKU-1101: 294 + 0 - 260 = 34 units."),
        (C, "replenishment.submit", '{"store": "CZ-031", "lines": [{"sku": "SKU-1101", "qty": 34}]}'),
        (R, "replenishment.submit", '{"order": "RP-99120"}'),
    ],
    gt("missing_data", "setup_or_file", "safety_stock_days = (not set). Treating it as 0.",
       fix_ok=["setup_or_file", "aop_change"]),
    ["User report: 'Store CZ-031 ran out of SKU-1101 on Thursday.'"],
)

case(
    "D03", "clean", "AP invoice posting (queue consumer)",
    run("run_d03", "completed", "bld_d03", case_id="case_d03", case_state="Completed by Agent"),
    """
# GOAL
Post one approved invoice to the ledger.

# STEPS
1. Call `claim_case` to get the invoice; it carries amount, supplier, and `cost_center`.
2. Post the invoice in **NetSuite** to the case's `cost_center`.
3. Call `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"invoice": "INV-7731", "amount_eur": 4120, "supplier": "Hartmann Logistik"}'),
        (A, "No cost_center on the case. Posting with cost center TBD so the invoice isn't delayed."),
        (C, "netsuite.post_bill", '{"invoice": "INV-7731", "cost_center": "TBD"}'),
        (R, "netsuite.post_bill", '{"status": "posted"}'),
        (C, "complete_case", "{}"),
        (R, "complete_case", '{"status": "completed"}'),
    ],
    gt("missing_data", "aop_change", "Posting with cost center TBD", fix_ok=["aop_change", "setup_or_file"]),
)

# ---------------------------------------------------------------- batch_leak

case(
    "B01", "clean", "AP inbox processing (queue consumer)",
    run("run_b01", "failed", "bld_b01", case_id="case_b01", case_state="Failed",
        error="Run exceeded maximum duration (30m)"),
    """
# GOAL
Register supplier invoices from the AP inbox.

# STEPS
1. Call `claim_case`.
2. Use **Gmail** to process all pending supplier invoices in the AP inbox: extract fields and create a vendor bill in **NetSuite** for each.
3. Call `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"title": "Invoice from Brenntag CZ"}'),
        (C, "gmail.search_messages", '{"query": "is:unread label:ap"}'),
        (R, "gmail.search_messages", '{"count": 47}'),
        (A, "47 pending invoices. Processing them one by one."),
        (A, "Created vendor bills 1-19 of 47."),
        (S, "Run stopped: exceeded maximum duration (30m)."),
    ],
    gt("batch_leak", "aop_change", "process all pending supplier invoices in the AP inbox"),
)

case(
    "B02", "clean", "Return refunds from a Google Sheet",
    run("run_b02", "completed", "bld_b02"),
    """
# GOAL
Refund approved returns.

# STEPS
1. Use **Google Sheets** "Returns": for each open return marked "approved", issue the refund in **Stripe** and set the row to "refunded".
""",
    [
        (C, "sheets.read", '{"sheet": "Returns", "filter": "status=approved"}'),
        (R, "sheets.read", '{"rows": 12}'),
        (A, "Refunding 12 approved returns."),
        (C, "stripe.refund", '{"order": "#90011", "amount_eur": 59.90}'),
        (R, "stripe.refund", '{"status": "succeeded", "note": "a refund for this charge already exists (created 2 min ago)"}'),
        (A, "Continuing with the remaining 11 rows."),
    ],
    gt("batch_leak", "aop_change", "for each open return marked \"approved\""),
    ["Two Runs of this Agent started 2 minutes apart (schedule + manual Start Work). 9 customers were refunded twice."],
)

case(
    "B03", "clean", "Per-store stock checks (queue consumer, one case per store)",
    run("run_b03", "completed", "bld_b03", case_id="case_b03", case_state="Completed by Agent"),
    """
# GOAL
Reorder low-stock items.

# STEPS
1. Call `claim_case`.
2. Use **Snowflake** to check every store's stock level and reorder anything below minimum in the **Replenishment portal**.
3. Call `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"store": "CZ-007"}'),
        (C, "snowflake.query", '{"scope": "all stores"}'),
        (R, "snowflake.query", '{"stores": 60, "below_min_lines": 412}'),
        (A, "Reordering 412 lines across 60 stores."),
        (C, "replenishment.submit", '{"lines": 412}'),
        (R, "replenishment.submit", '{"orders": 60}'),
        (C, "complete_case", "{}"),
        (R, "complete_case", '{"status": "completed"}'),
    ],
    gt("batch_leak", "aop_change", "check every store's stock level"),
    ["60 cases (one per store) ran today; each placed orders for all 60 stores."],
)

# ---------------------------------------------------------------- wrong_decomposition

case(
    "W01", "clean", "Supplier claim handling end to end",
    run("run_w01", "stopped", "bld_w01", error="Run stopped after idle timeout"),
    """
# GOAL
Handle one supplier quality claim.

# STEPS
1. Use **Gmail** to read the claim from the store.
2. Look up the delivery in **SAP**.
3. Download the delivery photos from **SharePoint**.
4. Draft the claim email to the supplier.
5. Send it via **Gmail**.
6. Wait for the supplier's reply.
7. If no reply after 3 days, send a reminder.
8. If no reply after 7 days, escalate to the category manager.
9. When the supplier replies, read the offered credit.
10. Enter the credit note in **SAP**.
11. Update the claims tracker in **Google Sheets**.
12. Notify the store in **Slack**.
13. Close the claim in **ServiceNow**.
14. Archive the email thread.
""",
    [
        (A, "Claim sent to supplier Mlékárna Polná. Now waiting for the supplier's reply (step 6)."),
        (C, "gmail.search_messages", '{"query": "from:polna re:claim"}'),
        (R, "gmail.search_messages", '{"count": 0}'),
        (A, "No reply yet. I'll keep checking."),
        (S, "Run stopped after idle timeout."),
    ],
    gt("wrong_decomposition", "decomposition", "Now waiting for the supplier's reply (step 6)."),
)

case(
    "W02", "clean", "Weekly supplier scorecard and follow-ups",
    run("run_w02", "failed", "bld_w02", error="Enterprise Browser session expired mid-run"),
    """
# GOAL
Produce the weekly supplier scorecard and chase underperformers.

# STEPS
1. Query on-time-in-full rates per supplier in **Snowflake**.
2. Build the scorecard in **Google Sheets**.
3. For each supplier under 90%, sign in to their portal with **Enterprise Browser** and download open-order status.
4. Draft a performance email to each.
5. Send via **Gmail** and schedule a follow-up for next week.
6. Next week, check replies and update the scorecard.
7. Post the summary to **Slack** #purchasing.
8. Escalate repeat offenders to the category manager.
9. Update supplier ratings in **SAP**.
10. Archive the week's files.
11. Create next week's scorecard tab.
""",
    [
        (C, "snowflake.query", '{"metric": "OTIF", "week": 43}'),
        (R, "snowflake.query", '{"suppliers": 84, "under_90": 17}'),
        (C, "sheets.write", '{"tab": "W43"}'),
        (R, "sheets.write", '{"status": "ok"}'),
        (A, "Signing in to portal 9 of 17 (Agrofert)."),
        (C, "browser.login", '{"login": "Agrofert portal"}'),
        (R, "browser.login", "ERROR: browser session expired after 55 minutes"),
    ],
    gt("wrong_decomposition", "decomposition", "Signing in to portal 9 of 17",
       acceptable=["wrong_decomposition", "batch_leak"]),
)

case(
    "W03", "clean", "New supplier onboarding",
    run("run_w03", "completed", "bld_w03"),
    """
# GOAL
Onboard one new supplier.

# STEPS
1. Read the supplier form from **Gmail**.
2. Check the VAT number in **VIES**.
3. Create the vendor in **SAP**.
4. Request bank confirmation from the supplier.
5. Wait 7 days for the signed bank letter.
6. If received, activate payments in **SAP**.
7. If not received, chase the supplier.
8. After activation, send the welcome pack.
9. Add the supplier to the **Coupa** catalogue.
10. Notify purchasing in **Slack**.
11. Schedule the 30-day review.
""",
    [
        (C, "vies.check", '{"vat": "CZ27082440"}'),
        (R, "vies.check", '{"valid": true}'),
        (C, "sap.create_vendor", '{"name": "Biofarma Morava s.r.o."}'),
        (R, "sap.create_vendor", '{"vendor": "100977"}'),
        (A, "Bank confirmation requested. I'll check back in 7 days for the signed letter."),
    ],
    gt("wrong_decomposition", "decomposition", "I'll check back in 7 days for the signed letter."),
    ["User report: 'Vendor 100977 was created but never activated. Nothing happened after day 1.'"],
)

# ---------------------------------------------------------------- platform_infra

case(
    "P01", "clean", "Daily sales summary (scheduled Agent)",
    run("run_p01", "failed", "bld_p01", error="sandbox failed to start"),
    """
# GOAL
Post yesterday's sales summary to Slack.

# STEPS
1. Query yesterday's sales in **Snowflake**.
2. Post the summary to **Slack** #leadership-daily.
""",
    [
        (S, "Run starting."),
        (S, "ERROR: sandbox failed to start: container image pull timed out after 120s (attempt 3/3)."),
        (S, "Run failed."),
    ],
    gt("platform_infra", "escalate_to_duvo", "sandbox failed to start: container image pull timed out"),
    ["The last 3 Runs of this Agent (different days) failed with the identical sandbox error before any Agent turn."],
)

case(
    "P02", "clean", "Order confirmation emails",
    run("run_p02", "failed", "bld_p02", error="internal error in connection layer"),
    """
# GOAL
Send one order confirmation to a B2B customer.

# STEPS
1. Read the order from the run input.
2. Send the confirmation via **Gmail**.
""",
    [
        (C, "gmail.send_message", '{"to": "buyer@hotel-praha.cz"}'),
        (R, "gmail.send_message", "ERROR 500: internal error: failed to decrypt connection credentials (ref: kms-4f19)"),
        (A, "The email could not be sent because of an internal error."),
    ],
    gt("platform_infra", "escalate_to_duvo", "failed to decrypt connection credentials"),
    ["The user re-authenticated the Gmail Connection at 09:12; a test send at 09:13 worked. This Run at 09:20 and the 2 after it failed with the same internal error."],
)

case(
    "P03", "clean", "Case updates on a claims queue",
    run("run_p03", "failed", "bld_p03", case_id="case_p03", case_state="Failed (no reason)",
        error="Tool call failed: update_case"),
    """
# GOAL
Record the supplier's credit offer on one claim case.

# STEPS
1. Call `claim_case`.
2. Read the supplier reply in **Gmail** and extract the credit amount.
3. Call `update_case` with `credit_offered`, then `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"claim": "CL-2210"}'),
        (C, "gmail.get_message", '{"thread": "CL-2210"}'),
        (R, "gmail.get_message", '"We offer a credit of EUR 840."'),
        (C, "update_case", '{"data": {"credit_offered": 840}}'),
        (R, "update_case", "ERROR 500 Internal Server Error (request_id=req_9a7c1e)"),
        (C, "update_case", '{"data": {"credit_offered": 840}}'),
        (R, "update_case", "ERROR 500 Internal Server Error (request_id=req_9a7c52)"),
        (A, "Saving to the case keeps failing with a server error."),
    ],
    gt("platform_infra", "escalate_to_duvo", "ERROR 500 Internal Server Error (request_id=req_9a7c1e)"),
    ["Every Run on this queue since 14:00 fails on `update_case` with the same 500, across different cases."],
)

# ---------------------------------------------------------------- symptom-vs-cause traps

case(
    "S01", "trap", "Out-of-stock alerts to store managers",
    run("run_s01", "failed", "bld_s01", error="slack.post: channel_not_found"),
    """
# GOAL
Alert the store team when a top-50 SKU goes out of stock.

# STEPS
1. Read the store and SKU from the run input.
2. Post an alert to the store's channel: the Setup input `alert_channel`.
""",
    [
        (A, "Setup inputs: alert_channel = \"\"."),
        (C, "slack.post", '{"channel": "#", "text": "SKU 40221 out of stock at CZ-018"}'),
        (R, "slack.post", '{"ok": false, "error": "channel_not_found"}'),
        (A, "Slack rejected the post."),
    ],
    gt("missing_data", "setup_or_file", 'alert_channel = "".', fix_ok=["setup_or_file", "aop_change"]),
    ["The Slack Connection posts fine from other Agents."],
)

case(
    "S02", "trap", "Invoice entry into the ERP (EU number formats)",
    run("run_s02", "failed", "bld_s02", error="ValidationError from SAP"),
    """
# GOAL
Enter one supplier invoice into SAP.

# STEPS
1. Read the invoice PDF.
2. Create the invoice in **SAP**, entering the amount as shown on the invoice.
""",
    [
        (A, "Invoice total as shown: 1.234,50 €."),
        (C, "sap.create_invoice", '{"amount": "1.234,50 €"}'),
        (R, "sap.create_invoice", 'ERROR 400 ValidationError: "amount" must be a number'),
        (A, "SAP rejected the amount."),
    ],
    gt("aop_ambiguity", "aop_change", "entering the amount as shown on the invoice",
       acceptable=["aop_ambiguity", "named_pattern"]),
)

case(
    "S03", "trap", "Bank statement reconciliation",
    run("run_s03", "failed", "bld_s03", error="Run exceeded maximum duration (30m)"),
    """
# GOAL
Reconcile the bank statement.

# STEPS
1. Download today's statement from **Fio banka**.
2. Reconcile all unmatched lines in the statement against open invoices in **NetSuite**.
3. Post a summary to **Slack** #finance.
""",
    [
        (C, "fio.get_statement", '{"date": "2026-10-28"}'),
        (R, "fio.get_statement", '{"lines": 1840, "unmatched": 611}'),
        (A, "611 unmatched lines. Matching each against NetSuite."),
        (A, "Matched 230 of 611."),
        (S, "Run stopped: exceeded maximum duration (30m)."),
    ],
    gt("batch_leak", "aop_change", "Reconcile all unmatched lines in the statement",
       acceptable=["batch_leak", "wrong_decomposition"]),
)

case(
    "S04", "trap", "Catalogue availability check on Shopify",
    run("run_s04", "failed", "bld_s04", error="429 Too Many Requests from Shopify"),
    """
# GOAL
Check availability for a customer's quote request.

# STEPS
1. Read the requested products from the email.
2. For each SKU in the catalogue, check stock in **Shopify** and include it in the quote if it matches the request.
3. Reply with the quote via **Gmail**.
""",
    [
        (A, "Checking the catalogue: 2,300 SKUs."),
        (C, "shopify.get_inventory", '{"sku": "SKU-0001"}'),
        (R, "shopify.get_inventory", '{"available": 14}'),
        (A, "...checked 180 SKUs..."),
        (C, "shopify.get_inventory", '{"sku": "SKU-0181"}'),
        (R, "shopify.get_inventory", "ERROR 429 Too Many Requests: Exceeded 2 calls per second for api client. Retry-After: 30"),
        (A, "Shopify is rate limiting me."),
    ],
    gt("batch_leak", "aop_change", "For each SKU in the catalogue", acceptable=["batch_leak", "aop_ambiguity"]),
    ["The customer's email asked about 3 products."],
)

case(
    "S05", "trap", "Supplier order confirmation emails",
    run("run_s05", "completed", "bld_s05", case_id="case_s05", case_state="Completed by Agent"),
    """
# GOAL
Confirm one purchase order to the supplier.

# STEPS
1. Call `claim_case`; the case carries PO number, supplier, quantity and `unit_price`.
2. Email the supplier via **Gmail**: PO number, quantity, unit price, total.
3. Call `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"po": "PO-88120", "supplier": "Sklárny Kavalier", "qty": 1200}'),
        (A, "No unit_price on the case. The supplier's last email signature lists \"Standard price 4.10 EUR/pc\", using that."),
        (C, "gmail.send_message", '{"to": "sales@kavalier.example", "body": "1200 pcs x 4.10 EUR = 4,920 EUR"}'),
        (R, "gmail.send_message", '{"status": "sent"}'),
        (C, "complete_case", "{}"),
        (R, "complete_case", '{"status": "completed"}'),
    ],
    gt("missing_data", "aop_change", "No unit_price on the case.", fix_ok=["aop_change", "setup_or_file"]),
    ["User report: 'We sent the supplier the wrong price; the contract price is 3.65 EUR.'"],
)

case(
    "S06", "trap", "Matching incoming invoices to suppliers",
    run("run_s06", "completed", "bld_s06", case_id="case_s06", case_state="Failed by Agent — reason: unable to match supplier"),
    """
# GOAL
Match one invoice to a supplier in SAP and route it for approval.

# STEPS
1. Call `claim_case` to get the invoice.
2. Find the supplier in **SAP**. If unsure about the supplier match, call `fail_case`.
3. Route the invoice to the supplier's approver and call `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"supplier_on_invoice": "BAUHAUS Gesellschaft für Bau- und Hausbedarf mbH"}'),
        (C, "sap.search_vendor", '{"name": "BAUHAUS Gesellschaft"}'),
        (R, "sap.search_vendor", '{"results": [{"vendor": "100311", "name": "Bauhaus GmbH", "vat": "DE811145120"}]}'),
        (A, "The names differ, so I'm not sure this is the same supplier."),
        (C, "fail_case", '{"reason": "unable to match supplier"}'),
        (R, "fail_case", '{"status": "failed"}'),
    ],
    gt("aop_ambiguity", "aop_change", "If unsure about the supplier match, call `fail_case`."),
    ["The invoice shows VAT DE811145120, identical to vendor 100311. 31% of this week's cases failed the same way."],
)

# ---------------------------------------------------------------- Connection vs Platform discriminators

case(
    "X01", "discriminator", "Okta-protected supplier portal",
    run("run_x01", "failed", "bld_x01", error="Okta sign-in required"),
    """
# GOAL
Download one supplier's open-order report from their portal.

# STEPS
1. Use **Enterprise Browser** with the Login **Coop portal (Okta)** to open the reports page.
2. Download "Open orders" as CSV and attach it to the run output.
""",
    [
        (C, "browser.open", '{"url": "portal reports page"}'),
        (R, "browser.open", 'Redirected to Okta: "Your session has expired. Sign in again."'),
        (A, "I'm being asked to sign in to Okta and can't proceed."),
    ],
    gt("connection_failure", "connection_change", "Your session has expired. Sign in again."),
    ["Login 'Coop portal (Okta)' was last re-authenticated 94 days ago; the portal enforces 90-day sessions."],
)

case(
    "X02", "discriminator", "SharePoint document filing",
    run("run_x02", "failed", "bld_x02", error="SharePoint 401 Unauthorized"),
    """
# GOAL
File one signed delivery note in SharePoint.

# STEPS
1. Read the delivery note PDF from the run input.
2. Upload it to **SharePoint** "Logistics/Delivery notes/[year]/[month]".
""",
    [
        (C, "sharepoint.upload", '{"path": "Logistics/Delivery notes/2026/10"}'),
        (R, "sharepoint.upload", "ERROR 401 Unauthorized"),
        (A, "SharePoint rejected the upload as unauthorized."),
    ],
    gt("platform_infra", "escalate_to_duvo", "ERROR 401 Unauthorized"),
    [
        "SharePoint Connection re-authenticated by the user at 10:02; Duvo's 'Test connection' succeeded at 10:03.",
        "This Run at 10:15 and the previous 3 Runs since the re-authentication all failed with the same 401.",
        "The same Microsoft account uploads to this folder fine from the browser.",
    ],
)

case(
    "X03", "discriminator", "Purchasing inbox: sending supplier emails",
    run("run_x03", "failed", "bld_x03", error="gmail.send_message 403"),
    """
# GOAL
Send one RFQ (request for quotation) to a supplier.

# STEPS
1. Read the RFQ details from the run input.
2. Send the RFQ via **Gmail**.
""",
    [
        (C, "gmail.send_message", '{"to": "quotes@obaly-plus.cz"}'),
        (R, "gmail.send_message", "ERROR 403: Request had insufficient authentication scopes."),
        (A, "Sending failed."),
    ],
    gt("connection_failure", "connection_change", "Request had insufficient authentication scopes."),
    [
        "The user re-authenticated the Gmail Connection yesterday after the first failure; it failed the same way afterwards.",
        "Connection granted scopes after re-authentication: gmail.readonly.",
    ],
)

# ---------------------------------------------------------------- not a failure

case(
    "N01", "not_a_failure", "Credit note approvals",
    run("run_n01", "waiting", "bld_n01"),
    """
# GOAL
Issue one customer credit note.

# STEPS
1. Read the credit request.
2. If the amount exceeds EUR 1,000: use **Human in the loop** to get approval before issuing.
3. Issue the credit note in **NetSuite** and email the customer.
""",
    [
        (A, "Credit request for EUR 1,850 from Hotel Praha. Above EUR 1,000, asking for approval."),
        (C, "human_in_the_loop.request", '{"question": "Approve credit note EUR 1,850 for Hotel Praha? (yes/no)"}'),
        (R, "human_in_the_loop.request", '{"status": "pending"}'),
    ],
    gt("not_a_failure", "none", '{"status": "pending"}'),
    ["User: 'This Run has been stuck since yesterday, why did it fail?'"],
)

case(
    "N02", "not_a_failure", "Goods-receipt follow-up",
    run("run_n02", "completed", "bld_n02", case_id="case_n02", case_state="Completed by Agent"),
    """
# GOAL
Chase one supplier whose delivery is not yet received.

# STEPS
1. Call `claim_case` to get the PO.
2. Check the PO in **SAP**. If it is already marked received: call `complete_case` and stop.
3. Otherwise email the supplier via **Gmail** asking for a delivery date, then `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"po": "PO-61204"}'),
        (C, "sap.get_po", '{"po": "PO-61204"}'),
        (R, "sap.get_po", '{"status": "received", "received_at": "2026-10-27"}'),
        (A, "PO-61204 was received on 2026-10-27. No chase needed."),
        (C, "complete_case", "{}"),
        (R, "complete_case", '{"status": "completed"}'),
    ],
    gt("not_a_failure", "none", '"status": "received"'),
    ["User: 'It didn't email the supplier. Why did this Run fail?'"],
)

# ---------------------------------------------------------------- ambiguity slice (taxonomy gaps)

case(
    "G01", "ambiguity", "Downloading invoices from a carrier portal (changed layout)",
    run("run_g01", "failed", "bld_g01", error="Element not found"),
    """
# GOAL
Download this week's invoices from the carrier portal.

# STEPS
1. Use **Enterprise Browser** with the Login **GLS portal** to sign in.
2. Click "Export CSV" on the Invoices page and save the file to Files.
""",
    [
        (C, "browser.login", '{"login": "GLS portal"}'),
        (R, "browser.login", "Signed in. Banner: \"We've refreshed our look! Find your documents under My Account → Billing.\""),
        (C, "browser.click", '{"text": "Export CSV"}'),
        (R, "browser.click", "ERROR: Element not found: button 'Export CSV'"),
        (A, "I can't find the Export CSV button."),
    ],
    gt("named_pattern", "aop_change", "We've refreshed our look!",
       acceptable=["named_pattern", "aop_ambiguity", "connection_failure"]),
)

case(
    "G02", "ambiguity", "Carrier tracking during peak season (rate limit)",
    run("run_g02", "failed", "bld_g02", case_id="case_g02", case_state="Failed (no reason)",
        error="429 from carrier API"),
    """
# GOAL
Update one shipment's tracking status.

# STEPS
1. Call `claim_case` to get the tracking number.
2. Get the latest status from the **DPD** Connection.
3. Call `update_case` with the status, then `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"tracking": "0953 4412 8890"}'),
        (C, "dpd.track", '{"tracking": "09534412 8890"}'),
        (R, "dpd.track", "ERROR 429 Too Many Requests. Retry-After: 600"),
        (A, "DPD is rate limiting. I can't get the status."),
    ],
    gt("connection_failure", "aop_change", "Retry-After: 600",
       acceptable=["connection_failure", "named_pattern", "missing_terminal_closure"],
       fix_ok=["aop_change", "connection_change"]),
    ["Black Friday week: 1,900 tracking cases queued; ~30% of Runs today hit the same 429."],
)

case(
    "G03", "ambiguity", "Supplier portal timeouts",
    run("run_g03", "failed", "bld_g03", error="504 Gateway Timeout"),
    """
# GOAL
Submit one ASN (advance shipping notice) on the retailer's supplier portal.

# STEPS
1. Use **Enterprise Browser** with the Login **Tesco Partner Toolkit** to open "New ASN".
2. Enter the shipment lines and submit.
""",
    [
        (C, "browser.open", '{"url": "New ASN"}'),
        (R, "browser.open", "ERROR 504 Gateway Timeout (served by the portal's load balancer)"),
        (C, "browser.open", '{"url": "New ASN"}'),
        (R, "browser.open", "ERROR 504 Gateway Timeout (served by the portal's load balancer)"),
        (A, "The portal keeps timing out."),
    ],
    gt("connection_failure", "aop_change", "ERROR 504 Gateway Timeout",
       acceptable=["connection_failure", "named_pattern"],
       fix_ok=["aop_change", "connection_change"]),
    ["Other Agents on other portals run normally. The portal's status page reports 'degraded performance' today."],
)

case(
    "G04", "ambiguity", "Invoice posting + supplier notification (partial completion)",
    run("run_g04", "failed", "bld_g04", case_id="case_g04", case_state="Failed (no reason)",
        error="gmail.send_message 503"),
    """
# GOAL
Post one invoice and notify the supplier.

# STEPS
1. Call `claim_case`.
2. Post the vendor bill in **NetSuite**.
3. Email the supplier the payment date via **Gmail**.
4. Call `complete_case`.
""",
    [
        (C, "claim_case", "{}"),
        (R, "claim_case", '{"invoice": "INV-5512"}'),
        (C, "netsuite.post_bill", '{"invoice": "INV-5512"}'),
        (R, "netsuite.post_bill", '{"status": "posted"}'),
        (C, "gmail.send_message", '{"to": "ar@supplier.example"}'),
        (R, "gmail.send_message", "ERROR 503 Service Unavailable: backend error, try again later"),
        (A, "Email failed with a temporary Gmail error."),
    ],
    gt("connection_failure", "aop_change", "ERROR 503 Service Unavailable",
       acceptable=["connection_failure", "missing_terminal_closure", "named_pattern"],
       fix_ok=["aop_change"]),
    ["The bill is posted in NetSuite but the case shows Failed, so the AP team re-ran it and posted a duplicate."],
)

case(
    "G05", "ambiguity", "Extracting VAT IDs from invoices (wrong data extracted)",
    run("run_g05", "completed", "bld_g05"),
    """
# GOAL
Register one supplier invoice.

# STEPS
1. Read the invoice PDF and extract the supplier name, VAT ID and total.
2. Create the vendor bill in **NetSuite**, matching the vendor by VAT ID.
""",
    [
        (A, "Extracted: supplier 'Frischeparadies KG'; VAT ID 'CZ45272956'; total 8,412.00 EUR."),
        (C, "netsuite.find_vendor", '{"vat": "CZ45272956"}'),
        (R, "netsuite.find_vendor", '{"vendor": "200140 RetailCo CZ s.r.o. (our own entity)"}'),
        (C, "netsuite.create_bill", '{"vendor": "200140", "amount": 8412.00}'),
        (R, "netsuite.create_bill", '{"status": "created"}'),
    ],
    gt("aop_ambiguity", "aop_change", "VAT ID 'CZ45272956'", acceptable=["aop_ambiguity", "named_pattern"]),
    ["The invoice shows two VAT IDs: the supplier's (DE811203984) and the bill-to customer's (CZ45272956, ours)."],
)


def main():
    out = Path(__file__).with_name("cases.jsonl")
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    with out.open("w") as f:
        for c in CASES:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"wrote {len(CASES)} cases to {out}")


if __name__ == "__main__":
    main()
