#!/usr/bin/env python3
"""Run extraction, reconcile, income statement, and HTML report in order."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(args: list[str]) -> None:
    print("+ " + " ".join(args), flush=True)
    subprocess.check_call(args, cwd=str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chain hw1 scripts from the document pack to income_statement.html"
    )
    parser.add_argument(
        "--docs-dir",
        default="output/hw1_spoke_and_wrench",
        help="Source PDFs and emails",
    )
    parser.add_argument(
        "--json-dir",
        default="output",
        help="Directory for JSON extracts",
    )
    parser.add_argument(
        "--out-dir",
        default="output",
        help="Directory for JSON and HTML outputs",
    )
    ns = parser.parse_args()
    py = sys.executable
    out_dir = Path(ns.out_dir)
    html_path = str(out_dir / "income_statement.html")

    run(
        [
            py,
            "read_receipts.py",
            "--docs-dir",
            ns.docs_dir,
            "--out-dir",
            ns.out_dir,
        ]
    )
    run(
        [
            py,
            "read_bank.py",
            "--docs-dir",
            ns.docs_dir,
            "--out-dir",
            ns.out_dir,
        ]
    )
    run(
        [
            py,
            "read_card.py",
            "--docs-dir",
            ns.docs_dir,
            "--out-dir",
            ns.out_dir,
        ]
    )
    run(
        [
            py,
            "reconcile.py",
            "--docs-dir",
            ns.docs_dir,
            "--json-dir",
            ns.json_dir,
            "--output-dir",
            ns.out_dir,
        ]
    )
    run(
        [
            py,
            "income_statement.py",
            "--json-dir",
            ns.json_dir,
            "--out-dir",
            ns.out_dir,
        ]
    )
    run(
        [
            py,
            "report.py",
            "--json-dir",
            ns.json_dir,
            "--out",
            html_path,
        ]
    )
    print("done")


if __name__ == "__main__":
    main()
