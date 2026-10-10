#!/usr/bin/env python3
"""Reconcile receipts, bank lines, card charges, and supporting documents."""

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
DEFAULT_PROMPT = HW1_ROOT / "prompts" / "reconcile.md"
ENV_FILES = (HW1_ROOT / ".env",)

JSON_FILES = (
    "receipts.json",
    "bank_transactions.json",
    "credit_card_transactions.json",
)

ROW_FIELDS = (
    "id",
    "sources",
    "amounts_seen",
    "included_in_income_statement",
    "amount_used_in_income_statment",
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
        description="Build reconciliation_log.json from extracts and source docs"
    )
    parser.add_argument("--docs-dir", required=True, type=Path)
    parser.add_argument(
        "--json-dir",
        required=True,
        type=Path,
        help="Directory containing receipts.json, bank_transactions.json, "
        "credit_card_transactions.json",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def pdf_basename(path: Path) -> str:
    return path.name.replace("\\", "/").split("/")[-1]


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def load_required_json(json_dir: Path) -> dict[str, str]:
    if not json_dir.is_dir():
        sys.exit(f"json dir not found: {json_dir}")
    loaded = {}
    for name in JSON_FILES:
        path = json_dir / name
        if not path.is_file():
            sys.exit(f"Missing {path}")
        loaded[name] = path.read_text(encoding="utf-8")
        json.loads(loaded[name])
    return loaded


def iter_source_docs(docs_dir: Path) -> list[Path]:
    if not docs_dir.is_dir():
        sys.exit(f"docs dir not found: {docs_dir}")
    found = []
    for path in docs_dir.rglob("*"):
        if not path.is_file():
            continue
        name = pdf_basename(path).lower()
        if name.endswith((".pdf", ".txt", ".md")):
            found.append(path)
    found.sort(key=lambda p: pdf_basename(p).lower())
    return found


def collect_document_text(docs_dir: Path) -> str:
    chunks = []
    for path in iter_source_docs(docs_dir):
        name = pdf_basename(path)
        suffix = path.suffix.lower()
        try:
            if suffix == ".pdf":
                body = extract_pdf_text(path)
            else:
                body = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            body = f"[could not read: {exc}]"
        chunks.append(f"### {name}\n\n```\n{body.strip()}\n```")
    if not chunks:
        sys.exit(f"No PDF/text documents found under {docs_dir}")
    return "\n\n".join(chunks)


def llm_chat(prompt: str) -> str:
    portkey_key = os.environ.get("PORTKEY_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
    messages = [
        {
            "role": "system",
            "content": (
                "You reconcile messy small-business books. "
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
        with urllib.request.urlopen(request, timeout=180, context=ssl_context()) as response:
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


def parse_items(raw: str) -> list:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fenced:
        text = fenced.group(1)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        sys.exit(f"LLM did not return JSON: {exc}\n{raw}")

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("items", "rows", "reconciliation", "log"):
            if isinstance(parsed.get(key), list):
                return parsed[key]
        sys.exit("LLM JSON object did not contain an items array")
    sys.exit("LLM JSON was not an object or array")


def normalize_row(row: dict) -> dict:
    if not isinstance(row, dict):
        sys.exit("LLM returned a non-object reconciliation row")
    out = {field: row.get(field) for field in ROW_FIELDS}
    out["resolution"] = row.get("resolution")

    if not out.get("id"):
        sys.exit(f"Row missing id: {row}")
    sources = out.get("sources")
    if isinstance(sources, str):
        out["sources"] = [sources]
    elif not isinstance(sources, list):
        out["sources"] = []

    amounts = out.get("amounts_seen")
    if not isinstance(amounts, dict):
        out["amounts_seen"] = {}
    else:
        cleaned = {}
        for key, value in amounts.items():
            try:
                cleaned[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        out["amounts_seen"] = cleaned

    flag = str(out.get("included_in_income_statement") or "").strip().lower()
    if flag in ("yes", "true", "y", "1"):
        out["included_in_income_statement"] = "yes"
    elif flag in ("no", "false", "n", "0"):
        out["included_in_income_statement"] = "no"
    else:
        sys.exit(f"Row {out['id']} has invalid included_in_income_statement")

    used = out.get("amount_used_in_income_statment")
    try:
        out["amount_used_in_income_statment"] = float(used)
    except (TypeError, ValueError):
        sys.exit(f"Row {out['id']} has invalid amount_used_in_income_statment")

    if out["included_in_income_statement"] == "no":
        out["amount_used_in_income_statment"] = 0.0

    return out


def main() -> None:
    load_dotenv_files()
    args = parse_args()
    if not DEFAULT_PROMPT.is_file():
        sys.exit(f"Prompt file not found: {DEFAULT_PROMPT}")

    extracts = load_required_json(args.json_dir)
    documents_text = collect_document_text(args.docs_dir)
    template = DEFAULT_PROMPT.read_text(encoding="utf-8")
    prompt = (
        template.replace("{receipts_json}", extracts["receipts.json"])
        .replace("{bank_json}", extracts["bank_transactions.json"])
        .replace("{card_json}", extracts["credit_card_transactions.json"])
        .replace("{documents_text}", documents_text)
    )

    raw = llm_chat(prompt)
    rows = [normalize_row(row) for row in parse_items(raw)]
    print(f"reconciled {len(rows)} items", file=sys.stderr)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / "reconciliation_log.json"
    out_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
