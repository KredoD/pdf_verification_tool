from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None

from app.config import settings
from app.models import CheckReport, DocumentReadResult, EvidenceItem, VerificationRow
from app.artifact_rules import evaluate_address_consistency, evaluate_artifact_requirements
from app.utils import normalize_digits, normalize_for_compare

FACT_LABELS = {
    "inn": "ИНН",
    "ogrn": "ОГРН",
    "phone": "Телефон",
    "email": "Email",
    "organization": "Организация",
    "risk_class": "Класс риска",
    "nkmi_code": "НКМИ / код вида",
    "license": "Лицензия / разрешение",
    "address": "Адресная строка",
}

FACTS_TO_COMPARE = ["inn", "ogrn", "organization", "risk_class", "nkmi_code", "license", "address", "phone", "email"]


def similarity(a: str, b: str, *, digits: bool = False) -> int:
    """Exact/fuzzy similarity score for verification."""
    if digits:
        aa, bb = normalize_digits(a), normalize_digits(b)
    else:
        aa, bb = normalize_for_compare(a), normalize_for_compare(b)
    if not aa or not bb:
        return 0
    if aa == bb:
        return 100
    if digits:
        return 0
    if fuzz is not None:
        return int(fuzz.token_set_ratio(aa, bb))
    from difflib import SequenceMatcher
    return int(SequenceMatcher(None, aa, bb).ratio() * 100)


def _best_reference_match(fact: EvidenceItem, references: list[EvidenceItem]) -> tuple[EvidenceItem | None, int]:
    best_item = None
    best_score = 0
    for ref in references:
        score = similarity(fact.value, ref.value, digits=fact.fact_type in {"inn", "ogrn", "phone", "nkmi_code"})
        if score > best_score:
            best_item, best_score = ref, score
    return best_item, best_score


def _status_and_comment(fact_type: str, score: int, ref_exists: bool) -> tuple[str, str]:
    label = FACT_LABELS.get(fact_type, fact_type)
    if not ref_exists:
        return "missing_in_reference", f"{label}: значение найдено в проверяемом документе, но в эталоне такого значения нет. Требуется ручная оценка."
    if score == 100:
        return "correct", f"{label}: полное совпадение с эталонным документом."
    if score >= settings.fuzzy_match_threshold:
        return "correct", f"{label}: корректно, совпадение с эталоном по fuzzy-сравнению ({score}%)."
    if score >= settings.possible_match_threshold:
        return "possible_match", f"{label}: частичное совпадение ({score}%). Нужно проверить вручную: возможны сокращения, OCR или разные формулировки."
    return "mismatch", f"{label}: расхождение с эталонным документом."


def choose_reference(documents: list[DocumentReadResult], explicit_reference_filename: str | None = None) -> DocumentReadResult:
    """Pick reference document.

    In the web UI reference is uploaded separately, so this is normally explicit.
    Fallback exists for CLI or batch runs.
    """
    if explicit_reference_filename:
        for doc in documents:
            if doc.filename == explicit_reference_filename:
                return doc

    priority = ["REFERENCE_EGRUL_OR_MASTER", "REGISTRATION_APPLICATION", "UPP", "BUSINESS_LICENSE"]
    for role in priority:
        for doc in documents:
            if doc.role == role:
                return doc
    return max(documents, key=lambda d: d.stats.get("total_text_chars", 0))


def verify_package(*, project_name: str, documents: list[DocumentReadResult], reference_filename: str | None = None, project_id: str | None = None) -> CheckReport:
    """Stage B: compare all documents against the reference and build report data."""
    if not documents:
        raise ValueError("No documents to verify")

    reference = choose_reference(documents, reference_filename)
    rows: list[VerificationRow] = []

    for doc in documents:
        if doc.filename == reference.filename:
            continue
        for fact_type in FACTS_TO_COMPARE:
            ref_items = reference.facts.get(fact_type, [])
            checked_items = doc.facts.get(fact_type, [])

            if not checked_items and ref_items:
                for ref in ref_items:
                    rows.append(
                        VerificationRow(
                            fact_type=fact_type,
                            checked_file=doc.filename,
                            checked_value="",
                            reference_value=ref.value,
                            status="missing_in_document",
                            score=0,
                            checked_evidence=None,
                            reference_evidence=ref,
                            comment=f"{FACT_LABELS.get(fact_type, fact_type)}: значение есть в эталоне, но не найдено в проверяемом документе.",
                        )
                    )
                continue

            for item in checked_items:
                ref, score = _best_reference_match(item, ref_items)
                status, comment = _status_and_comment(fact_type, score, bool(ref_items))
                rows.append(
                    VerificationRow(
                        fact_type=fact_type,
                        checked_file=doc.filename,
                        checked_value=item.value,
                        reference_value=ref.value if ref else "",
                        status=status,
                        score=score,
                        checked_evidence=item,
                        reference_evidence=ref,
                        comment=comment,
                    )
                )

    artifact_requirements = evaluate_artifact_requirements(documents, reference.filename)
    address_consistency = evaluate_address_consistency(documents, reference.filename, threshold=settings.fuzzy_match_threshold)
    summary = build_summary(documents, rows, reference.filename)
    summary["artifact_requirements_status"] = {req.code: req.status for req in artifact_requirements}
    summary["address_consistency_rows"] = len(address_consistency)
    return CheckReport(
        project_id=project_id or uuid4().hex[:12],
        project_name=project_name,
        reference_file=reference.filename,
        generated_at=datetime.now(timezone.utc).isoformat(),
        documents=documents,
        rows=rows,
        summary=summary,
        artifact_requirements=artifact_requirements,
        address_consistency=address_consistency,
    )


def build_summary(documents: list[DocumentReadResult], rows: list[VerificationRow], reference_file: str) -> dict[str, object]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1

    extracted_counts = {
        doc.filename: {fact_type: len(items) for fact_type, items in doc.facts.items() if items}
        for doc in documents
    }
    return {
        "reference_file": reference_file,
        "documents_total": len(documents),
        "verification_rows_total": len(rows),
        "status_counts": counts,
        "extracted_counts_by_file": extracted_counts,
        "human_status": make_human_status(counts),
    }


def make_human_status(counts: dict[str, int]) -> str:
    mismatches = counts.get("mismatch", 0)
    missing = counts.get("missing_in_document", 0) + counts.get("missing_in_reference", 0)
    possible = counts.get("possible_match", 0)
    if mismatches:
        return f"Есть критические расхождения: {mismatches}. Требуется ручная проверка."
    if missing:
        return f"Есть отсутствующие значения: {missing}. Нужно уточнить пакет документов."
    if possible:
        return f"Есть частичные совпадения: {possible}. Нужна ручная валидация."
    return "Критических расхождений не найдено по извлеченным реквизитам."
