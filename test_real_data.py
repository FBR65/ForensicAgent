#!/usr/bin/env python3
"""End-to-end test of the ForensicAgent pipeline on three synthetic real-data cases.

Cases:
  1. legal_001     — Zivilprozess Arbeitsplatzunfall (TXT + PDF + DOCX)
  2. cyber_001     — Ransomware-Angriff (TXT + PDF + DOCX)
  3. financial_001 — Betrugsverdacht Buchhaltung (TXT + PDF + DOCX)

Each case exercises mixed-format ingestion (anydoc for PDF/DOCX, direct for TXT),
domain-specific rules, BM25 keyword indexing, fact extraction, evidence linking,
graph construction, requirements evaluation, deterministic query, grounding,
and markdown report export.
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s: %(message)s")

from forensicagent.pipeline.orchestrator import ForensicPipeline

BASE = Path(__file__).parent / "sample_cases"

CASES = [
    {
        "case_id": "LEGAL-2026-001",
        "domain": "legal",
        "dir": BASE / "legal_001" / "evidence",
        "kb_dir": str(BASE / "legal_001" / "domains" / "legal"),
        "queries": [
            "Wer ist der Klieger und wer ist die Beklagte?",
            "Wie hoch ist der Gesamtschaden?",
            "Welches Gerichtsaktenzeichen hat der Fall?",
            "Gibt es Hinweise auf eine Pflichtverletzung der Beklagten?",
        ],
    },
    {
        "case_id": "CYBER-2026-001",
        "domain": "cyber",
        "dir": BASE / "cyber_001" / "evidence",
        "kb_dir": str(BASE / "cyber_001" / "domains" / "cyber"),
        "queries": [
            "Welche IP-Adressen sind als C2-Server identifiziert?",
            "Wie viele Server waren von der Ransomware betroffen?",
            "Wann begann der Angriff und wann wurde er erkannt?",
            "Wie hoch ist der geschaetzte Schaden?",
        ],
    },
    {
        "case_id": "FIN-2026-001",
        "domain": "financial",
        "dir": BASE / "financial_001" / "evidence",
        "kb_dir": str(BASE / "financial_001" / "domains" / "financial"),
        "queries": [
            "Wer ist der Beschuldigte und was ist seine Position?",
            "Wie hoch ist das geschaetzte auffaellige Volumen?",
            "Welche IBAN erscheint mehrfach in den Buchungen?",
            "Gibt es Hinweise auf Scheinrechnungen?",
        ],
    },
]


def run_case(cfg: dict) -> None:
    case_id = cfg["case_id"]
    evidence_dir = cfg["dir"]
    kb_dir = cfg["kb_dir"]
    domain = cfg["domain"]

    files = sorted(str(p) for p in evidence_dir.iterdir() if p.is_file())
    print(f"\n{'='*70}")
    print(f"CASE: {case_id} (domain={domain})")
    print(f"Files: {[Path(f).name for f in files]}")
    print(f"{'='*70}")

    with ForensicPipeline(case_id=case_id, domain=domain, kb_dirs=[kb_dir]) as pipeline:
        sources = pipeline.ingest(files)
        print(f"\nIngested {len(sources)} sources:")
        for s in sources:
            print(f"  [{s.status.value:>16s}] {Path(s.path).name:30s} "
                  f"mime={s.mime:20s} quality={s.quality_score:.2f} ocr={s.ocr_used}")

        pipeline.index_keywords()
        facts, evidence = pipeline.extract_and_link()
        pipeline.build_graph()

        graph = pipeline.graph
        print(f"\n--- GRAPH SUMMARY ---")
        print(f"Sources:      {len(graph.all_sources())}")
        print(f"Facts:        {len(graph.all_facts())}")
        print(f"Evidence:     {len(graph.all_evidence())}")
        print(f"Requirements: {len(graph.all_requirements())}")

        print(f"\n--- FACT TABLE (first 25) ---")
        for row in graph.fact_table()[:25]:
            print(f"  [{row['status']:>11s}] {row['type']:<16} "
                  f"{str(row['value'])[:35]:<35} conf={row['confidence']:.2f} "
                  f"src={row['sources']}")

        print(f"\n--- REQUIREMENTS ---")
        for req in graph.all_requirements():
            print(f"  {req.description}: {req.status.value} "
                  f"(missing: {req.missing_fact_types})")

        print(f"\n--- QUERIES ---")
        for q in cfg["queries"]:
            result = pipeline.query(q)
            answer = result["answer"][:300]
            mode = result["mode"]
            passed = result["grounding"]["passed"]
            status = "PASSED" if passed else "REJECTED"
            print(f"\n  Q: {q}")
            print(f"  A ({mode}, grounding={status}): {answer}")
            if not passed:
                for uc in result["grounding"]["ungrounded_claims"]:
                    print(f"    Ungrounded {uc['type']}: {uc['claim'][:100]}")

        print(f"\n--- REPORT (first 2000 chars) ---")
        report_md = pipeline.export_markdown_report()
        print(report_md[:2000])

    print(f"\n[{case_id} session destroyed]")


def main() -> None:
    for cfg in CASES:
        run_case(cfg)
    print(f"\n{'='*70}")
    print("All 3 cases completed.")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()