from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from forensicagent.agents.base import BaseAgent
from forensicagent.models import Finding, FindingStatus, Fact
from forensicagent.pipeline.graph import CaseGraph

logger = logging.getLogger(__name__)


class ReportingAgent(BaseAgent):
    """Compiles findings into a structured, section-by-section report
    using the Drafting Matrix concept.

    Each section of the report is tied to a Requirement.  A section is
    only marked as *complete* when its required facts are CONFIRMED and
    the evidence path is intact.  Otherwise it carries a warning.
    """

    name = "reporting"

    def __init__(self, case_id: str, graph: CaseGraph) -> None:
        super().__init__(case_id)
        self._graph = graph

    def build_report(self, title: str = "Forensic Case Report") -> dict[str, Any]:
        matrix = self._graph.drafting_matrix(self._graph.all_requirements())
        findings = self._graph.all_findings()

        sections: list[dict[str, Any]] = []
        for row in matrix:
            sections.append({
                "section": row["requirement"],
                "domain": row["domain"],
                "status": row["status"],
                "required_facts": row["required_facts"],
                "covered_facts": row["covered"],
                "missing_facts": row["missing"],
                "warning": row["status"] != "satisfied",
            })

        report = {
            "title": title,
            "case_id": self._graph.case_id,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "sections": sections,
            "findings": [self._finding_to_dict(f) for f in findings],
            "fact_table": self._graph.fact_table(),
            "evidence_audit": self._graph.evidence_audit()[:50],
            "amount_audit": self._amount_audit(),
            "quality_score": self._compute_quality_score(matrix),
            "warnings": self._collect_warnings(matrix),
        }
        logger.info("Report built: %d sections, %d findings", len(sections), len(findings))
        return report

    def _amount_audit(self) -> list[dict[str, Any]]:
        """Expose the amount provenance / addend audit for AMOUNT facts."""
        audit: list[dict[str, Any]] = []
        for fact in self._graph.all_facts():
            if fact.type != "AMOUNT":
                continue
            amount = (fact.metadata or {}).get("amount")
            audit.append({
                "fact_id": fact.id,
                "value": str(fact.value),
                "status": fact.status.value,
                "source_type": amount.source_type.value if amount else "unproven",
                "is_total": bool(amount and amount.is_total),
                "addend_ids": amount.addend_ids if amount else [],
                "sources": fact.source_ids,
            })
        return audit

    def _finding_to_dict(self, f: Finding) -> dict[str, Any]:
        fact_ids = []
        for fid in f.fact_ids:
            fact = self._graph.get_fact(fid)
            if fact:
                fact_ids.append({"id": fid, "type": fact.type, "value": str(fact.value)})
        return {
            "id": f.id,
            "statement": f.statement,
            "confidence": f.confidence,
            "status": f.status.value,
            "evidence_path": f.evidence_path,
            "linked_facts": fact_ids,
        }

    def _compute_quality_score(self, matrix: list[dict[str, Any]]) -> float:
        if not matrix:
            return 0.0
        weights = {"satisfied": 1.0, "partial": 0.5, "unsatisfied": 0.0}
        total = sum(weights.get(r["status"], 0.0) for r in matrix)
        return round(total / len(matrix), 3)

    def _collect_warnings(self, matrix: list[dict[str, Any]]) -> list[str]:
        warnings = []
        for r in matrix:
            if r["missing"]:
                warnings.append(
                    f"Requirement '{r['requirement']}' missing facts: {r['missing']}"
                )
            if r["status"] == "unsatisfied":
                warnings.append(f"Requirement '{r['requirement']}' is unsatisfied — professional review required.")
        return warnings

    def export_markdown(self, report: dict[str, Any]) -> str:
        lines = [f"# {report['title']}", f"\nCase ID: `{report['case_id']}`", f"\nGenerated: {report['generated_at']}", f"\nQuality Score: **{report['quality_score']}**"]
        lines.append("\n## Findings\n")
        for f in report["findings"]:
            lines.append(f"- **[{f['status']}]** {f['statement']} (confidence: {f['confidence']:.2f})")
        lines.append("\n## Sections / Requirements\n")
        for s in report["sections"]:
            flag = "✅" if s["status"] == "satisfied" else "⚠️"
            lines.append(f"- {flag} {s['section']} — `{s['status']}`")
            if s["missing_facts"]:
                lines.append(f"    - Missing: {s['missing_facts']}")
        if report["warnings"]:
            lines.append("\n## Warnings\n")
            for w in report["warnings"]:
                lines.append(f"- ⚠️ {w}")
        lines.append("\n## Evidence Audit (excerpt)\n")
        for ev in report["evidence_audit"][:10]:
            lines.append(f"- [{ev['evidence_id']}] {ev['snippet'][:120]}")
        if report.get("amount_audit"):
            lines.append("\n## Amount Audit (provenance / addends)\n")
            for a in report["amount_audit"]:
                flag = "✅" if a["status"] == "confirmed" else "⚠️"
                lines.append(
                    f"- {flag} {a['value']} [{a['source_type']}] "
                    f"total={a['is_total']} addends={a['addend_ids']}"
                )
        return "\n".join(lines)

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}
