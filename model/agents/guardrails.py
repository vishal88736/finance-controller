"""
Layered Guardrail Architecture for the AI Finance Controller.

Every user message flows through all six layers before producing an answer:

    USER MESSAGE
        ↓
    1. Input Safety           — injection, jailbreak, secrets, encoding tricks
    2. Domain / Intent        — finance-only domain, paraphrase-aware
    3. Thread Scope           — thread exists, all ops scoped to it
    4. Tool Permission        — only whitelisted financial tools may run
    5. Evidence Validation    — answers must be grounded in retrieved evidence
    6. Output Safety          — no ground truth, prompts, secrets, cross-thread leak

All layers are deterministic Python — no LLM is used to make safety decisions.
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..database.models import Thread


class GuardrailVerdict(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


OFF_TOPIC_REFUSAL = (
    "I can help with reconciliation, settlement analysis, financial exceptions, "
    "and questions about the data in this thread."
)

INJECTION_REFUSAL = (
    "This request attempts to override my operating instructions. "
    "I can only help with reconciliation and financial analysis of this thread's data."
)

THREAD_REFUSAL = (
    "That identifier does not exist in this thread. I can only answer questions "
    "about documents, transactions, and reconciliation results within the current thread."
)

BENCHMARK_REFUSAL = (
    "Benchmark evaluation data and answer keys are not available through Q&A. "
    "I can only answer questions about this thread's reconciliation results."
)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1: Input Safety
# ─────────────────────────────────────────────────────────────────────────────

INJECTION_PATTERNS = [
    # instruction override
    r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions?|rules?|prompts?|directives?)",
    r"disregard\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)",
    r"forget\s+(all\s+|your\s+)?(previous|prior|instructions?|rules?)",
    r"(override|bypass|jailbreak|circumvent)\s+(your\s+)?(instructions?|rules?|guardrails?|filters?|restrictions?)",
    # persona hijack
    r"you\s+are\s+now\s+(dan|unrestricted|god\s*mode|a\s+different\s+ai|an?\s+(un)?restricted)",
    r"(pretend|act)\s+(to\s+be|as(?:\s+an?)?)\s+(a\s+)?(unrestricted|dan|different\s+ai|ai\s+without\s+rules)",
    r"(developer|god|root|admin|sudo)\s+mode",
    r"stay\s+(in\s+)?(character|role)\s+as",
    # prompt / secret extraction
    r"(reveal|show|print|export|repeat|output|give|leak|dump|expose)\s+(me\s+)?(the\s+|your\s+)?(system|internal|hidden|original|initial|full|complete)?\s*(prompt|instructions?|configuration|rules?|guardrails?)",
    r"(reveal|show|print|export|repeat|output|give|leak|dump|expose)\s+(me\s+)?(the\s+|your\s+)?(api[\s_-]?key|secret|credentials?|password|token)",
    r"(reveal|show|print|export|read|give|dump|cat|open)\s+(me\s+)?(the\s+)?(ground[\s_-]*truth|answer[\s_-]*key|benchmark\s+answers?|evaluation\s+(answers?|key|data)|hidden\s+answers?)",
    r"ground[\s_-]*truth",
    r"answer[\s_-]*key",
    # encoding / delimiter tricks used to smuggle instructions
    r"</?(system|assistant|developer)>",
    r"\bBEGIN\s+(SYSTEM\s+)?PROMPT\b",
    # tool abuse
    r"execute\s+(arbitrary\s+)?(sql|shell|os|python|code)",
    r"\b(drop|delete|truncate)\s+(table|database)",
    r"import\s+(os|subprocess|shutil)\b",
    r"open\s*\(\s*['\"]?(/etc/passwd|ground_truth\.json)",
]

# Unicode confusable normalization for injection detection
_UNICODE_MAP = {
    "\uff01": "!", "\uff1f": "?", "\uff0c": ",", "\uff1b": ";",
    "\uff1a": ":", "\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
    "\u00a0": " ", "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "",
}


def _normalize_for_safety(text: str) -> str:
    """Normalize confusable characters so obfuscation cannot bypass patterns."""
    out = text
    for k, v in _UNICODE_MAP.items():
        out = out.replace(k, v)
    # collapse repeated whitespace, strip zero-width chars
    out = re.sub(r"\s+", " ", out)
    # homoglyph-ish: replace fullwidth letters with ascii
    out = "".join(
        chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c for c in out
    )
    return out


def check_input_safety(user_prompt: str) -> Tuple[GuardrailVerdict, Optional[str]]:
    """
    Layer 1: Reject prompt injection, jailbreaks, secret extraction, and
    ground-truth extraction attempts (including unicode-obfuscated variants).
    """
    if not user_prompt or not user_prompt.strip():
        return GuardrailVerdict.BLOCK, "Please enter a financial question or instruction."

    if len(user_prompt) > 4000:
        return GuardrailVerdict.BLOCK, "Input exceeds the maximum allowed length."

    norm = _normalize_for_safety(user_prompt).lower()

    for pat in INJECTION_PATTERNS:
        if re.search(pat, norm, flags=re.IGNORECASE):
            if "ground" in pat or "answer" in pat or "benchmark" in pat:
                return GuardrailVerdict.BLOCK, BENCHMARK_REFUSAL
            return GuardrailVerdict.BLOCK, INJECTION_REFUSAL

    return GuardrailVerdict.ALLOW, None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2: Domain / Intent Validation (paraphrase-aware)
# ─────────────────────────────────────────────────────────────────────────────

# Requests that are clearly out of scope no matter what finance words they contain
_OFF_TOPIC_PATTERNS = [
    r"\b(poems?|poetry|rhyme[sd]?|haiku|limericks?|sonnets?|verses?)\b",
    r"\b(jokes?|funny\s+(story|haiku)|riddles?|puns?)\b",
    r"\bwrite\s+(me\s+)?a?\s*(song|lyrics?|lullaby)\b",
    r"\b(recipes?|cook(ing)?|baking|ingredients?|cocktails?|dinner\s+ideas)\b",
    r"\b(weather|forecast|rain\s+today|temperature\s+in|hurricane|snowfall)\b",
    r"\b(president|election|prime\s+minister|democrat|republican|parliament|politics|vote\s+for)\b",
    r"\b(quantum|black\s*holes?|astronomy|astrology|horoscope|zodiac)\b",
    r"\b(football|cricket\s+score|stock\s+price\s+of\s+apple|cryptocurrency\s+price)\b",
    r"\b(essay|book\s+report|movie\s+recommendations?|travel\s+itinerary)\b",
    r"\b(hack|scrape|ddos|malware|keylogger|exploit)\b",
    r"\b(who\s+are\s+you|what('s| is)\s+your\s+name|who\s+made\s+you|are\s+you\s+human|what\s+model\s+are\s+you)\b",
]

# Finance-domain lexicon: stems so paraphrases match ("reconciling", "reconciliation")
_FINANCE_TERMS = [
    "reconcil", "match", "unmatch", "exception", "discrepanc", "fee", "delta",
    "invoice", "settlement", "payout", "ledger", "bank", "statement",
    "transaction", "txn", "record", "amount", "balance", "counterpart",
    "duplicate", "ambiguous", "missing", "unresolved", "evidence",
    "metric", "accuracy", "precision", "recall", "f1", "throughput",
    "confidence", "score", "document", "upload", "file", "csv", "xlsx",
    "json", "fingerprint", "sha", "digest", "hash", "settle",
    "payment", "gateway", "gateway-fee", "gateway fee", "net", "gross",
    "currency", "fx", "wire", "transfer", "deposit", "debit", "credit",
    "vendor", "merchant", "entity", "payable", "receivable", "ar ", "ap ",
    "journal", "posting", "audit", "run", "process", "compare",
]

_SHORT_ALLOWED = {
    "hi", "hello", "hey", "help", "start", "overview", "status",
    "summary", "hi!", "hello!", "summarize", "summarise",
}


def check_domain_intent(user_prompt: str) -> Tuple[GuardrailVerdict, Optional[str]]:
    """
    Layer 2: Finance-domain validation.

    Order matters:
    1. A clearly off-topic request is rejected even if it mentions finance words.
    2. Otherwise the message must contain a finance term / record ID / allowed
       greeting to pass.
    """
    text = user_prompt.strip().lower()
    norm = _normalize_for_safety(text)

    # 1. Off-topic content overrides finance keywords
    for pat in _OFF_TOPIC_PATTERNS:
        if re.search(pat, norm, flags=re.IGNORECASE):
            return GuardrailVerdict.BLOCK, OFF_TOPIC_REFUSAL

    # 2. Positive finance signals
    if norm in _SHORT_ALLOWED:
        return GuardrailVerdict.ALLOW, None

    has_finance_term = any(t in norm for t in _FINANCE_TERMS)
    has_record_id = bool(re.search(r"\b[A-Za-z0-9]+[-_][A-Za-z0-9-_]+\b", user_prompt))
    is_question_about_thread_data = bool(
        re.search(r"\b(what|which|why|how|when|where|who|show|list|explain|tell me|find|is there|are there|how many|any)\b", norm)
        and re.search(r"\b(this|current|the|my|our)\s+(thread|workspace|analysis|investigation|data|documents?|records?|files?|results?|exceptions?|matches?|transactions?)\b", norm)
    )

    if has_finance_term or has_record_id or is_question_about_thread_data:
        return GuardrailVerdict.ALLOW, None

    return GuardrailVerdict.BLOCK, OFF_TOPIC_REFUSAL


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3: Thread Scope Validation
# ─────────────────────────────────────────────────────────────────────────────


def check_thread_scope(db: Session, thread_id: Optional[str]) -> Tuple[GuardrailVerdict, Optional[str]]:
    """
    Layer 3: Thread scope enforcement. The thread must exist; every downstream
    query is filtered by this thread_id.
    """
    if not thread_id:
        return GuardrailVerdict.BLOCK, "Thread ID is required for operations."

    try:
        thread = db.query(Thread).filter(Thread.id == thread_id).first()
    except Exception:
        return GuardrailVerdict.BLOCK, THREAD_REFUSAL

    if not thread:
        return GuardrailVerdict.BLOCK, THREAD_REFUSAL

    return GuardrailVerdict.ALLOW, None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 4: Tool Permission Validation
# ─────────────────────────────────────────────────────────────────────────────

ALLOWED_QA_TOOLS = frozenset({
    "get_thread_documents_tool",
    "get_reconciliation_summary_tool",
    "get_unmatched_transactions_tool",
    "get_ambiguous_transactions_tool",
    "get_transaction_result_tool",
    "get_material_exceptions_tool",
    "get_metrics_tool",
})


def check_tool_permission(tool_name: str) -> Tuple[GuardrailVerdict, Optional[str]]:
    """Layer 4: Only whitelisted deterministic tools may execute."""
    if tool_name in ALLOWED_QA_TOOLS:
        return GuardrailVerdict.ALLOW, None
    return (
        GuardrailVerdict.BLOCK,
        f"Tool '{tool_name}' is not authorized for Q&A operations.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Layer 5: Evidence Validation (called after tool retrieval, before answering)
# ─────────────────────────────────────────────────────────────────────────────

_ID_FIELDS = (
    "record_id", "record_id_a", "record_id_b", "exception_id", "match_id",
    "document_id", "reference_id", "target_record_id", "filename", "source",
)
_AMOUNT_FIELDS = (
    "amount", "amount_a", "amount_b", "amount_discrepancy", "amount_difference",
    "total_amount_processed", "total_amount_matched", "total_amount_discrepancy",
    "fee_delta", "target_amount",
)
_COUNT_FIELDS = (
    "total_records", "matched_count", "exceptions_count", "unmatched_count",
    "record_count", "total", "count", "true_positives", "false_positives",
    "false_negatives", "true_negatives", "candidate_count",
)


def _extract_facts(obj: Any, facts: Dict[str, float]) -> None:
    """Recursively collect the latest value per named numeric fact."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _ID_FIELDS and isinstance(v, str):
                facts[f"id:{v}"] = 1.0
            elif k in _AMOUNT_FIELDS and isinstance(v, (int, float)):
                facts[f"amount:{k}"] = float(v)
            elif k in _COUNT_FIELDS and isinstance(v, (int, float)):
                facts[f"count:{k}"] = float(v)
            else:
                _extract_facts(v, facts)
    elif isinstance(obj, list):
        for item in obj:
            _extract_facts(item, facts)


