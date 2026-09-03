"""
Groq LLM Client for the AI Finance Controller Copilot.

Enforces:
1. Primary LLM Provider: Groq (via GROQ_API_KEY environment variable).
2. Primary Model: llama-3.3-70b-versatile (configurable via GROQ_MODEL).
3. Grounding invariant: The LLM is used ONLY for synthesis and explanation of
   facts retrieved by deterministic Python tools.
4. When GROQ_API_KEY is not configured or an API error occurs, `generate_text`
   returns `LLM_UNAVAILABLE`, seamlessly falling back to deterministic Python formatters.
5. Numeric claims from the LLM are subsequently validated by Guardrail Layer 5
   before anything is returned to the user.
"""

import os
from typing import Optional

LLM_UNAVAILABLE = "__LLM_UNAVAILABLE__"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqFinanceClient:
    """
    Groq client wrapper for financial reasoning, QA synthesis, and explanation.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self.client = None

        if self.api_key:
            try:
                from groq import Groq

                self.client = Groq(api_key=self.api_key)
            except Exception as e:
                # Log without crashing; fallback to deterministic path
                print(f"Warning: Failed to initialize Groq Client: {e}")

    @property
    def is_available(self) -> bool:
        return self.client is not None and bool(self.api_key)

    @property
    def provider_name(self) -> str:
        return "Groq"

    @property
    def model_name(self) -> str:
        return self.model

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> str:
        """
        Call Groq with the evidence-grounded prompt.

        Returns LLM_UNAVAILABLE when Groq is unconfigured or unavailable.
        Callers fall back to the deterministic Python formatter.
        """
        if not self.is_available:
            return LLM_UNAVAILABLE

        system_msg = (
            system_instruction
            or (
                "You are the AI Finance Controller Copilot for Razorpay AI Buildathon 2026. "
                "Answer financial reconciliation questions concisely and accurately using ONLY "
                "the provided evidence. Never invent financial numbers or transactions."
            )
        )

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if chat_completion and chat_completion.choices:
                choice = chat_completion.choices[0]
                if choice.message and choice.message.content:
                    text = choice.message.content.strip()
                    if text:
                        return text
            return LLM_UNAVAILABLE
        except Exception as e:
            print(f"Groq API call failed; falling back to deterministic formatter: {e}")
            return LLM_UNAVAILABLE


# Singleton instance for the application
groq_client = GroqFinanceClient()
