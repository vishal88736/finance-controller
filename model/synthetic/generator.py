"""
Synthetic Financial Data Generator with Ground Truth.
Generates 200+ multi-source financial records covering:
- Clean exact matches (120)
- Fuzzy entity / reference matches (25)
- Amount discrepancies (15)
- Date discrepancies / settlement lags (10)
- Missing counterpart records (10)
- Duplicate transactions (10)
- Ambiguous multi-candidate matches (10)
Outputs:
- source_a_ledger.csv
- source_b_bank.csv
- source_c_payouts.xlsx
- ground_truth.json
"""

import json
import random
import os
from datetime import datetime, timedelta, timezone
import pandas as pd

# Vendors and Entities
VENDORS = [
    ("Acme Cloud Corp", "Acme Cloud Services", "ACME-CLOUD-US"),
    ("Stripe Payments", "Stripe Inc", "STRIPE-PAY"),
    ("Razorpay Software", "Razorpay Pvt Ltd", "RAZORPAY-SETTLE"),
    ("AWS Infrastructure", "Amazon Web Services", "AWS-INFRA-EAST"),
    ("Google Cloud Platform", "Google Ireland Ltd", "GCP-WORKSPACE"),
    ("Salesforce CRM", "Salesforce Inc", "SFDC-SUB"),
    ("Slack Technologies", "Slack Inc", "SLACK-COMM"),
    ("Zoom Video Comm", "Zoom Communications", "ZOOM-PRO-MTG"),
    ("Twilio API Services", "Twilio Ireland", "TWILIO-SMS"),
    ("Figma Design Systems", "Figma Inc", "FIGMA-SEATS"),
    ("Datadog Monitoring", "Datadog SaaS", "DATADOG-APM"),
    ("Atlassian Jira", "Atlassian Pty Ltd", "JIRA-CLOUD"),
    ("HubSpot Marketing", "HubSpot Inc", "HUBSPOT-ENT"),
    ("GitHub Enterprise", "GitHub Inc", "GH-COPILOT-SEATS"),
    ("Snowflake Data Cloud", "Snowflake Inc", "SNOWFLAKE-WH"),
    ("Notion Labs", "Notion Inc", "NOTION-WORKSPACE"),
    ("Intercom Support", "Intercom R&D", "INTERCOM-MESSAGING"),
    ("Cloudflare Edge", "Cloudflare Inc", "CLOUDFLARE-CDN"),
    ("Zendesk Support", "Zendesk Inc", "ZENDESK-SEATS"),
    ("Workday HRMS", "Workday Inc", "WORKDAY-PAYROLL")
]

CURRENCIES = ["USD", "EUR", "GBP", "INR"]

