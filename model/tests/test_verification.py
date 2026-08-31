"""
Unit tests for the verification package.
Tests each function independently with clear, deterministic inputs.
"""

import pytest
from decimal import Decimal

from ..verification.normalizers import (
    normalize_amount,
    normalize_date,
    normalize_currency,
    normalize_entity_name,
    normalize_transaction_id,
    validate_required_fields,
)
from ..verification.matchers import (
    exact_id_match,
    amount_match,
    date_match,
    currency_match,
    entity_match,
    fuzzy_entity_match,
    description_match,
)
from ..verification.scorer import calculate_match_score
from ..verification.verifier import detect_duplicates, verify_candidate
from ..verification.exceptions import ExceptionType, classify_exception


# ==================== NORMALIZERS ====================

class TestNormalizeAmount:
    def test_decimal_string(self):
        assert normalize_amount("1050.25") == Decimal("1050.25")

    def test_float_input(self):
        assert normalize_amount(1050.25) == Decimal("1050.25")

    def test_int_input(self):
        assert normalize_amount(500) == Decimal("500.00")

    def test_currency_symbols(self):
        assert normalize_amount("$1,250.50") == Decimal("1250.50")
        assert normalize_amount("₹10,000.00") == Decimal("10000.00")
        assert normalize_amount("€999.99") == Decimal("999.99")

    def test_with_currency_code(self):
        assert normalize_amount("1050.25 USD") == Decimal("1050.25")

    def test_none_returns_zero(self):
        assert normalize_amount(None) == Decimal("0.00")

    def test_nan_returns_zero(self):
        assert normalize_amount(float("nan")) == Decimal("0.00")

    def test_empty_string_returns_zero(self):
        assert normalize_amount("") == Decimal("0.00")

    def test_negative_amount(self):
        assert normalize_amount("-250.50") == Decimal("-250.50")


class TestNormalizeDate:
    def test_iso_format(self):
        assert normalize_date("2026-08-15") == "2026-08-15"

    def test_iso_datetime(self):
        assert normalize_date("2026-08-15 14:30:00") == "2026-08-15"

    def test_slash_dmy(self):
        assert normalize_date("15/08/2026") == "2026-08-15"

    def test_named_month(self):
        assert normalize_date("Aug 15, 2026") == "2026-08-15"

    def test_none_returns_none(self):
        assert normalize_date(None) is None

    def test_garbage_returns_none(self):
        assert normalize_date("not-a-date") is None


class TestNormalizeCurrency:
    def test_usd(self):
        assert normalize_currency("USD") == "USD"

    def test_lowercase(self):
        assert normalize_currency("inr") == "INR"

    def test_symbol(self):
        assert normalize_currency("₹") == "INR"
        assert normalize_currency("$") == "USD"

    def test_none_defaults_usd(self):
        assert normalize_currency(None) == "USD"


class TestNormalizeEntityName:
    def test_basic(self):
        # 'Corp' is stripped as a business suffix
        assert normalize_entity_name("Acme Cloud Corp") == "acme cloud"

    def test_strips_suffixes(self):
        assert normalize_entity_name("Razorpay Pvt Ltd") == "razorpay"

    def test_strips_ltd(self):
        assert normalize_entity_name("Stripe Inc") == "stripe"

    def test_none_returns_empty(self):
        assert normalize_entity_name(None) == ""


class TestNormalizeTransactionId:
    def test_inv_prefix(self):
        assert normalize_transaction_id("INV-2026-2005") == "20262005"

    def test_ref_prefix(self):
        assert normalize_transaction_id("REF#2005/AUTO") == "2005"

    def test_none_returns_empty(self):
        assert normalize_transaction_id(None) == ""


class TestValidateRequiredFields:
    def test_valid_record(self):
        assert validate_required_fields({"record_id": "X", "amount": 100}) == []

    def test_missing_id(self):
        assert "record_id" in validate_required_fields({"amount": 100})

    def test_missing_amount(self):
        assert "amount" in validate_required_fields({"record_id": "X"})

    def test_alternative_id_field(self):
        assert validate_required_fields({"txn_id": "X", "amount": 100}) == []


# ==================== MATCHERS ====================

class TestExactIdMatch:
    def test_exact(self):
        assert exact_id_match("INV-2026-001", "INV-2026-001") is True

    def test_case_insensitive(self):
        assert exact_id_match("inv-2026-001", "INV-2026-001") is True

    def test_different(self):
        assert exact_id_match("INV-001", "INV-002") is False

    def test_none(self):
        assert exact_id_match(None, "INV-001") is False


class TestAmountMatch:
    def test_exact_match(self):
        is_match, diff = amount_match(Decimal("1050.25"), Decimal("1050.25"))
        assert is_match is True
        assert diff == Decimal("0.00")

    def test_within_tolerance(self):
        is_match, diff = amount_match(
            Decimal("1050.25"), Decimal("1050.20"), tolerance_cents=5
        )
        assert is_match is True
        assert diff == Decimal("0.05")

    def test_outside_tolerance(self):
        is_match, diff = amount_match(
            Decimal("1050.25"), Decimal("1050.00"), tolerance_cents=5
        )
        assert is_match is False
        assert diff == Decimal("0.25")

    def test_zero_tolerance_default(self):
        is_match, diff = amount_match(Decimal("100.00"), Decimal("100.01"))
        assert is_match is False


