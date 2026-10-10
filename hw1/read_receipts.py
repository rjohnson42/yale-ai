#!/usr/bin/env python3
"""Extract one JSON row per purchase-receipt PDF using an LLM."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    sys.exit("Missing dependency pypdf. Install with: pip install pypdf")

HW1_ROOT = Path(__file__).resolve().parent
DEFAULT_PROMPT = HW1_ROOT / "prompts" / "receipts_extract.md"
ENV_FILES = (HW1_ROOT / ".env",)

REQUIRED_FIELDS = (
    "vendor",
    "date",
    "description",
    "amount_usd",
    "category",
    "source_file",
    "fields_not_found",
)

RECEIPT_NAME_RE = re.compile(
    r"(^|[\\/])(receipt_[^\\/]+\.pdf|ebay_[^\\/]+\.pdf)$",
    re.IGNORECASE,
)


def load_dotenv_files() -> None:
    """Load KEY=VALUE pairs from local .env files without overriding the process env."""
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract purchase receipts from PDFs into receipts.json"
    )
    parser.add_argument(
        "--docs-dir",
        required=True,
        type=Path,
        help="Directory containing source PDFs (and nested packs)",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="Directory to write receipts.json",
    )
    return parser.parse_args()


def pdf_basename(path: Path) -> str:
    """Filename only, even when the on-disk name is like 'pdfs\\receipt_x.pdf'."""
    return path.name.replace("\\", "/").split("/")[-1]


def is_purchase_receipt(path: Path) -> bool:
    if path.suffix.lower() != ".pdf":
        return False
    return bool(RECEIPT_NAME_RE.search(path.name))


def iter_receipt_pdfs(docs_dir: Path) -> list[Path]:
    if not docs_dir.is_dir():
        sys.exit(f"docs dir not found: {docs_dir}")
    found = [p for p in docs_dir.rglob("*") if p.is_file() and is_purchase_receipt(p)]
    found.sort(key=lambda p: pdf_basename(p).lower())
    return found


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def fill_prompt(template: str, source_file: str, receipt_text: str) -> str:
    return template.replace("{source_file}", source_file).replace(
        "{receipt_text}", receipt_text
    )


def llm_chat(prompt: str) -> str:
    """Call Portkey (Yale gateway) or an OpenAI-compatible Chat Completions API."""
    portkey_key = os.environ.get("PORTKEY_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
    messages = [
        {
            "role": "system",
            "content": (
                "You extract structured accounting data from receipts. "
                "Reply with a single JSON object only."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    if portkey_key:
        try:
            from portkey_ai import Portkey
        except ImportError:
            sys.exit("Missing dependency portkey-ai. Install with: pip install portkey-ai")
        client = Portkey(api_key=portkey_key)
        kwargs = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        try:
            payload = client.chat.completions.create(**kwargs)
        except Exception as exc:
            kwargs.pop("response_format", None)
            try:
                payload = client.chat.completions.create(**kwargs)
            except Exception as exc2:
                sys.exit(f"LLM request failed: {exc2}")
        try:
            return payload.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            sys.exit(f"Unexpected LLM response: {exc}\n{payload}")

    if not openai_key:
        sys.exit(
            "No LLM credentials found. Set OPENAI_API_KEY (or LLM_API_KEY) "
            "or PORTKEY_API_KEY."
        )

    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    url = base.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_key}",
        "User-Agent": "spoke-wrench-hw1/1.0",
    }
    body = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90, context=ssl_context()) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        sys.exit(f"LLM HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        sys.exit(f"LLM request failed: {exc}")

    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        sys.exit(f"Unexpected LLM response: {exc}\n{payload}")


def parse_row(raw: str, source_file: str) -> dict:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        row = json.loads(text)
    except json.JSONDecodeError as exc:
        sys.exit(f"LLM did not return JSON for {source_file}: {exc}\n{raw}")
    if not isinstance(row, dict):
        sys.exit(f"LLM JSON for {source_file} was not an object")

    row["source_file"] = source_file
    missing = row.get("fields_not_found")
    if not isinstance(missing, list):
        missing = []

    for field in REQUIRED_FIELDS:
        if field == "fields_not_found":
            continue
        if field == "source_file":
            continue
        value = row.get(field)
        empty = value is None or value == "" or value == []
        if empty and field not in missing:
            missing.append(field)
        if field == "amount_usd" and value is not None:
            try:
                row["amount_usd"] = float(value)
            except (TypeError, ValueError):
                if field not in missing:
                    missing.append(field)

    row["fields_not_found"] = missing
    return {key: row.get(key) for key in REQUIRED_FIELDS}


def main() -> None:
    load_dotenv_files()
    args = parse_args()
    if not DEFAULT_PROMPT.is_file():
        sys.exit(f"Prompt file not found: {DEFAULT_PROMPT}")
    template = DEFAULT_PROMPT.read_text(encoding="utf-8")

    pdfs = iter_receipt_pdfs(args.docs_dir)
    if not pdfs:
        sys.exit(f"No purchase-receipt PDFs found under {args.docs_dir}")

    rows = []
    for path in pdfs:
        source_file = pdf_basename(path)
        text = extract_pdf_text(path)
        if not text:
            rows.append(
                {
                    "vendor": None,
                    "date": None,
                    "description": None,
                    "amount_usd": None,
                    "category": None,
                    "source_file": source_file,
                    "fields_not_found": [
                        "vendor",
                        "date",
                        "description",
                        "amount_usd",
                        "category",
                    ],
                }
            )
            continue
        prompt = fill_prompt(template, source_file, text)
        raw = llm_chat(prompt)
        rows.append(parse_row(raw, source_file))
        print(f"extracted {source_file}", file=sys.stderr)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "receipts.json"
    out_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
