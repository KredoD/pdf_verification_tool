from pathlib import Path

from app.extractors import read_any_document
from app.report_builder import html_report, write_docx_report, write_json_report
from app.verification import verify_package


def test_smoke(tmp_path: Path):
    ref = tmp_path / "egrul_reference.txt"
    doc = tmp_path / "business_license.txt"
    ref.write_text('ООО "МЕДТЕСТ"\nИНН 7701234567\nОГРН 1027700123456\nАдрес: г. Москва, ул. Ленина, д. 1\nКласс риска 2а\nКод вида НКМИ 120550\n', encoding="utf-8")
    doc.write_text('Бизнес лицензия для ООО "МЕДТЕСТ"\nИНН: 7701234567\nОГРН: 1027700123456\nАдрес: город Москва, улица Ленина, дом 1\nЛицензия № Л041-01137-77/00300000\n', encoding="utf-8")

    docs = [read_any_document(ref, role_hint="REFERENCE_EGRUL_OR_MASTER"), read_any_document(doc)]
    report = verify_package(project_name="smoke", documents=docs, reference_filename=docs[0].filename, project_id="smoke")
    assert report.rows
    assert any(r.fact_type == "inn" and r.status == "correct" for r in report.rows)

    write_json_report(report, tmp_path / "report.json")
    write_docx_report(report, tmp_path / "report.docx")
    html = html_report(report)
    assert "Отчет первичной проверки" in html
    assert (tmp_path / "report.docx").exists()
