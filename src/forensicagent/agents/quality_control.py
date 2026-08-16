from __future__ import annotations

import re

from forensicagent.agents.base import BaseAgent
from forensicagent.models import Source, SourceStatus


class QualityControlAgent(BaseAgent):
    name = "quality_control"

    _ABNORMAL_RE = re.compile(r"[^\x00-\x7F]{4,}")
    _TRUNCATED_RE = re.compile(r"\b\d{1,10}\b.*[\.\-] ?$")
    _TECH_MARKER_RE = re.compile(r"^(\s*Page\s+\d+\s*|\s*\d+\s*/\s*\d+\s*|\s*—\s*|\s*\|)")

    def assess(self, source: Source) -> SourceStatus:
        issues: list[str] = []
        text = source.raw_text
        if not text or len(text.strip()) < 10:
            source.status = SourceStatus.BLOCKING
            source.metadata["qc_issues"] = ["empty_text"]
            return source.status
        if source.ocr_used:
            abnormal_pages = len(self._ABNORMAL_RE.findall(text))
            if abnormal_pages > 5:
                issues.append("abnormal_characters")
            trunc_lines = len(self._TRUNCATED_RE.findall(text, re.MULTILINE))
            if trunc_lines > 10:
                issues.append("truncated_lines")
            tech_markers = len(self._TECH_MARKER_RE.findall(text, re.MULTILINE))
            if tech_markers > 5:
                issues.append("technical_markers")
        word_count = len(text.split())
        source.metadata["word_count"] = word_count
        source.metadata["line_count"] = text.count("\n") + 1
        if issues:
            source.status = SourceStatus.REVIEW
            source.metadata["qc_issues"] = issues
            source.quality_score = max(0.0, 1.0 - 0.15 * len(issues))
        else:
            source.status = SourceStatus.USABLE
            source.quality_score = 1.0
        return source.status

    def assess_batch(self, sources: list[Source]) -> list[Source]:
        for s in sources:
            self.assess(s)
        return sources

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}
