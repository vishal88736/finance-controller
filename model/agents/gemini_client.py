"""
Legacy / currently unused: Gemini Flash LLM Client for the QA Copilot.
The live QA path uses the Groq client only; this module is kept for
reference and is not imported by the runtime.

When GEMINI_API_KEY is configured, answers are synthesized by the LLM from
retrieved evidence ONLY. When the LLM is unavailable (offline/demo mode),
`generate_text` returns an explicit sentinel (LLM_UNAVAILABLE) and the caller
falls back to a deterministic Python formatter — never to fabricated content.

This client never fabricates financial numbers: it is a thin wrapper, and all
grounding is enforced by the QA graph (evidence prompt + numeric validation).
"""

import os
from typing import Optional

# Sentinel returned when the LLM cannot be used. Callers must handle it by
# producing a deterministic, evidence-only response.
LLM_UNAVAILABLE = "__LLM_UNAVAILABLE__"


class GeminiFinanceClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                from google import genai

                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"Warning: Failed to initialize Google GenAI Client: {e}")

    @property
    def is_available(self) -> bool:
        return self.client is not None

    def generate_text(
        self, prompt: str, system_instruction: Optional[str] = None
    ) -> str:
        """
        Call Gemini with the evidence-grounded prompt.

        Returns LLM_UNAVAILABLE when the model is not configured or the call
        fails — callers MUST then use their deterministic formatter instead of
        showing anything unverified.
        """
        if not self.client:
            return LLM_UNAVAILABLE

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={
                    "system_instruction": system_instruction
                    or "You are an expert AI Finance Controller. Answer strictly from the provided evidence; never invent numbers."
                },
            )
            if response and getattr(response, "text", None):
                text = response.text.strip()
                if text:
                    return text
            return LLM_UNAVAILABLE
        except Exception as e:
            print(f"Gemini API call failed; using deterministic formatter: {e}")
            return LLM_UNAVAILABLE


gemini_client = GeminiFinanceClient()
