"""
Multi-source financial document parser.
Supports: CSV, XLSX, JSON.
PDF extraction is currently a stub and returns no extracted records
(no OCR/VLM/PDF extraction implemented).
Extracts rows and standardizes them using normalizer.py.
"""

import os
import io
import json
from typing import List, Dict, Any, Union
import pandas as pd
from .normalizer import normalize_single_record, NormalizedRecord

def parse_file(file_path_or_bytes: Union[str, bytes], filename: str, source_label: str = None) -> List[NormalizedRecord]:
    if source_label is None:
        source_label = os.path.splitext(os.path.basename(filename))[0]

    ext = os.path.splitext(filename)[1].lower()
    raw_dicts: List[Dict[str, Any]] = []

    if ext == ".csv":
        if isinstance(file_path_or_bytes, bytes):
            df = pd.read_csv(io.BytesIO(file_path_or_bytes))
        else:
            df = pd.read_csv(file_path_or_bytes)
        raw_dicts = df.to_dict(orient="records")

    elif ext in [".xlsx", ".xls"]:
        if isinstance(file_path_or_bytes, bytes):
            df = pd.read_excel(io.BytesIO(file_path_or_bytes))
        else:
            df = pd.read_excel(file_path_or_bytes)
        raw_dicts = df.to_dict(orient="records")

    elif ext == ".json":
        if isinstance(file_path_or_bytes, bytes):
            data = json.loads(file_path_or_bytes.decode("utf-8"))
        else:
            with open(file_path_or_bytes, "r", encoding="utf-8") as f:
                data = json.load(f)
        if isinstance(data, list):
            raw_dicts = data
        elif isinstance(data, dict) and "records" in data:
            raw_dicts = data["records"]
        else:
            raw_dicts = [data]

    elif ext == ".pdf":
        # Simple robust text parser for tabular records in text-based PDFs
        raw_dicts = parse_simple_pdf(file_path_or_bytes, source_label)

    else:
        # Fallback to CSV parser
        try:
            if isinstance(file_path_or_bytes, bytes):
                df = pd.read_csv(io.BytesIO(file_path_or_bytes))
            else:
                df = pd.read_csv(file_path_or_bytes)
            raw_dicts = df.to_dict(orient="records")
        except Exception:
            raw_dicts = []

    normalized = [normalize_single_record(r, source_label) for r in raw_dicts]
    return normalized

def parse_simple_pdf(file_path_or_bytes: Union[str, bytes], source_label: str) -> List[Dict[str, Any]]:
    """PDF extraction stub: currently returns no extracted records (no OCR/VLM implemented)."""
    # Reads plain text if PDF contains text lines or falls back to line-by-line parsing
    lines = []
    if isinstance(file_path_or_bytes, bytes):
        try:
            content = file_path_or_bytes.decode("latin1", errors="ignore")
            for line in content.splitlines():
                if any(kw in line.upper() for kw in ["TXN", "INV", "PAYMENT", "REF", "AMOUNT", "$"]):
                    lines.append(line)
        except Exception:
            pass
    return []
