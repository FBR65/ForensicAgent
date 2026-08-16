from __future__ import annotations

import re

from forensicagent.agents.base import BaseAgent
from forensicagent.models import DocumentClass, Source
from forensicagent.utils.spacy_utils import get_nlp

_CLASS_KEYWORDS = {
    "identity_document": ["id card", "passport", "driver license", "tax code", "fiscal code", "social security",
                          "birth certificate", "identity card", "national id"],
    "financial_record": ["bank statement", "balance", "debt", "liability", "asset", "income", "salary",
                         "payment", "invoice", "receipt", "loan", "credit", "mortgage", "transaction"],
    "communication": ["email", "letter", "memo", "correspondence", "message", "notice", "contract"],
    "log_file": ["log", "timestamp", "event", "audit", "server", "access", "request", "error", "system"],
    "medical_record": ["medical", "diagnosis", "treatment", "patient", "doctor", "hospital", "prescription"],
    "expert_report": ["expert", "analysis", "findings", "conclusion", "forensic", "report", "examination"],
    "court_filing": ["motion", "petition", "complaint", "brief", "order", "decree", "judgment", "court"],
    "template": ["template", "sample", "form", "draft", "placeholder", "example", "xxx"],
    "metadata": ["metadata", "index", "toc", "table of contents", "summary"],
}

_FUNCTION_WEIGHTS = {
    "PRIMARY": 5,
    "DERIVATIVE": 4,
    "TEMPLATE": 2,
    "METADATA": 1,
}


class ClassificationAgent(BaseAgent):
    name = "classification"

    def classify(self, source: Source) -> DocumentClass:
        text_lower = source.raw_text.lower()
        scores: dict[str, float] = {}
        for category, keywords in _CLASS_KEYWORDS.items():
            for kw in keywords:
                pattern = re.escape(kw)
                count = len(re.findall(pattern, text_lower))
                if count:
                    scores[category] = scores.get(category, 0.0) + count

        if scores:
            top_cat = max(scores, key=scores.get)
            confidence = min(1.0, scores[top_cat] / max(1, len(source.raw_text.split()) / 20))
            category = top_cat
        else:
            category = "other"
            confidence = 0.0

        if "template" in text_lower and category != "template":
            function = "TEMPLATE"
        elif "summary" in text_lower or "index" in text_lower:
            function = "METADATA"
        else:
            function = "PRIMARY"

        doc_class = DocumentClass(
            category=category,
            function=function,
            weight=_FUNCTION_WEIGHTS.get(function, 3),
            confidence=round(confidence, 3),
        )
        source.classification = doc_class
        return doc_class

    def classify_batch(self, sources: list[Source]) -> list[Source]:
        for s in sources:
            self.classify(s)
        return sources

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}
