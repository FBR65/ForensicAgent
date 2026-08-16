#!/usr/bin/env python3
"""End-to-end test of the ForensicAgent pipeline on the insurance fraud sample case."""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s: %(message)s")

from forensicagent.pipeline.orchestrator import ForensicPipeline

KB_DIR = "sample_cases/insurance_fraud_001/domains/general"
EVIDENCE_DIR = "sample_cases/insurance_fraud_001/evidence"
RULES_FILE = f"{KB_DIR}/general_rules.json"

queries = [
    "What is the insured person's name and tax ID?",
    "Is there evidence of a collision between the claimed vehicles?",
    "What damage is actually visible on the vehicle according to the inspection report?",
    "What is the total claimed liability?",
]

with ForensicPipeline(case_id="INS-FRAUD-2026-001", domain="general", kb_dirs=[KB_DIR]) as pipeline:
    sources = pipeline.ingest([
        f"{EVIDENCE_DIR}/claim_file.txt",
        f"{EVIDENCE_DIR}/police_report.txt",
    ])
    pipeline.index_keywords()
    facts, evidence = pipeline.extract_and_link()
    pipeline.build_graph()

    graph = pipeline.graph
    print(f"\n--- CASE GRAPH SUMMARY ---")
    print(f"Sources: {len(graph.all_sources())}")
    print(f"Facts:   {len(graph.all_facts())}")
    print(f"Evidence: {len(graph.all_evidence())}")
    print(f"Requirements: {len(graph.all_requirements())}")

    print("\n--- FACT TABLE (first 20) ---")
    for row in graph.fact_table()[:20]:
        print(f"  [{row['status']:>11s}] {row['type']:<14} {row['value']:<30} conf={row['confidence']:.2f} src={row['sources']}")

    print("\n--- REQUIREMENTS ---")
    for req in graph.all_requirements():
        print(f"  {req.description}: {req.status.value} (missing: {req.missing_fact_types})")

    print("\n--- REPORT ---")
    report = pipeline.build_report(title="Insurance Fraud Investigation — Preliminary Report")
    print(pipeline.export_markdown_report()[:3000])

    print("\n--- QUERIES ---")
    for q in queries:
        print(f"\nQ: {q}")
        result = pipeline.query(q)
        print(f"A ({result['mode']}): {result['answer'][:400]}")
        print(f"  Grounding: {'PASSED' if result['grounding']['passed'] else 'REJECTED'} — {result['grounding']['summary']}")

print("\n[Pipeline closed — session/LMDB destroyed]")