class TestDateMatch:
    def test_same_day(self):
        is_match, days = date_match("2026-08-15", "2026-08-15", window_days=0)
        assert is_match is True
        assert days == 0

    def test_within_window(self):
        is_match, days = date_match("2026-08-15", "2026-08-18", window_days=3)
        assert is_match is True
        assert days == 3

    def test_outside_window(self):
        is_match, days = date_match("2026-08-15", "2026-08-25", window_days=3)
        assert is_match is False
        assert days == 10

    def test_none_date(self):
        is_match, days = date_match(None, "2026-08-15")
        assert is_match is False
        assert days == 999


class TestCurrencyMatch:
    def test_same(self):
        assert currency_match("USD", "USD") is True

    def test_different(self):
        assert currency_match("USD", "EUR") is False

    def test_none_assumes_match(self):
        assert currency_match(None, "USD") is True


class TestEntityMatch:
    def test_exact(self):
        is_match, sim = entity_match("acme cloud corp", "acme cloud corp")
        assert is_match is True
        assert sim == 100.0

    def test_different(self):
        is_match, sim = entity_match("acme cloud corp", "stripe payments")
        assert is_match is False
        assert sim < 50.0


class TestFuzzyEntityMatch:
    def test_similar_names(self):
        is_match, sim = fuzzy_entity_match(
            "Amazon India Pvt Ltd", "AMAZON INDIA", threshold=70.0
        )
        assert is_match is True
        assert sim >= 70.0

    def test_dissimilar_names(self):
        is_match, sim = fuzzy_entity_match(
            "Acme Corp", "Zendesk Support", threshold=80.0
        )
        assert is_match is False


# ==================== SCORER ====================

class TestCalculateMatchScore:
    def test_perfect_match(self):
        ms = calculate_match_score(
            ref_a="INV-2026-001", ref_b="INV-2026-001",
            clean_ref_a="2026001", clean_ref_b="2026001",
            amount_a=Decimal("1500.00"), amount_b=Decimal("1500.00"),
            date_a="2026-08-15", date_b="2026-08-15",
            currency_a="USD", currency_b="USD",
            entity_a="acme cloud corp", entity_b="acme cloud services",
        )
        assert ms.total >= 85.0
        assert ms.checks["reference"] is True
        assert ms.checks["amount"] is True
        assert ms.checks["date"] is True
        assert ms.checks["currency"] is True
        assert ms.category in ["EXACT_MATCH", "FUZZY_MATCH"]

    def test_amount_mismatch_score(self):
        ms = calculate_match_score(
            ref_a="INV-2026-001", ref_b="INV-2026-001",
            clean_ref_a="2026001", clean_ref_b="2026001",
            amount_a=Decimal("1000.00"), amount_b=Decimal("975.00"),
            date_a="2026-08-15", date_b="2026-08-15",
            currency_a="USD", currency_b="USD",
            entity_a="stripe payments", entity_b="stripe inc",
        )
        assert ms.checks["amount"] is False
        assert ms.amount_diff == Decimal("25.00")


# ==================== VERIFIER ====================

class TestDetectDuplicates:
    def test_no_duplicates(self):
        class FakeRec:
            def __init__(self, rid, ref, amt):
                self.record_id = rid
                self.clean_reference_id = ref
                self.amount = amt
                self.source = "test"

        recs = [FakeRec("R1", "REF1", 100), FakeRec("R2", "REF2", 200)]
        groups = detect_duplicates(recs)
        assert len(groups) == 0

    def test_with_duplicate(self):
        class FakeRec:
            def __init__(self, rid, ref, amt):
                self.record_id = rid
                self.clean_reference_id = ref
                self.amount = amt
                self.source = "test"

        recs = [
            FakeRec("R1", "REF1", 100),
            FakeRec("R2", "REF1", 100),  # duplicate
            FakeRec("R3", "REF2", 200),
        ]
        groups = detect_duplicates(recs)
        assert len(groups) == 1
        assert "R1" in groups[0].record_ids
        assert "R2" in groups[0].record_ids


# ==================== EXCEPTION CLASSIFIER ====================

class TestClassifyException:
    def test_missing_counterpart(self):
        exc = classify_exception(
            has_candidates=False, num_candidates=0,
        )
        assert exc == ExceptionType.MISSING_COUNTERPART

    def test_duplicate(self):
        exc = classify_exception(
            has_candidates=False, num_candidates=0, is_duplicate=True,
        )
        assert exc == ExceptionType.DUPLICATE

    def test_invalid_record(self):
        exc = classify_exception(
            has_candidates=False, num_candidates=0,
            missing_fields=["amount"],
        )
        assert exc == ExceptionType.INVALID_RECORD
