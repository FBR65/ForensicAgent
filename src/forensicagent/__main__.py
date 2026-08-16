from __future__ import annotations

import logging
import sys

from forensicagent.pipeline.orchestrator import ForensicPipeline

__version__ = "0.1.0"

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s: %(message)s")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: forensicagent <case_dir_or_file> [query ...]")
        print("Example: forensicagent ./evidence/ 'What is the total liability?'")
        sys.exit(1)

    import glob
    from pathlib import Path

    arg = sys.argv[1]
    if Path(arg).is_dir():
        files = sorted(glob.glob(str(Path(arg) / "*")))
    else:
        files = [arg]

    queries = sys.argv[2:]
    if not queries:
        queries = ["What facts are confirmed in this case file?"]

    with ForensicPipeline(case_id="CLI-CASE") as pipeline:
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
                print("\n[Grounding] PASSED ✓")
            else:
                print(f"\n[Grounding] REJECTED ✗ — {result['grounding']['summary']}")
                for uc in result["grounding"]["ungrounded_claims"]:
                    print(f"  ↳ Ungrounded {uc['type']}: {uc['claim']}")

        print("\n" + "=" * 60)
        print("REPORT")
        print("=" * 60)
        print(pipeline.export_markdown_report())


if __name__ == "__main__":
    main()
