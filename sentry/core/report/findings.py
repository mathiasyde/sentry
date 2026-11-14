"""core/report: finding store: de-duplication, evidence cap, ordering and risk scoring."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from core.report.rules.catalog import SEVERITY_ORDER, SEVERITY_SCORE
from core.report.values import compact


class FindingStore:
    def __init__(self) -> None:
        self.findings: dict[str, dict[str, Any]] = {}

    def add(
        self,
        rule_id: str,
        severity: str,
        title: str,
        description: str,
        recommendation: str,
        evidence: dict[str, Any],
        fingerprint: str | None = None,
    ) -> None:
        key = fingerprint or f"{rule_id}:{json.dumps(evidence, sort_keys=True, default=str)}"
        finding = self.findings.get(key)
        if finding is None:
            self.findings[key] = {
                "rule_id": rule_id,
                "severity": severity,
                "title": title,
                "description": description,
                "recommendation": recommendation,
                "evidence": [],
            }
            finding = self.findings[key]

        if len(finding["evidence"]) < 20:
            finding["evidence"].append(compact(evidence))

    def sorted_findings(self) -> list[dict[str, Any]]:
        return sorted(
            self.findings.values(),
            key=lambda item: (-SEVERITY_ORDER[item["severity"]], item["rule_id"], item["title"]),
        )

    def risk_score(self) -> int:
        return min(
            100,
            sum(SEVERITY_SCORE[finding["severity"]] for finding in self.sorted_findings()),
        )

    def severity_counts(self) -> dict[str, int]:
        counts = Counter(finding["severity"] for finding in self.sorted_findings())
        return {severity: counts.get(severity, 0) for severity in SEVERITY_ORDER}
