#!/usr/bin/env python3
"""CLI runner for technical verification without web UI.

Example:
python scripts/run_local_check.py \
  --project "Тест ВНИИМТ" \
  --reference ./data/egrul.pdf \
  --documents ./data/business_license.pdf ./data/upp.docx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.extractors import read_any_document
from app.report_builder import html_report, write_docx_report, write_json_report
from app.verification import verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", "--project-name", dest="project", default="Первичная проверка ВНИИМТ")
    parser.add_argument("--reference", required=True, help="Reference/master document: EGRUL, application, UPP, etc.")
    parser.add_argument("--documents", nargs="+", required=True, help="Documents to verify against reference")
    parser.add_argument("--out", default="output/local_check", help="Output directory")
    args = parser.parse_args()

    project_id = uuid4().hex[:12]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    documents = [read_any_document(Path(args.reference), role_hint="REFERENCE_EGRUL_OR_MASTER")]
    for item in args.documents:
        documents.append(read_any_document(Path(item)))

    report = verify_package(project_name=args.project, documents=documents, reference_filename=documents[0].filename, project_id=project_id)
    write_json_report(report, out_dir / "report.json")
    write_docx_report(report, out_dir / "report.docx")
    (out_dir / "report.html").write_text(html_report(report), encoding="utf-8")
    print(f"OK: {out_dir / 'report.html'}")
    print(report.summary.get("human_status"))


if __name__ == "__main__":
    main()
