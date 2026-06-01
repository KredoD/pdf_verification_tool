from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal

FactType = Literal[
    "inn",
    "ogrn",
    "phone",
    "email",
    "organization",
    "risk_class",
    "nkmi_code",
    "license",
    "address",
]

Status = Literal[
    "correct",
    "possible_match",
    "mismatch",
    "missing_in_reference",
    "missing_in_document",
    "not_checked",
]


@dataclass
class EvidenceItem:
    """One extracted fact with proof trail.

    The key requirement for VNIIMT staff is explainability: every fact must show
    where the script found it. This object is used in JSON, HTML, and DOCX
    reports.
    """

    fact_type: str
    value: str
    normalized_value: str
    source_file: str
    location: str
    quote: str
    extraction_method: str
    confidence: int = 100

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentReadResult:
    filename: str
    role: str
    text: str
    stats: dict[str, Any]
    facts: dict[str, list[EvidenceItem]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["facts"] = {k: [x.to_dict() for x in v] for k, v in self.facts.items()}
        # Avoid huge JSON reports. Full text is not needed for the employee.
        data["text_preview"] = self.text[:3000]
        data.pop("text", None)
        return data


@dataclass
class VerificationRow:
    fact_type: str
    checked_file: str
    checked_value: str
    reference_value: str
    status: str
    score: int
    checked_evidence: EvidenceItem | None
    reference_evidence: EvidenceItem | None
    comment: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checked_evidence"] = self.checked_evidence.to_dict() if self.checked_evidence else None
        data["reference_evidence"] = self.reference_evidence.to_dict() if self.reference_evidence else None
        return data


@dataclass
class CheckReport:
    project_id: str
    project_name: str
    reference_file: str
    generated_at: str
    documents: list[DocumentReadResult]
    rows: list[VerificationRow]
    summary: dict[str, Any]
    artifact_requirements: list[Any] = field(default_factory=list)
    address_consistency: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "reference_file": self.reference_file,
            "generated_at": self.generated_at,
            "documents": [d.to_dict() for d in self.documents],
            "verification_rows": [r.to_dict() for r in self.rows],
            "summary": self.summary,
            "artifact_requirements": [x.to_dict() if hasattr(x, "to_dict") else x for x in self.artifact_requirements],
            "address_consistency": [x.to_dict() if hasattr(x, "to_dict") else x for x in self.address_consistency],
        }
