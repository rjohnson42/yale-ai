#!/usr/bin/env python3
"""Extract structured lease fields from PDFs using Portkey (GPT-5.6-luna)."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / "data" / "pdfs"
OUTPUT_PATH = ROOT / "data" / "leases_test.json"
PROMPT_PATH = ROOT / "prompts" / "lease_extract.md"
ENV_FILES = (ROOT / ".env",)

SCHEMA_FIELDS = (
    "source_file",
    "landlord_name",
    "tenant_name",
    "address",
    "space_type",
    "rentable_sqft",
    "annual_base_rent",
    "rent_per_sqft",
    "lease_structure",
    "commencement_date",
    "expiration_date",
    "security_deposit",
    "permitted_use",
)

NUMERIC_FIELDS = (
    "rentable_sqft",
    "annual_base_rent",
    "rent_per_sqft",
    "security_deposit",
)


def load_dotenv_files() -> None:
    for path in ENV_FILES:
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key:
                os.environ[key] = value


def read_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def fill_prompt(template: str, source_file: str, lease_text: str) -> str:
    return template.replace("{source_file}", source_file).replace(
        "{lease_text}", lease_text
    )


def llm_chat(prompt: str) -> str:
    portkey_key = os.environ.get("PORTKEY_API_KEY")
    model = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
    if not portkey_key:
        sys.exit(
            "No Portkey key found. Set PORTKEY_API_KEY in lecture_one/.env "
            "(see .env.example)."
        )
    try:
        from portkey_ai import Portkey
    except ImportError:
        sys.exit("Missing dependency portkey-ai. Install with: pip install portkey-ai")

    client = Portkey(api_key=portkey_key)
    messages = [
        {
            "role": "system",
            "content": (
                "You extract structured commercial lease data. "
                "Reply with a single JSON object only."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    kwargs = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    try:
        payload = client.chat.completions.create(**kwargs)
    except Exception:
        kwargs.pop("response_format", None)
        try:
            payload = client.chat.completions.create(**kwargs)
        except Exception as exc:
            sys.exit(f"LLM request failed: {exc}")
    try:
        return payload.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        sys.exit(f"Unexpected LLM response: {exc}\n{payload}")


def parse_json_object(raw: str) -> dict:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        sys.exit(f"LLM did not return valid JSON: {exc}\n{raw}")
    if not isinstance(data, dict):
        sys.exit(f"LLM JSON was not an object:\n{raw}")
    return data


def coerce_number(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[\d,]+(?:\.\d+)?", str(value))
    if not match:
        return None
    return float(match.group(0).replace(",", ""))


def normalize_lease(raw: dict, source_file: str) -> dict:
    record = {field: raw.get(field) for field in SCHEMA_FIELDS}
    record["source_file"] = source_file
    for field in NUMERIC_FIELDS:
        record[field] = coerce_number(record[field])
    for field in SCHEMA_FIELDS:
        if field in NUMERIC_FIELDS:
            continue
        value = record[field]
        if isinstance(value, str):
            value = value.strip()
            record[field] = value or None
    return record


def extract_lease(path: Path, template: str) -> dict:
    text = read_pdf_text(path)
    if not text:
        sys.exit(f"No text extracted from {path.name}")
    prompt = fill_prompt(template, path.name, text)
    raw = parse_json_object(llm_chat(prompt))
    return normalize_lease(raw, path.name)


def main() -> None:
    load_dotenv_files()
    if not PROMPT_PATH.is_file():
        sys.exit(f"Prompt file not found: {PROMPT_PATH}")
    template = PROMPT_PATH.read_text(encoding="utf-8")
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs found in {PDF_DIR}")

    leases = []
    for path in pdfs:
        print(f"Extracting {path.name} via {os.environ.get('LLM_MODEL', 'gpt-5.6-luna')}...")
        leases.append(extract_lease(path, template))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(leases, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(leases)} leases to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
