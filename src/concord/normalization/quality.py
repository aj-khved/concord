"""Data-quality checks run against canonical records after mapping (FR11).

tax_id is deliberately NOT required — the messiness spec makes it legitimately
absent in ~15% of Source B records, so flagging every missing tax_id would
just be noise a reviewer learns to ignore.
"""

from dataclasses import dataclass, field

from concord.normalization.schema import CanonicalVendorRecord

REQUIRED_FIELDS = ("legal_name", "city", "category")


def check_record(record: CanonicalVendorRecord) -> list[str]:
    issues = []

    for field_name in REQUIRED_FIELDS:
        if not getattr(record, field_name):
            issues.append(f"missing_{field_name}")

    if record.postal_code and not _is_plausible_postal_code(record.postal_code):
        issues.append("invalid_postal_code")

    if record.phone and len(record.phone) != 10:
        issues.append("invalid_phone_length")

    if record.tax_id and len(record.tax_id) != 9:
        issues.append("invalid_tax_id_length")

    return issues


def _is_plausible_postal_code(postal_code: str) -> bool:
    digits = postal_code.replace("-", "")
    return digits.isdigit() and len(digits) in (5, 9)


@dataclass
class QualityReport:
    records_checked: int = 0
    records_passed: int = 0
    records_failed: int = 0
    issue_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "records_checked": self.records_checked,
            "records_passed": self.records_passed,
            "records_failed": self.records_failed,
            "issue_counts": self.issue_counts,
        }


def run_quality_checks(records: list[CanonicalVendorRecord]) -> QualityReport:
    report = QualityReport(records_checked=len(records))
    for record in records:
        issues = check_record(record)
        if issues:
            report.records_failed += 1
            for issue in issues:
                report.issue_counts[issue] = report.issue_counts.get(issue, 0) + 1
        else:
            report.records_passed += 1
    return report
