"""
Unit tests for Groq LLM Client.
Verifies:
1. Provider is Groq.
2. Default model is llama-3.3-70b-versatile (configurable via GROQ_MODEL).
3. Without GROQ_API_KEY, is_available is False and generate_text returns LLM_UNAVAILABLE.
4. Client gracefully handles missing configuration without crashing.
"""

import os
import pytest
from model.agents.groq_client import GroqFinanceClient, LLM_UNAVAILABLE, DEFAULT_GROQ_MODEL


def test_groq_client_defaults(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    client = GroqFinanceClient(api_key=None, model=None)
    assert client.provider_name == "Groq"
    assert client.model_name == DEFAULT_GROQ_MODEL
    # Without an API key, it should not claim to be available
    assert client.is_available is False


def test_groq_client_custom_model():
    client = GroqFinanceClient(api_key=None, model="llama-3.1-8b-instant")
    assert client.provider_name == "Groq"
    assert client.model_name == "llama-3.1-8b-instant"


def test_groq_client_fallback_when_unconfigured():
    client = GroqFinanceClient(api_key=None)
    result = client.generate_text("What is the balance of TX_001?")
    # Must return explicit sentinel so caller falls back to deterministic formatter
    assert result == LLM_UNAVAILABLE


def test_groq_client_with_dummy_key(monkeypatch):
    """Verify initialization when key is provided via env."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy_key_12345")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    client = GroqFinanceClient()
    assert client.is_available is True
    assert client.model_name == "llama-3.3-70b-versatile"
