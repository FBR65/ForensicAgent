from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DomainRule:
    id: str
    name: str
    description: str
    fact_types: list[str]
    check: str
    severity: str = "warning"


@dataclass
class DomainConfig:
    name: str
    label: str
    categories: list[str] = field(default_factory=list)
    requirements: list[dict[str, Any]] = field(default_factory=list)
    rules: list[DomainRule] = field(default_factory=list)
    entity_patterns: dict[str, list[str]] = field(default_factory=dict)


_DEFAULT_CONFIG = DomainConfig(
    name="general",
    label="General Forensic",
    categories=[
        "identity_document", "financial_record", "communication",
        "log_file", "medical_record", "expert_report",
        "court_filing", "template", "metadata", "other",
    ],
    requirements=[
        {"domain": "general", "description": "Identity verification", "required_fact_types": ["PERSON", "DATE"]},
        {"domain": "general", "description": "Source traceability", "required_fact_types": ["SOURCE"]},
    ],
    entity_patterns={
        "PERSON": [],
        "ORG": [],
        "DATE": [],
        "AMOUNT": [],
    },
)


def load_domain(domain_name: str = "general", base_dir: str | Path | None = None) -> DomainConfig:
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent / "domains"
    domain_path = Path(base_dir) / f"{domain_name}.json"
    if not domain_path.exists():
        return _DEFAULT_CONFIG
    with open(domain_path) as f:
        data = json.load(f)
    rules = [DomainRule(**r) for r in data.get("rules", [])]
    return DomainConfig(
        name=data.get("name", domain_name),
        label=data.get("label", domain_name.title()),
        categories=data.get("categories", []),
        requirements=data.get("requirements", []),
        rules=rules,
        entity_patterns=data.get("entity_patterns", {}),
    )
