from pathlib import Path

from app.extractors import read_any_document
from app.verification import verify_package


def test_oem_and_rf_artifacts_are_reported():
    root = Path(__file__).resolve().parents[1]
    docs = [
        read_any_document(root / "sample_data" / "registration_application.txt", role_hint="REFERENCE_EGRUL_OR_MASTER"),
        read_any_document(root / "sample_data" / "oem_contract.txt"),
        read_any_document(root / "sample_data" / "lease_agreement.txt"),
    ]
    report = verify_package(
        project_name="artifact test",
        documents=docs,
        reference_filename="registration_application.txt",
    )
    codes = {item.code: item.status for item in report.artifact_requirements}
    assert "reference_or_application" in codes
    assert "address_cross_check" in codes
    assert report.summary["documents_total"] == 3
    assert report.rows