_NUM_IN_ANSWER = re.compile(
    r"(?<![\w.])\d{1,3}(?:,\d{3})*(?:\.\d+)?(?![\w.])|(?<![\w.])\d+(?:\.\d+)?(?![\w.])"
)


def _parse_number(token: str) -> Optional[float]:
    token = token.replace(",", "").rstrip(".")
    try:
        return float(token)
    except ValueError:
        return None


def check_evidence_consistency(
    answer: str,
    retrieved_records: List[Dict[str, Any]],
    retrieved_exceptions: List[Dict[str, Any]],
    retrieved_metrics: Dict[str, Any],
    retrieved_documents: List[Dict[str, Any]],
) -> Tuple[GuardrailVerdict, Optional[str]]:
    """
    Layer 5: Numeric consistency validation.

    Every number in the proposed answer must be justifiable from retrieved
    evidence. Numbers can appear as raw values, formatted (1,500.00), or with
    a % sign. If validation fails, the caller must fall back to the
    deterministic tool result instead of the unverified answer.
    """
    evidence: Dict[str, float] = {}
    _extract_facts(retrieved_records, evidence)
    _extract_facts(retrieved_exceptions, evidence)
    _extract_facts(retrieved_metrics, evidence)
    _extract_facts(retrieved_documents, evidence)
    evidence_values = set(evidence.values())

    for match in _NUM_IN_ANSWER.finditer(answer):
        val = _parse_number(match.group(0))
        if val is None:
            continue
        # tolerated derived values: percentage points and small ordinals
        candidates = {
            val, round(val), round(val, 1), round(val, 2),
            abs(val), round(abs(val), 2),
        }
        # formatted numbers already handled by parse; allow values within tiny epsilon
        if any(any(abs(c - ev) < 0.005 for ev in evidence_values) for c in candidates):
            continue
        # allow years and simple enumeration tokens (e.g., "2 records")
        if 1990 <= val <= 2100:
            continue
        return (
            GuardrailVerdict.BLOCK,
            f"Answer contains value {match.group(0)} that is not present in the retrieved evidence.",
        )

    return GuardrailVerdict.ALLOW, None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 6: Output Safety
