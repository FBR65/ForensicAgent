#!/usr/bin/env python3
"""Manual mutation tests for Semantica phases 7-9.

Introduces plausible bugs one at a time, runs the relevant test suite,
and checks that at least one test catches the mutant.  Restores after
each mutation.
"""

import subprocess
import sys
import shutil
from pathlib import Path

SRC_DIR = Path("src/forensicagent")
TESTS = [
    "tests/test_semantica_retrieval.py",
    "tests/test_semantica_assessment.py",
    "tests/test_semantica_query.py",
    "tests/test_semantica_integration.py",
]

def run_tests():
    """Run the relevant tests and return (passed, output)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=line", "-q"] + TESTS,
        capture_output=True, text=True, timeout=120,
    )
    output = result.stdout + result.stderr
    # Count passed/failed
    if "failed" in output.lower() or result.returncode != 0:
        return False, output
    return True, output

def mutate(file_path, old, new, description):
    """Apply a mutation, run tests, check if killed, restore."""
    full_path = Path(file_path)
    content = full_path.read_text()

    if old not in content:
        print(f"  SKIP (pattern not found): {description}")
        return None

    # Backup
    backup = content
    mutated = content.replace(old, new, 1)
    full_path.write_text(mutated)

    print(f"  MUTANT: {description}")
    try:
        passed, output = run_tests()
        if passed:
            print(f"  SURVIVED — no test caught this mutant!")
            return "survived"
        else:
            # Extract just the failure summary
            for line in output.split("\n"):
                if "FAILED" in line or "failed" in line.lower():
                    print(f"  KILLED by: {line.strip()}")
                    break
            return "killed"
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT — treating as killed")
        return "killed"
    finally:
        full_path.write_text(backup)

print("=" * 70)
print("MUTATION TESTING — Semantica Phases 7-9")
print("=" * 70)

results = []

# --- Phase 7: semantica_retrieval.py ---
print("\n--- Phase 7: semantica_retrieval.py ---")

r = mutate(
    "src/forensicagent/pipeline/semantica_retrieval.py",
    "use_graph_expansion=True,",
    "use_graph_expansion=False,",
    "Disable graph expansion in retrieval init",
)
results.append(("P7-graph_expansion", r))

r = mutate(
    "src/forensicagent/pipeline/semantica_retrieval.py",
    "hybrid_alpha=1.0,  # graph-only (no vector store)",
    "hybrid_alpha=0.0,  # MUTANT: vector-only",
    "Set hybrid_alpha to 0.0 (vector-only instead of graph-only)",
)
results.append(("P7-hybrid_alpha", r))

r = mutate(
    "src/forensicagent/pipeline/semantica_retrieval.py",
    "return self._retriever.graph_search(query, max_results=max_results)",
    "return []  # MUTANT",
    "graph_search returns empty list",
)
results.append(("P7-graph_search_empty", r))

# --- Phase 8: semantica_assessment.py ---
print("\n--- Phase 8: semantica_assessment.py ---")

r = mutate(
    "src/forensicagent/pipeline/semantica_assessment.py",
    "return self._cg.trace_decision_chain(decision_id, max_steps=max_steps)",
    "return []  # MUTANT",
    "trace_decision_chain returns empty list",
)
results.append(("P8-trace_empty", r))

r = mutate(
    "src/forensicagent/pipeline/semantica_assessment.py",
    "dec_id = self._cg.record_decision(",
    "dec_id = None  # MUTANT: skip recording\n            # self._cg.record_decision disabled",
    "record_decision returns None without recording",
)
results.append(("P8-record_none", r))

r = mutate(
    "src/forensicagent/agents/assessment.py",
    "if self._decision_kit is None or not self._decision_kit.is_available():",
    "if True:  # MUTANT: always skip recording",
    "Assessment agent never records decisions",
)
results.append(("P8-agent_skip_record", r))

# --- Phase 9: semantica_query.py ---
print("\n--- Phase 9: semantica_query.py ---")

r = mutate(
    "src/forensicagent/pipeline/semantica_query.py",
    "return self._cg.query(query, limit=limit) if limit else self._cg.query(query)",
    "return []  # MUTANT",
    "query_graph returns empty list",
)
results.append(("P9-query_empty", r))

r = mutate(
    "src/forensicagent/pipeline/semantica_query.py",
    "return self._cg.find_related_nodes(node_id, how_many=how_many)",
    "return []  # MUTANT",
    "find_related returns empty list",
)
results.append(("P9-find_related_empty", r))

r = mutate(
    "src/forensicagent/agents/context_builder.py",
    'if self._kg_query is not None and self._kg_query.is_available():',
    'if False:  # MUTANT: skip graph query',
    "Context builder skips graph query",
)
results.append(("P9-context_skip_graph", r))

# --- Summary ---
print("\n" + "=" * 70)
print("MUTATION SUMMARY")
print("=" * 70)
killed = sum(1 for _, r in results if r == "killed")
survived = sum(1 for _, r in results if r == "survived")
skipped = sum(1 for _, r in results if r is None)
total = len(results)
print(f"Total: {total}  Killed: {killed}  Survived: {survived}  Skipped: {skipped}")
for name, r in results:
    status = r or "skip"
    print(f"  {name}: {status}")
print("=" * 70)