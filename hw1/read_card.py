#!/usr/bin/env python3
"""Extract structured rows from the January credit card statement using an LLM."""

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

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    sys.exit("Missing dependency pypdf. Install with: pip install pypdf")

HW1_ROOT = Path(__file__).resolve().parent
DEFAULT_PROMPT = HW1_ROOT / "prompts" / "card_extract.md"
ENV_FILES = (HW1_ROOT / ".env",)
CARD_BASENAME = "credit_card_jan2026.pdf"

ROW_FIELDS = (
    "date",
    "merchant",
    "amount_usd",
    "classification",
    "expense_category",
)


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract credit card charges into credit_card_transactions.json"
    )
    parser.add_argument("--docs-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def pdf_basename(path: Path) -> str:
    return path.name.replace("\\", "/").split("/")[-1]


def find_card_statement(docs_dir: Path) -> Path:
    if not docs_dir.is_dir():
        sys.exit(f"docs dir not found: {docs_dir}")
    matches = [
        p
        for p in docs_dir.rglob("*")
        if p.is_file() and pdf_basename(p).lower() == CARD_BASENAME
    ]
    if not matches:
        sys.exit(f"Could not find {CARD_BASENAME} under {docs_dir}")
    return sorted(matches)[0]


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def llm_chat(prompt: str) -> str:
    portkey_key = os.environ.get("PORTKEY_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
    messages = [
        {
            "role": "system",
            "content": (
                "You extract structured credit-card charges. "
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
        except Exception:
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
        with urllib.request.urlopen(request, timeout=120, context=ssl_context()) as response:
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


def parse_transactions(raw: str) -> list:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fenced:
        text = fenced.group(1)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        sys.exit(f"LLM did not return JSON: {exc}\n{raw}")

    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, dict):
        rows = parsed.get("transactions") or parsed.get("rows") or parsed.get("charges")
        if not isinstance(rows, list):
            sys.exit("LLM JSON object did not contain a transactions array")
    else:
        sys.exit("LLM JSON was not an object or array")
    return rows


def normalize_row(row: dict) -> dict:
    if not isinstance(row, dict):
        sys.exit("LLM returned a non-object transaction row")
    out = {}
    for field in ROW_FIELDS:
        out[field] = row.get(field)

    if out["amount_usd"] is not None:
        try:
            out["amount_usd"] = abs(float(out["amount_usd"]))
        except (TypeError, ValueError):
            sys.exit(f"Invalid amount_usd on row: {row}")

    classification = (out.get("classification") or "").lower()
    if classification in ("business", "personal"):
        out["classification"] = classification
    if out["classification"] == "personal" or out.get("expense_category") in ("", None):
        if out["classification"] == "personal":
            out["expense_category"] = None
    return out


def main() -> None:
    load_dotenv_files()
    args = parse_args()
    if not DEFAULT_PROMPT.is_file():
        sys.exit(f"Prompt file not found: {DEFAULT_PROMPT}")

    path = find_card_statement(args.docs_dir)
    source_file = pdf_basename(path)
    text = extract_pdf_text(path)
    if not text:
        sys.exit(f"No text extracted from {source_file}")

    template = DEFAULT_PROMPT.read_text(encoding="utf-8")
    prompt = template.replace("{source_file}", source_file).replace(
        "{statement_text}", text
    )
    raw = llm_chat(prompt)
    rows = [normalize_row(row) for row in parse_transactions(raw)]
    print(f"extracted {len(rows)} charges from {source_file}", file=sys.stderr)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / "credit_card_transactions.json"
    out_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
