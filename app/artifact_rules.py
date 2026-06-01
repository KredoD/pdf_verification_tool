from __future__ import annotations

"""Rules for mandatory verification artifacts.

This module is deliberately separated from generic entity extraction. The CTO can
change business rules here without touching OCR, parsers, report generation, or
web UI. The rules reflect the current VNIIMT primary-check scenario:

* every package must have a check/reference document, usually application or EGRUL;
* UPP packages require business license validation;
* OEM packages require the agreement between Russian manufacturer and foreign site;
* Russian manufacturer packages require a production-site ownership artifact:
  lease agreement, EGRN extract, or another ownership/usage-right document;
* addresses must be cross-checked everywhere, because an address mismatch is one
  of the most important primary-review risks.
"""

from dataclasses import asdict, dataclass
from typing import Iterable

from app.models import DocumentReadResult
from app.utils import normalize_for_compare

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - fallback for minimal environments
    fuzz = None


ROLE_LABELS = {
    "REFERENCE_EGRUL_OR_MASTER": "Проверочный документ / ЕГРЮЛ / master",
    "REGISTRATION_APPLICATION": "Заявление",
    "BUSINESS_LICENSE": "Бизнес-лицензия",
    "UPP": "УПП / уполномоченный представитель",
    "OEM_SITE": "OEM-площадка / контрактная площадка",
    "OEM_AGREEMENT": "Договор РФ производитель - иностранная площадка",
    "RF_MANUFACTURER": "РФ-производитель",
    "LEASE_AGREEMENT": "Договор аренды производства",
    "EGRN_EXTRACT": "ЕГРН / подтверждение собственности",
    "OWNERSHIP_DOC": "Документ о праве собственности / пользования помещением",
    "PRODUCTION_SITE_DOC": "Документ производственной площадки",
    "TECHNICAL_DOCUMENT": "Технический документ",
    "OTHER_DOCUMENT": "Прочий документ",
}


@dataclass
class ArtifactRequirement:
    """One business-rule requirement shown to the employee in the report."""

    code: str
    title: str
    status: str
    found_files: list[str]
    expected: str
    comment: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class AddressConsistencyRow:
    """Address comparison pair for mandatory address cross-check."""

    left_file: str
    left_address: str
    right_file: str
    right_address: str
    score: int
    status: str
    comment: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _has_role(documents: Iterable[DocumentReadResult], *roles: str) -> list[str]:
    role_set = set(roles)
    return [d.filename for d in documents if d.role in role_set]


def _any_filename_contains(documents: Iterable[DocumentReadResult], *needles: str) -> list[str]:
    out: list[str] = []
    lower_needles = [n.lower() for n in needles]
    for d in documents:
        name = d.filename.lower()
        text_head = d.text[:8000].lower()
        if any(n in name or n in text_head for n in lower_needles):
            out.append(d.filename)
    return out