# ─────────────────────────────────────────────────────────────────────────────

_OUTPUT_DENY_PATTERNS = [
    (re.compile(r"ground[_\s-]*truth(\.json)?", re.IGNORECASE), "[CONFIDENTIAL_BENCHMARK]"),
    (re.compile(r"answer[_\s-]*key", re.IGNORECASE), "[CONFIDENTIAL_BENCHMARK]"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{20,50}"), "[REDACTED_KEY]"),
    (re.compile(r"lsv2_pt_[0-9A-Za-z\-_]{10,60}"), "[REDACTED_KEY]"),
    (re.compile(r"sk-[A-Za-z0-9\-_]{20,50}"), "[REDACTED_KEY]"),
]


def sanitize_output(answer: str) -> str:
    """
    Layer 6: redact ground truth references and API keys from any output.
    Applied to every final answer regardless of who generated it.
    """
    sanitized = answer
    for pattern, replacement in _OUTPUT_DENY_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


# ─────────────────────────────────────────────────────────────────────────────
# Composite engine used by orchestrator / QA graph
# ─────────────────────────────────────────────────────────────────────────────


class GuardrailEngine:
    """Facade over the six layers with convenience entry points."""

    # Layers 1 & 2
    @staticmethod
    def validate_input(user_prompt: str) -> Tuple[bool, Optional[str]]:
        verdict, refusal = check_input_safety(user_prompt)
        if verdict == GuardrailVerdict.BLOCK:
            return False, refusal
        verdict, refusal = check_domain_intent(user_prompt)
        if verdict == GuardrailVerdict.BLOCK:
            return False, refusal
        return True, None

    # Layer 3
    @staticmethod
    def validate_thread_scope(db: Session, thread_id: Optional[str]) -> Tuple[bool, Optional[str]]:
        verdict, refusal = check_thread_scope(db, thread_id)
        return verdict == GuardrailVerdict.ALLOW, refusal

    # Layer 4
    @staticmethod
    def validate_tool_permission(tool_name: str, allowed_tools: Optional[List[str]] = None) -> bool:
        if allowed_tools is not None:
            return tool_name in allowed_tools
        verdict, _ = check_tool_permission(tool_name)
        return verdict == GuardrailVerdict.ALLOW

    # Layer 5
    @staticmethod
    def validate_evidence(
        answer: str,
        retrieved_records: Optional[List[Dict[str, Any]]] = None,
        retrieved_exceptions: Optional[List[Dict[str, Any]]] = None,
        retrieved_metrics: Optional[Dict[str, Any]] = None,
        retrieved_documents: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[bool, Optional[str]]:
        verdict, reason = check_evidence_consistency(
            answer,
            retrieved_records or [],
            retrieved_exceptions or [],
            retrieved_metrics or {},
            retrieved_documents or [],
        )
        return verdict == GuardrailVerdict.ALLOW, reason

    # Layer 6
    @staticmethod
    def validate_output(answer: str) -> str:
        return sanitize_output(answer)


guardrails = GuardrailEngine()