def generate_synthetic_dataset(output_dir: str = None, total_records: int = 200) -> dict:
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))
    
    os.makedirs(output_dir, exist_ok=True)
    random.seed(42)  # Deterministic seed for reproducible evaluation

    records_a = []
    records_b = []
    records_c = []
    ground_truth = {
        "dataset_name": "Multi-Source Financial Reconciliation Benchmark",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": total_records,
        "cases": {},
        "summary": {
            "exact_matches": 120,
            "fuzzy_matches": 25,
            "amount_discrepancies": 15,
            "date_discrepancies": 10,
            "missing_records": 10,
            "duplicates": 10,
            "ambiguous_candidates": 10
        }
    }

    base_date = datetime(2026, 8, 1)
    
    # 1. Exact Clean Matches (120 records)
    for i in range(1, 121):
        txn_id_a = f"TXN-LEDGER-{1000 + i}"
        txn_id_b = f"BNK-REF-{5000 + i}"
        common_ref = f"INV-2026-{2000 + i}"
        vendor_info = VENDORS[i % len(VENDORS)]
        amount = round(random.uniform(50.0, 15000.0), 2)
        date_obj = base_date + timedelta(days=(i % 25))
        date_str = date_obj.strftime("%Y-%m-%d")
        currency = CURRENCIES[i % len(CURRENCIES)]

        # Tax details for tax-line matcher capability
        taxable_amt = amount
        if i % 15 == 3:
            t_rate = 0.18
            t_amt = 0.0  # Missing tax
        elif i % 15 == 7:
            t_rate = 0.12  # Mismatched rate (12% vs 18%)
            t_amt = round(taxable_amt * 0.12, 2)
        elif i % 15 == 11:
            t_rate = 0.18  # Arithmetic discrepancy
            t_amt = round(taxable_amt * 0.18 + 15.50, 2)
        else:
            t_rate = 0.18  # Exact match
            t_amt = round(taxable_amt * 0.18, 2)
        tot_amt = round(taxable_amt + t_amt, 2)

        records_a.append({
            "record_id": txn_id_a,
            "reference_id": common_ref,
            "date": date_str,
            "entity": vendor_info[0],
            "description": f"Payment for {vendor_info[0]} - {common_ref}",
            "amount": amount,
            "taxable_amount": taxable_amt,
            "tax_rate": t_rate,
            "tax_amount": t_amt,
            "total_amount": tot_amt,
            "currency": currency,
            "source": "source_a_ledger"
        })

        records_b.append({
            "record_id": txn_id_b,
            "reference_id": common_ref,
            "date": date_str,
            "entity": vendor_info[1],
            "description": f"Direct Debit / Transfer: {common_ref}",
            "amount": amount,
            "currency": currency,
            "source": "source_b_bank"
        })

        # Put some in Gateway Payouts as 3rd source
        if i % 3 == 0:
            records_c.append({
                "payout_id": f"PAYOUT-{7000 + i}",
                "order_ref": common_ref,
                "payout_date": date_str,
                "merchant_entity": vendor_info[2],
                "net_amount": amount,
                "currency": currency,
                "source": "source_c_payouts"
            })

        ground_truth["cases"][txn_id_a] = {
            "ground_truth_status": "MATCHED",
            "matched_record_id": txn_id_b,
            "category": "EXACT_MATCH",
            "expected_confidence": 100.0,
            "amount_a": amount,
            "amount_b": amount,
            "discrepancy_reason": None
        }

    # 2. Fuzzy Matches (25 records: 121 to 145)
    for i in range(121, 146):
        txn_id_a = f"TXN-LEDGER-{1000 + i}"
        txn_id_b = f"BNK-REF-{5000 + i}"
        common_num = 2000 + i
        ref_a = f"INV-2026-{common_num}"
        ref_b = f"REF#{common_num}/AUTO"  # slightly different formatting
        vendor_info = VENDORS[i % len(VENDORS)]
        amount = round(random.uniform(100.0, 8500.0), 2)
        date_obj = base_date + timedelta(days=(i % 25))
        currency = CURRENCIES[i % len(CURRENCIES)]

        records_a.append({
            "record_id": txn_id_a,
            "reference_id": ref_a,
            "date": date_obj.strftime("%Y-%m-%d"),
            "entity": vendor_info[0],
            "description": f"Invoice settlement {ref_a}",
            "amount": amount,
            "currency": currency,
            "source": "source_a_ledger"
        })

        # Slight variation in entity & date (+1 day)
        date_b = (date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
        records_b.append({
            "record_id": txn_id_b,
            "reference_id": ref_b,
            "date": date_b,
            "entity": vendor_info[2],
            "description": f"POS Cleared: {vendor_info[1]} {ref_b}",
            "amount": amount,
            "currency": currency,
            "source": "source_b_bank"
        })

        ground_truth["cases"][txn_id_a] = {
            "ground_truth_status": "MATCHED",
            "matched_record_id": txn_id_b,
            "category": "FUZZY_MATCH",
            "expected_confidence": 88.0,
            "amount_a": amount,
            "amount_b": amount,
            "discrepancy_reason": "Slight entity name and reference formatting variance"
        }

    # 3. Amount Discrepancies (15 records: 146 to 160)
    for i in range(146, 161):
        txn_id_a = f"TXN-LEDGER-{1000 + i}"
        txn_id_b = f"BNK-REF-{5000 + i}"
        common_ref = f"INV-2026-{2000 + i}"
        vendor_info = VENDORS[i % len(VENDORS)]
        amount_a = round(random.uniform(500.0, 12000.0), 2)
        # Bank has 2.5% gateway fee or $15 wire fee deducted
        fee = 15.00 if i % 2 == 0 else round(amount_a * 0.025, 2)
        amount_b = round(amount_a - fee, 2)
        date_str = (base_date + timedelta(days=(i % 25))).strftime("%Y-%m-%d")
        currency = "USD"

        records_a.append({
            "record_id": txn_id_a,
            "reference_id": common_ref,
            "date": date_str,
            "entity": vendor_info[0],
            "description": f"Gross amount billed {common_ref}",
            "amount": amount_a,
            "currency": currency,
            "source": "source_a_ledger"
        })

        records_b.append({
            "record_id": txn_id_b,
            "reference_id": common_ref,
            "date": date_str,
            "entity": vendor_info[1],
            "description": f"Net settlement received {common_ref} (fee deducted)",
            "amount": amount_b,
            "currency": currency,
            "source": "source_b_bank"
        })

        ground_truth["cases"][txn_id_a] = {
            "ground_truth_status": "AMOUNT_MISMATCH",
            "matched_record_id": txn_id_b,
            "category": "AMOUNT_DISCREPANCY",
            "expected_confidence": 75.0,
            "amount_a": amount_a,
            "amount_b": amount_b,
            "discrepancy_reason": f"Amount difference of ${round(amount_a - amount_b, 2)} due to processing fees"
        }

    # 4. Date Discrepancies / Settlement Lag (10 records: 161 to 170)
    for i in range(161, 171):
        txn_id_a = f"TXN-LEDGER-{1000 + i}"
        txn_id_b = f"BNK-REF-{5000 + i}"
        common_ref = f"INV-2026-{2000 + i}"
        vendor_info = VENDORS[i % len(VENDORS)]
        amount = round(random.uniform(200.0, 5000.0), 2)
        date_a = base_date + timedelta(days=2)
        date_b = date_a + timedelta(days=7)  # 7-day settlement lag (e.g. international ACH)

        records_a.append({
            "record_id": txn_id_a,
            "reference_id": common_ref,
            "date": date_a.strftime("%Y-%m-%d"),
            "entity": vendor_info[0],
            "description": f"Initiated wire {common_ref}",
            "amount": amount,
            "currency": "USD",
            "source": "source_a_ledger"
        })

        records_b.append({
            "record_id": txn_id_b,
            "reference_id": common_ref,
            "date": date_b.strftime("%Y-%m-%d"),
            "entity": vendor_info[1],
            "description": f"International Wire Credited {common_ref}",
            "amount": amount,
            "currency": "USD",
            "source": "source_b_bank"
        })

        ground_truth["cases"][txn_id_a] = {
            "ground_truth_status": "MATCHED",
            "matched_record_id": txn_id_b,
            "category": "DATE_LAG",
            "expected_confidence": 85.0,
            "amount_a": amount,
            "amount_b": amount,
            "discrepancy_reason": "Date lag of 7 days between ledger booking and bank credit"
        }

    # 5. Missing Records (10 records: 171 to 180)
    # 5 in Source A only, 5 in Source B only
    for i in range(171, 176):
        txn_id_a = f"TXN-LEDGER-{1000 + i}"
        common_ref = f"INV-2026-{2000 + i}"
        vendor_info = VENDORS[i % len(VENDORS)]
        amount = round(random.uniform(300.0, 4000.0), 2)
        date_str = (base_date + timedelta(days=(i % 25))).strftime("%Y-%m-%d")

        records_a.append({
            "record_id": txn_id_a,
            "reference_id": common_ref,
            "date": date_str,
            "entity": vendor_info[0],
            "description": f"Pending invoice unpaid in bank: {common_ref}",
            "amount": amount,
            "currency": "USD",
            "source": "source_a_ledger"
        })

        ground_truth["cases"][txn_id_a] = {
            "ground_truth_status": "MISSING_RECORD",
            "matched_record_id": None,
            "category": "UNMATCHED_MISSING_COUNTERPART",
            "expected_confidence": 0.0,
            "amount_a": amount,
            "amount_b": None,
            "discrepancy_reason": "Record exists in Ledger but has no corresponding Bank debit/credit entry"
        }

    for i in range(176, 181):
        txn_id_b = f"BNK-REF-{5000 + i}"
        common_ref = f"UNKNOWN-FEE-{2000 + i}"
        amount = round(random.uniform(20.0, 150.0), 2)
        date_str = (base_date + timedelta(days=(i % 25))).strftime("%Y-%m-%d")

        records_b.append({
            "record_id": txn_id_b,
            "reference_id": common_ref,
            "date": date_str,
            "entity": "Bank Service Charge",
            "description": f"Monthly Account Maintenance Fee {common_ref}",
            "amount": amount,
            "currency": "USD",
            "source": "source_b_bank"
        })

        ground_truth["cases"][txn_id_b] = {
            "ground_truth_status": "MISSING_RECORD",
            "matched_record_id": None,
            "category": "UNMATCHED_UNRECORDED_BANK_FEE",
            "expected_confidence": 0.0,
            "amount_a": None,
            "amount_b": amount,
            "discrepancy_reason": "Bank charge not recorded in internal ledger"
        }

    # 6. Duplicate Records (10 records: 181 to 190)
    for i in range(181, 186):
        txn_id_a1 = f"TXN-LEDGER-{1000 + i}"
        txn_id_a2 = f"TXN-LEDGER-{1000 + i}-DUP"
        txn_id_b = f"BNK-REF-{5000 + i}"
        common_ref = f"INV-2026-{2000 + i}"
        vendor_info = VENDORS[i % len(VENDORS)]
        amount = round(random.uniform(500.0, 2500.0), 2)
        date_str = (base_date + timedelta(days=(i % 25))).strftime("%Y-%m-%d")

        # Posted twice in ledger
        records_a.append({
            "record_id": txn_id_a1,
            "reference_id": common_ref,
            "date": date_str,
            "entity": vendor_info[0],
            "description": f"Vendor payment {common_ref}",
            "amount": amount,
            "currency": "USD",
            "source": "source_a_ledger"
        })
        records_a.append({
            "record_id": txn_id_a2,
            "reference_id": common_ref,
            "date": date_str,
            "entity": vendor_info[0],
            "description": f"Duplicate accidental entry: {common_ref}",
            "amount": amount,
            "currency": "USD",
            "source": "source_a_ledger"
        })

        records_b.append({
            "record_id": txn_id_b,
            "reference_id": common_ref,
            "date": date_str,
            "entity": vendor_info[1],
            "description": f"Cleared payment {common_ref}",
            "amount": amount,
            "currency": "USD",
            "source": "source_b_bank"
        })

        ground_truth["cases"][txn_id_a1] = {
            "ground_truth_status": "MATCHED",
            "matched_record_id": txn_id_b,
            "category": "DUPLICATE_PRIMARY",
            "expected_confidence": 95.0,
            "amount_a": amount,
            "amount_b": amount,
            "discrepancy_reason": "Primary transaction matched to bank statement"
        }
        ground_truth["cases"][txn_id_a2] = {
            "ground_truth_status": "DUPLICATE",
            "matched_record_id": None,
            "category": "DUPLICATE_ENTRY",
            "expected_confidence": 0.0,
            "amount_a": amount,
            "amount_b": None,
            "discrepancy_reason": f"Duplicate booking of reference {common_ref} in ledger"
        }

    # 7. Ambiguous / Multiple Candidates (10 records: 191 to 200)
    for i in range(191, 196):
        txn_id_a = f"TXN-LEDGER-{1000 + i}"
        txn_id_b1 = f"BNK-REF-{5000 + i}-CAND1"
        txn_id_b2 = f"BNK-REF-{5000 + i}-CAND2"
        vendor_info = VENDORS[i % len(VENDORS)]
        amount = 1250.00  # Exact identical rounded amounts on same date
        date_str = (base_date + timedelta(days=15)).strftime("%Y-%m-%d")

        records_a.append({
            "record_id": txn_id_a,
            "reference_id": f"GENERIC-PAY-{i}",
            "date": date_str,
            "entity": vendor_info[0],
            "description": f"Subscription payment to {vendor_info[0]}",
            "amount": amount,
            "currency": "USD",
            "source": "source_a_ledger"
        })

        records_b.append({
            "record_id": txn_id_b1,
            "reference_id": f"UNLABELED-TRF-{i}-1",
            "date": date_str,
            "entity": vendor_info[1],
            "description": f"Debit transfer {vendor_info[1]}",
            "amount": amount,
            "currency": "USD",
            "source": "source_b_bank"
        })

        records_b.append({
            "record_id": txn_id_b2,
            "reference_id": f"UNLABELED-TRF-{i}-2",
            "date": date_str,
            "entity": vendor_info[1],
            "description": f"Debit transfer {vendor_info[1]}",
            "amount": amount,
            "currency": "USD",
            "source": "source_b_bank"
        })

        ground_truth["cases"][txn_id_a] = {
            "ground_truth_status": "UNRESOLVED_AMBIGUOUS",
            "matched_record_id": None,
            "category": "AMBIGUOUS_MULTI_CANDIDATE",
            "expected_confidence": 78.0,
            "amount_a": amount,
            "amount_b": None,
            "discrepancy_reason": f"Two candidates ({txn_id_b1} and {txn_id_b2}) found with identical amount ($1,250.00), entity, and date. Needs human investigation."
        }

    # Save to files
    df_a = pd.DataFrame(records_a)
    df_b = pd.DataFrame(records_b)
    df_c = pd.DataFrame(records_c)

    file_a_path = os.path.join(output_dir, "source_a_ledger.csv")
    file_b_path = os.path.join(output_dir, "source_b_bank.csv")
    file_c_path = os.path.join(output_dir, "source_c_payouts.xlsx")
    gt_path = os.path.join(output_dir, "ground_truth.json")

    df_a.to_csv(file_a_path, index=False)
    df_b.to_csv(file_b_path, index=False)
    df_c.to_excel(file_c_path, index=False)

    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)

    return {
        "source_a_path": file_a_path,
        "source_b_path": file_b_path,
        "source_c_path": file_c_path,
        "ground_truth_path": gt_path,
        "total_source_a": len(records_a),
        "total_source_b": len(records_b),
        "total_source_c": len(records_c),
        "ground_truth_cases": len(ground_truth["cases"])
    }

if __name__ == "__main__":
    result = generate_synthetic_dataset()
    print("Synthetic dataset generated successfully:")
    print(f"- Source A (Ledger): {result['total_source_a']} records -> {result['source_a_path']}")
    print(f"- Source B (Bank): {result['total_source_b']} records -> {result['source_b_path']}")
    print(f"- Source C (Payouts): {result['total_source_c']} records -> {result['source_c_path']}")
    print(f"- Ground Truth: {result['ground_truth_cases']} cases -> {result['ground_truth_path']}")