def evaluate_artifact_requirements(documents: list[DocumentReadResult], reference_file: str) -> list[ArtifactRequirement]:
    """Evaluate mandatory document-package artifacts.

    The function does not block generation. It gives the VNIIMT employee a clear
    checklist: what was found, what is missing, and why it matters.
    """

    requirements: list[ArtifactRequirement] = []

    ref_found = [reference_file] if reference_file else []
    application_found = _has_role(documents, "REGISTRATION_APPLICATION")
    if not application_found:
        application_found = _any_filename_contains(documents, "заявление", "registration application")

    requirements.append(
        ArtifactRequirement(
            code="reference_or_application",
            title="Проверочный документ: заявление / ЕГРЮЛ / master-документ",
            status="found" if (ref_found or application_found) else "missing",
            found_files=ref_found or application_found,
            expected="Должен быть документ, который считается источником правильных реквизитов: заявление, ЕГРЮЛ или иной master-документ.",
            comment="По нему сверяются ИНН, ОГРН, организации, адреса, класс риска, НКМИ и иные реквизиты.",
        )
    )

    upp_found = _has_role(documents, "UPP")
    business_license_found = _has_role(documents, "BUSINESS_LICENSE")
    if upp_found:
        requirements.append(
            ArtifactRequirement(
                code="upp_business_license",
                title="Если есть УПП — нужна бизнес-лицензия / разрешительный документ",
                status="found" if business_license_found else "missing",
                found_files=business_license_found,
                expected="Для пакета с УПП должен быть проверочный артефакт: бизнес-лицензия или иной разрешительный документ.",
                comment="Скрипт должен сверить данные УПП с лицензией: организации, ИНН/ОГРН, адреса, реквизиты лицензии.",
            )
        )

    oem_found = _has_role(documents, "OEM_SITE")
    oem_agreement_found = _has_role(documents, "OEM_AGREEMENT")
    if not oem_agreement_found:
        oem_agreement_found = _any_filename_contains(
            documents,
            "oem contract",
            "oem agreement",
            "соглашение_oem",
            "договор oem",
            "договор между",
            "контракт",
        )
    if oem_found or oem_agreement_found:
        requirements.append(
            ArtifactRequirement(
                code="oem_agreement",
                title="Если OEM — нужен договор между отечественным производителем и иностранной площадкой",
                status="found" if oem_agreement_found else "missing",
                found_files=oem_agreement_found,
                expected="Для OEM-пакета обязателен договор/соглашение между РФ-производителем и иностранной производственной площадкой.",
                comment="В договоре проверяются стороны, адрес иностранной площадки, адрес РФ-производителя и связь с заявлением/ЕГРЮЛ.",
            )
        )

    rf_manufacturer_found = _has_role(documents, "RF_MANUFACTURER")
    if not rf_manufacturer_found:
        rf_manufacturer_found = _any_filename_contains(documents, "российский производитель", "рф производитель", "отечественный производитель")
    production_rights_found = _has_role(documents, "LEASE_AGREEMENT", "EGRN_EXTRACT", "OWNERSHIP_DOC", "PRODUCTION_SITE_DOC")
    if not production_rights_found:
        production_rights_found = _any_filename_contains(
            documents,
            "договор аренды",
            "егрн",
            "собственност",
            "право пользования",
            "производственное помещение",
            "производственная площадка",
        )
    if rf_manufacturer_found:
        requirements.append(
            ArtifactRequirement(
                code="rf_manufacturer_site_rights",
                title="Если РФ-производитель — нужен документ на производственную площадку",
                status="found" if production_rights_found else "missing",
                found_files=production_rights_found,
                expected="Если производство в аренде — договор аренды. Если в собственности — ЕГРН или документ о праве собственности/пользования.",
                comment="Главная сверка: адрес производства из заявления/ЕГРЮЛ должен совпадать с адресом в договоре аренды, ЕГРН или документе собственности.",
            )
        )

    # Address requirement is always present because it applies to every scenario.
    address_docs = [d.filename for d in documents if d.facts.get("address")]
    requirements.append(
        ArtifactRequirement(
            code="address_cross_check",
            title="Обязательная сверка адресов во всех документах",
            status="found" if len(address_docs) >= 2 else "needs_review",
            found_files=address_docs,
            expected="Адреса должны быть извлечены минимум из двух документов: эталона и проверяемого артефакта.",
            comment="Если адреса отличаются, отчет показывает расхождение и источник каждого адреса.",
        )
    )

    return requirements


def _addr_similarity(a: str, b: str) -> int:
    aa, bb = normalize_for_compare(a), normalize_for_compare(b)
    if not aa or not bb:
        return 0
    if aa == bb:
        return 100
    if fuzz is not None:
        return int(fuzz.token_set_ratio(aa, bb))
    from difflib import SequenceMatcher

    return int(SequenceMatcher(None, aa, bb).ratio() * 100)


def evaluate_address_consistency(documents: list[DocumentReadResult], reference_file: str, threshold: int = 85) -> list[AddressConsistencyRow]:
    """Compare every extracted address with the reference addresses."""

    reference = next((d for d in documents if d.filename == reference_file), None)
    if reference is None or not reference.facts.get("address"):
        return []

    rows: list[AddressConsistencyRow] = []
    for doc in documents:
        if doc.filename == reference_file:
            continue
        for item in doc.facts.get("address", []):
            best_ref = None
            best_score = 0
            for ref in reference.facts.get("address", []):
                score = _addr_similarity(item.value, ref.value)
                if score > best_score:
                    best_ref = ref
                    best_score = score
            if best_ref:
                status = "correct" if best_score >= threshold else "mismatch"
                rows.append(
                    AddressConsistencyRow(
                        left_file=doc.filename,
                        left_address=item.value,
                        right_file=reference.filename,
                        right_address=best_ref.value,
                        score=best_score,
                        status=status,
                        comment=(
                            "Адрес совпадает с эталоном."
                            if status == "correct"
                            else "Адрес отличается от эталона: требуется ручная проверка адреса производства/площадки."
                        ),
                    )
                )
    return rows
