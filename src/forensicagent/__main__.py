from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
from pathlib import Path

from forensicagent.pipeline.orchestrator import ForensicPipeline

__version__ = "0.1.0"

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s: %(message)s")

_DOMAINS_DIR = Path(__file__).resolve().parent / "domains"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forensicagent",
        description=(
            "General-purpose AI forensic agent pipeline. "
            "Reads a case file, verifies evidence, and helps draft a report."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # --- run: ingest a case file and answer queries ---
    p_run = sub.add_parser(
        "run",
        help="Ingest a case file/directory and answer queries (default command).",
    )
    p_run.add_argument("case", help="Case file or directory to ingest.")
    p_run.add_argument("query", nargs="*", help="Query to answer (default: list confirmed facts).")
    p_run.add_argument("--domain", default="general", help="Domain config to use (default: general).")
    p_run.add_argument("--kb-dir", action="append", default=[], help="Knowledge-base directory (repeatable).")
    p_run.add_argument("--no-semantica", action="store_true", help="Force legacy mode (no Semantica).")
    p_run.add_argument("--api-key", help="LLM API key (overrides OPENAI_API_KEY).")
    p_run.add_argument("--base-url", help="LLM base URL (overrides OPENAI_BASE_URL).")
    p_run.add_argument("--model-id", help="LLM model id (overrides OPENAI_MODEL_ID).")

    # --- new-domain: scaffold a new domain config (README §19) ---
    p_dom = sub.add_parser(
        "new-domain",
        help="Scaffold a new forensic domain configuration (README §19).",
    )
    p_dom.add_argument("name", help="Domain name (e.g. 'insurance').")
    p_dom.add_argument("--label", help="Human-readable label (default: title-cased name).")
    p_dom.add_argument("--output", help="Output path for the JSON file (default: src/forensicagent/domains/<name>.json).")
    p_dom.add_argument("--force", action="store_true", help="Overwrite an existing file.")

    # --- kb-add: author a KB document from a description (README §20) ---
    p_kb = sub.add_parser(
        "kb-add",
        help="Author a knowledge-base document from a description (README §20).",
    )
    p_kb.add_argument("kb_dir", help="Knowledge-base directory to write into.")
    p_kb.add_argument("description", help="Free-form description of the rule / precedent / procedure.")
    p_kb.add_argument("--domain", default="general", help="Domain tag for the document (default: general).")
    p_kb.add_argument("--file", help="Explicit output file (default: <kb_dir>/<id>.json).")

    # --- kb-list: list KB documents ---
    p_list = sub.add_parser(
        "kb-list",
        help="List documents in a knowledge-base directory.",
    )
    p_list.add_argument("kb_dir", help="Knowledge-base directory to list.")

    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    # Per-invocation LLM overrides (highest priority, above config.yaml and
    # environment variables).
    llm_overrides: dict[str, str] = {}
    if args.api_key:
        llm_overrides["api_key"] = args.api_key
    if args.base_url:
        llm_overrides["base_url"] = args.base_url
    if args.model_id:
        llm_overrides["model_id"] = args.model_id

    arg = args.case
    if Path(arg).is_dir():
        files = sorted(glob.glob(str(Path(arg) / "*")))
    else:
        files = [arg]

    queries = args.query or ["What facts are confirmed in this case file?"]

    with ForensicPipeline(
        case_id="CLI-CASE",
        domain=args.domain,
        kb_dirs=args.kb_dir or None,
        use_semantica=not args.no_semantica,
        llm_overrides=llm_overrides or None,
    ) as pipeline:
        pipeline.ingest(files)
        pipeline.index_keywords()
        pipeline.extract_and_link()
        pipeline.build_graph()

        for q in queries:
            print(f"\n{'='*60}")
            print(f"Q: {q}")
            print("=" * 60)
            result = pipeline.query(q)
            print(f"\nAnswer ({result['mode']}): {result['answer']}")
            if result["grounding"]["passed"]:
                print("\n[Grounding] PASSED")
            else:
                print(f"\n[Grounding] REJECTED - {result['grounding']['summary']}")
                for uc in result["grounding"]["ungrounded_claims"]:
                    print(f"  - Ungrounded {uc['type']}: {uc['claim']}")

        print("\n" + "=" * 60)
        print("REPORT")
        print("=" * 60)
        print(pipeline.export_markdown_report())
    return 0


def _cmd_new_domain(args: argparse.Namespace) -> int:
    """Scaffold a new domain config (README §19)."""
    name = args.name
    label = args.label or name.replace("_", " ").title()

    if args.output:
        out = Path(args.output)
    else:
        out = _DOMAINS_DIR / f"{name}.json"

    if out.exists() and not args.force:
        print(f"Error: {out} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "name": name,
        "label": label,
        "categories": [
            "identity_document", "financial_record", "communication",
            "log_file", "medical_record", "expert_report",
            "court_filing", "template", "metadata", "other",
        ],
        "requirements": [
            {
                "domain": name,
                "description": "Identity verification",
                "required_fact_types": ["PERSON", "DATE"],
            }
        ],
        "rules": [
            {
                "id": f"{name}-1",
                "name": "Identity Verification",
                "description": "Person facts must trace to a source",
                "fact_types": ["PERSON"],
                "check": "has_evidence",
                "severity": "error",
            },
            {
                "id": f"{name}-2",
                "name": "Amount Must Have Source",
                "description": "Every monetary amount must have documented evidence",
                "fact_types": ["AMOUNT"],
                "check": "has_evidence",
                "severity": "error",
            },
        ],
        "entity_patterns": {
            "PERSON": [],
            "ORG": [],
            "DATE": [],
            "AMOUNT": [],
        },
    }
    out.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created domain config: {out}")
    print("Edit the file to add requirements, rules, and entity patterns.")
    print("Then use it with: forensicagent run <case> --domain <name>")
    return 0


def _cmd_kb_add(args: argparse.Namespace) -> int:
    """Author a KB document from a description (README §20)."""
    from forensicagent.agents.knowledge_base import KnowledgeBaseAgent

    kb_dir = Path(args.kb_dir)
    kb_dir.mkdir(parents=True, exist_ok=True)

    agent = KnowledgeBaseAgent("CLI-KB", kb_dirs=[kb_dir])
    doc = agent.draft_from_description(args.description, domain=args.domain)
    path = agent.add_document(doc, file=args.file)

    print(f"KB document written: {path}")
    print(f"  id:    {doc['id']}")
    print(f"  title: {doc['title']}")
    print(f"  tags:  {doc.get('tags', [])}")
    print(f"  body:  {doc['body'][:120]}{'...' if len(doc['body']) > 120 else ''}")
    return 0


def _cmd_kb_list(args: argparse.Namespace) -> int:
    """List documents in a knowledge-base directory."""
    kb_dir = Path(args.kb_dir)
    if not kb_dir.exists():
        print(f"Error: KB directory not found: {kb_dir}", file=sys.stderr)
        return 1

    files = sorted(kb_dir.rglob("*"))
    docs = [f for f in files if f.suffix in (".json", ".txt", ".md")]
    if not docs:
        print(f"No KB documents found in {kb_dir}")
        return 0

    print(f"Knowledge base: {kb_dir}")
    for f in docs:
        rel = f.relative_to(kb_dir)
        if f.suffix == ".json":
            try:
                with open(f) as fh:
                    data = json.load(fh)
                items = data if isinstance(data, list) else data.get("items", [])
                for it in items:
                    print(f"  - {rel}  [{it.get('id', '?')}] {it.get('title', '?')}")
            except Exception:
                print(f"  - {rel}  (unreadable JSON)")
        else:
            print(f"  - {rel}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "run":
        return _cmd_run(args)
    if args.command == "new-domain":
        return _cmd_new_domain(args)
    if args.command == "kb-add":
        return _cmd_kb_add(args)
    if args.command == "kb-list":
        return _cmd_kb_list(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
