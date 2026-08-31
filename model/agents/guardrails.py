"""
4-Layer Guardrail Architecture for AI Finance Controller.

Layer 1: Input Classification (Detect & reject off-topic, malicious, prompt-injection, or ground-truth probing attempts)
Layer 2: Thread Scope Validation (Enforce strict thread isolation)
Layer 3: Tool Permission Validation (Allow only authorized financial query tools)
Layer 4: Output Validation (Ensure responses stay grounded and do not expose secrets)
"""

import re
from typing import Tuple, Dict, Any, Optional, List
from sqlalchemy.orm import Session
from ..database.models import Thread


OFF_TOPIC_REFUSAL = (
    "I can help with reconciliation, settlement analysis, financial exceptions, "
    "and questions about the data in this thread."
)

# Off-topic keyword and intent triggers
DISALLOWED_PATTERNS = [
    r"\b(poem|poetry|rhyme|haiku|limerick)\b",
    r"\b(joke|funny|riddle|pun)\b",
    r"\b(song|sing|lyrics|music)\b",
    r"\b(president|election|prime minister|politics|democrat|republican)\b",
    r"\b(quantum physics|quantum mechanics|relativity|astronomy|black hole)\b",
    r"\b(recipe|cook|baking|ingredients|cocktail)\b",
    r"\b(weather|rain today|temperature in)\b",
    r"\b(write (me )?a python script to (scrape|hack|bypass|jailbreak|exploit))\b",
    r"\b(ignore all previous instructions|disregard previous|system prompt|system instructions)\b",
    r"\b(who are you|what is your name|who made you|are you human)\b",
    r"\b(ground[_\s-]?truth(\.json)?|answer[_\s-]?key|hidden\s+answer|hidden\s+dataset)\b"
]

FINANCIAL_ALLOWED_KEYWORDS = [
    "reconcil", "match", "unmatch", "exception", "discrepanc", "fee", "delta",
    "invoice", "settlement", "payout", "ledger", "bank", "transaction", "txn",
    "record", "metric", "accuracy", "precision", "recall", "throughput", "f1",
    "score", "confidence", "evidence", "why", "how many", "status", "audit",
    "ambiguous", "duplicate", "missing", "difference", "counterpart", "amount",
    "balance", "statement", "document", "upload", "file", "csv", "xlsx", "run",
    "what is", "is ", "show", "tell me"
]


class GuardrailEngine:
    """
    Multi-layer guardrail validation engine.
    """

    @staticmethod
    def validate_input(user_prompt: str) -> Tuple[bool, Optional[str]]:
        """
        Layer 1: Input Guardrail.
        Checks for prompt injection, disallowed off-topic queries, ground truth probes,
        and verifies financial intent.
        Returns: (is_allowed, refusal_message_or_none)
        """
        if not user_prompt or not user_prompt.strip():
            return False, "Please enter a financial question or instruction."

        text = user_prompt.strip().lower()

        # 1. Check prompt injection / malicious overrides / ground truth probes
        if any(re.search(pat, text) for pat in [
            r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
            r"(show|print|reveal|export|read|give)\s+(me\s+)?(the\s+)?(system\s+prompt|ground\s*truth|answer\s*key)",
            r"you\s+are\s+now\s+(dan|unrestricted|god\s+mode)",
            r"act\s+as\s+a\s+(poet|comedian|unrestricted)",
            r"ground[_\s-]?truth",
            r"answer[_\s-]?key"
        ]):
            return False, OFF_TOPIC_REFUSAL

        # 2. Check disallowed off-topic domains
        for pattern in DISALLOWED_PATTERNS:
            if re.search(pattern, text):
                return False, OFF_TOPIC_REFUSAL

        # 3. Check for positive financial / domain relevance
        has_financial_term = any(kw in text for kw in FINANCIAL_ALLOWED_KEYWORDS)
        has_id_pattern = bool(re.search(r'\b[A-Za-z0-9]+[-_][A-Za-z0-9-_]+\b', user_prompt))
        is_short_greeting = text in ["hi", "hello", "help", "start", "hey", "overview"]

        if not (has_financial_term or has_id_pattern or is_short_greeting):
            return False, OFF_TOPIC_REFUSAL

        return True, None

    @staticmethod
    def validate_thread_scope(db: Session, thread_id: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        Layer 2: Thread Scope Check.
        Ensures thread exists in database and prevents cross-thread access.
        """
        if not thread_id:
            return False, "Thread ID is required for operations."

        thread = db.query(Thread).filter(Thread.id == thread_id).first()
        if not thread:
            return False, f"Thread '{thread_id}' not found or access unauthorized."

        return True, None

    @staticmethod
    def validate_tool_permission(tool_name: str, allowed_tools: List[str]) -> bool:
        """
        Layer 3: Tool Permission Check.
        Verifies that only authorized financial query tools are invoked.
        """
        return tool_name in allowed_tools

    @staticmethod
    def validate_output(answer: str) -> str:
        """
        Layer 4: Output Guardrail.
        Ensures ground truth answer keys or system credentials are never leaked.
        """
        sanitized = re.sub(r'ground_truth\.json', '[CONFIDENTIAL_BENCHMARK]', answer, flags=re.IGNORECASE)
        sanitized = re.sub(r'AIza[0-9A-Za-z-_]{20,50}', '[REDACTED_KEY]', sanitized)
        return sanitized


guardrails = GuardrailEngine()
