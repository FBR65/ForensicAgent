# ForensicAgent

A general-purpose AI forensic agent pipeline applicable to any forensic activity:
legal case files, cyber-incident investigations, financial fraud analysis, insurance
claims, tax fraud investigations, medical-examiner reports, and other investigation types.

The system is built with **Agno** (agent framework), **SpaCy** (`de_dep_news_trf`),
**BM25** (`rank-bm25`), **Semantica** (`semantica[agno]` — ContextGraph, Provenance,
Conflict Detection, Deduplication, Datalog Reasoning, PROV-O Export), and **LMDB** for
volatile per-session case storage. Document ingestion is handled by
**`firecrawl-anydoc`** (`anydoc`) — a fully local document-to-Markdown converter that
requires no API key and no external service.

---

## 1. Philosophy

> Do not generate text first — build an evidentiary foundation.

This design principle, adapted from the "AI Forensic Agents" article by Andrea Belvedere,
places the language model as the *final, constrained* link in a pipeline of deterministic
processing steps. Every fact emitted by the LLM must trace back to **atomic evidence**
stored in a volatile, per-session **evidentiary knowledge graph**.

A real forensic agent does not take a case file, send everything to a language model, and
hope the output is correct. That approach is fragile: the model may confuse documents,
sum the wrong amounts, treat a source as evidence when it is not, or draw conclusions not
supported by the record. Instead, the agent reads, classifies, extracts facts, checks the
evidence, builds a graph, retrieves relevant domain sources, and only at the end invokes
the LLM inside a verified perimeter.

---

## 2. High-Level Pipeline

```
Case File (documents / logs / artefacts)
   |
   +- 1. Ingestion        Parse doc/docx/odt/rtf/epub/pdf/ppt/xls/csv (anydoc), TXT, OCR
   +- 2. Quality Control  Measure OCR / parse quality
   +- 3. Classification   Categorise by evidentiary function
   +- 4. Keyword Index    BM25 index of every source
   +- 5. Fact Extraction  SpaCy NER + custom entity rules
   +- 6. Evidence Linking Atomic evidence -> fact edges
   +- 7. Graph Build      Case knowledge graph (NetworkX + ContextGraph)
   +- 8. Validation       Datalog rules + deterministic checks
   +- 9. Knowledge RAG    Multi-hop GraphRAG (Semantica) + BM25 fallback
   +-10. Context Build    Construct controlled LLM context (AgnoKGToolkit)
   +-11. Assessment       LLM reasoning within evidence perimeter (AgnoDecisionKit)
   +-12. Grounding        Verify LLM output against evidence
   +-13. Reporting        Section-by-section draft + audit + PROV-O export
   +-14. Review           Human-in-the-loop corrections
```

---

## 3. Agent / Component Matrix

Each processing step is an Agno-based agent. The LLM is optional: without an
`OPENAI_API_KEY`, the pipeline runs in deterministic (graph-query) mode.

| # | Agent | Responsibility |
|---|-------|----------------|
| 1 | **IngestionAgent** | Read PDF, DOCX, TXT, images (OCR), structured logs via `firecrawl-anydoc` |
| 2 | **QualityControlAgent** | Assign per-source status: `usable` / `requires_review` / `blocking` |
| 3 | **ClassificationAgent** | Predict document function (primary / derivative / template / metadata) |
| 4 | **KeywordIndexAgent** | BM25 tokenisation and keyword extraction per source |
| 5 | **FactExtractionAgent** | NER + entity / amount / date extraction via SpaCy and custom rules |
| 6 | **EvidenceLinkingAgent** | Create `Evidence` objects (atomic fragments) linked to each `Fact` |
| 7 | **ValidationAgent** | Datalog rule verification (via Semantica) or deterministic fallback |
| 8 | **KnowledgeRetrievalAgent** | Multi-hop GraphRAG (Semantica) + BM25 fallback for domain KB retrieval |
| 9 | **KnowledgeBaseAgent** | LLM-assisted authoring of KB documents via Q&A |
|10 | **ContextBuilderAgent** | Assemble controlled context + AgnoKGToolkit graph queries |
|11 | **AssessmentAgent** | LLM reasoning + AgnoDecisionKit decision tracking and causal chains |
|12 | **GroundingAgent** | Post-generation verification of every claim against evidence |
|13 | **ReportingAgent** | Section-by-section report + drafting matrix + PROV-O export |
|14 | **ReviewAgent** | Human review workflow; corrections feed back into the graph |

---

## 4. Data Model

The case file is represented as a graph of connected entities.

```
Source        (document / artefact)
  - id, path, mime, status, quality_score
  - raw_text, metadata, keywords, classification

DocumentClass
  - category  (identity, financial, communication, ...)
  - function  (PRIMARY / DERIVATIVE / TEMPLATE / METADATA)
  - weight    (1-5)

Fact
  - id, case_id, type (PERSON / AMOUNT / DATE / TAX_CODE / IBAN / ...)
  - value, unit
  - status (CONFIRMED / APPROVED / CANDIDATE / INCOMPLETE / REJECTED / REVIEW)
  - confidence (0-1)
  - source_ids, evidence_ids

Evidence      (atomic fragment)
  - id, source_id, fact_id
  - snippet, page, start_char, end_char, confidence

Relationship
  - subject_fact_id, predicate, object_fact_id, evidence_id

Requirement
  - id, case_id, domain
  - description, status (SATISFIED / PARTIAL / UNSATISFIED)
  - required_fact_types

Finding
  - id, case_id, statement, confidence
  - status (supported / partial / unsupported)
  - evidence_path  (list of Evidence ids)
  - metadata       (conflict_type, values, detector_found)

CaseGraph     (volatile, per-session)
  - NetworkX DiGraph (working memory) + Semantica ContextGraph (mirror)
  - nodes: Case | Source | Fact | Evidence | Requirement | Finding | Relationship
  - edges: HAS_SOURCE, HAS_FACT, SUPPORTS, CONTAINS, HAS_EVIDENCE, REQUIRES
```

The key traceability path is:

```
Requirement -> Fact -> Evidence -> Source
```

A requirement is only considered satisfied when the complete evidentiary path exists.
If the path breaks, the agent reports the problem instead of treating the requirement
as fulfilled.

---

## 5. Two Knowledge Stores

The system keeps two physically separate stores.

| Store | Persistence | Contents | Access |
|-------|-------------|----------|--------|
| **Case Graph** | Volatile (LMDB + ContextGraph) | Case-specific evidence, facts, findings | Read-write; destroyed on session end |
| **Domain KB** | Persistent (BM25) | Statutes, procedures, protocols, templates, checklists | Read-only; shared across cases |

This separation guarantees that client / case data is never mixed into general knowledge.
One client's case must never become a source for another client. The case file lives in a
volatile session: deletion removes the graph, excerpts, and sensitive data; legal sources
remain separate.

---

## 6. Semantica Integration

When `semantica[agno]` is installed, the pipeline uses Semantica's infrastructure
alongside the existing NetworkX + LMDB layer. When Semantica is not available, the
pipeline falls back to legacy mode automatically.

| Component | Spec-ID | Function |
|-----------|---------|----------|
| `SemanticaBackend` | S-GRAPH, S-MEMORY | Factory holding ContextGraph, ProvenanceManager, ConflictDetector, DuplicateDetector, EntityMerger, DatalogReasoner, RDFExporter |
| `CaseGraph` adapter | S-GRAPH | Mirrors all `add_*` calls to ContextGraph; NetworkX remains working memory |
| `ProvenanceTracker` | S-PROV | W3C PROV-O provenance for every source and fact |
| `EntityDeduplicator` | S-DEDUP | Merges same-entity facts across documents (PERSON, IBAN, TAX_CODE, IP, DEVICE_ID) |
| `ConflictScanner` | S-CONFLICT | Detects contradictory values (e.g. different amounts for the same claim) |
| `DatalogValidator` | S-REASON | Translates JSON rules to Datalog rules; deterministic inference with explanation paths |
| `SemanticaRetrieval` | S-RETRIEVE | Multi-hop GraphRAG via ContextRetriever; BM25 as fallback |
| `SemanticaDecisionKit` | S-ASSESS, S-DECISION | Decision recording, precedent search, causal chain tracing |
| `SemanticaKGQuery` | S-QUERY | Graph queries, related-node lookup, subgraph export via AgnoKGToolkit |
| `export_provenance()` | S-EXPORT | PROV-O Turtle/JSON-LD export validated with rdflib |

### Fallback Mode

```python
# Force legacy mode (NetworkX + LMDB, no Semantica):
pipeline = ForensicPipeline(case_id="C", domain="general", use_semantica=False)
```

---

## 7. Core Principles

1. **Evidence-first**: facts are only usable if they trace to atomic evidence
   (Fact -> Evidence -> Source) in the case graph.
2. **Deterministic before probabilistic**: rule-based validation runs before any LLM
   invocation.
3. **Two knowledge stores**:
   - Volatile case graph (LMDB + ContextGraph), destroyed on `close()` / `destroy()`.
   - Persistent domain KB (BM25 index), read-only and shared.
4. **Constrained LLM**: the LLM may only use `CONFIRMED` / `APPROVED` facts; output is
   verified by the `GroundingAgent`.
5. **Audit-grade provenance**: every fact has W3C PROV-O provenance tracking its source,
   extraction activity, and agent.
6. **Conflict detection**: contradictory facts across sources are automatically flagged
   as Findings.

---

## 8. BM25 — Keyword Extraction and Retrieval

`rank-bm25` is used for two purposes.

1. **Keyword extraction per source**: the top-k BM25-weighted terms become the source's
   keyword vector, stored on the `Source` node. These keywords drive:
   - duplicate detection across the case file,
   - semantic search within the case corpus,
   - fast evidence lookup during grounding.

2. **Domain-KB retrieval**: the persistent KB is tokenised and indexed with BM25. The
   `KnowledgeRetrievalAgent` selects the most relevant domain rules and precedents for
   the current case. When Semantica is available, Multi-hop GraphRAG is used as the
   primary retrieval path with BM25 as fallback.

---

## 9. SpaCy — NLP Layer

SpaCy (`de_dep_news_trf`, a German transformer model) provides:

- tokenisation and lemmatisation for BM25 indexing,
- NER for persons, organisations, locations, dates, and identifiers,
- sentence segmentation for atomic evidence snippets,
- dependency parsing for relationship extraction.

Because the German model's NER can be unreliable on mixed-language or highly structured
forensic documents, custom regex patterns in `utils/spacy_utils.py`
(`extract_domain_entities`) compensate for TAX_CODE, IBAN, email, URL, IP address, phone,
dates, amounts, court references, device IDs, account numbers, and structured person
fields. SpaCy remains a support library; the LLM agents handle high-level reasoning.

---

## 10. Validation Layer

### Datalog Reasoning (with Semantica)

When Semantica is available, the `DatalogValidator` translates domain JSON rules into
`DatalogRule` objects and runs them through `DatalogReasoner` for deterministic inference
with explainable reasoning paths.

### Deterministic Fallback (without Semantica)

The `ValidationAgent` runs a declarative rule set stored as JSON. Each rule carries a
`fact_types` filter so it only applies to matching facts.

```
{
  "id": "tax-1",
  "name": "Steuernummer vorhanden",
  "description": "Jeder Steuerpflichtige muss mit Steuernummer identifiziert werden",
  "fact_types": ["TAX_CODE"],
  "check": "type:TAX_CODE",
  "severity": "error"
}
```

Supported `check` operators: `type:<T>`, `min_confidence:<N>`, `regex:<pattern>`,
`has_evidence`. A fact failing an `error` rule is `REJECTED`; failing a `warning` rule
marks it `REQUIRES_REVIEW`.

---

## 11. Controlled LLM Prompt

The `ContextBuilderAgent` assembles a context window containing only usable facts
(`CONFIRMED` / `APPROVED`), the requirement satisfaction map, domain rules, relevant
KB snippets, and graph query results (via `AgnoKGToolkit` when Semantica is available).
The `AssessmentAgent` prompt enforces:

```
You are a forensic reasoning agent.
You may ONLY use facts whose status is CONFIRMED or APPROVED.
For each claim you make, cite the fact id and evidence id that support it.
Never invent amounts, identifiers, courts, or dates.
```

Rejected or unproven data is excluded from the context entirely. When Semantica is
available, the `AgnoDecisionKit` records each assessment decision with its reasoning
and confidence, enabling causal chain tracing for audit purposes.

---

## 12. Output Grounding

After the LLM generates text, the `GroundingAgent` verifies the output:

1. Extract every numerical, identifier, court, or date claim.
2. Verify each claim maps to a `CONFIRMED` fact in the graph.
3. Any claim with no evidence path rejects the output and feeds it back into the graph
   as a `REQUIRES_REVIEW` item.

The system does not trust the model; it uses the model and then checks it. A rejected
output produces an operational indication rather than a generic error.

---

## 13. Reporting

The `ReportingAgent` compiles a **Drafting Matrix** — a per-section checklist that maps
each required section to its required facts, the evidence path, and its status.

| Section | Required Facts | Status | Notes |
|---------|----------------|--------|-------|
| Identity | PERSON, TAX_CODE | SATISFIED | |
| Liabilities | AMOUNT x 3 | PARTIAL | one amount needs review |
| Conflicts | AMOUNT | UNSUPPORTED | two contradictory amounts detected |

The final output is an **assisted draft + audit report**, not an automated decision.
Sections that are incomplete carry explicit warnings; the professional performs the
final review. When Semantica is available, a PROV-O Turtle export is generated for
regulatory audit purposes:

```python
prov_turtle = pipeline.export_provenance(format="turtle")
# Validated with rdflib — W3C PROV-O compliant
```

---

## 14. Domains

| Domain | Config | Description |
|--------|--------|-------------|
| `general` | `domains/general.json` | Default domain for insurance and general investigations |
| `legal` | `domains/legal.json` | Legal case files (Klage, Gerichtsgutachten, Zeugenaussage) |
| `cyber` | `domains/cyber.json` | Cyber-incident forensics (logs, firewall, incident reports) |
| `financial` | `domains/financial.json` | Financial fraud (bank statements, invoices, audit reports) |
| `tax` | `domains/tax.json` | Tax fraud / Steuerstrafverfahren (USt, AO, Scheinrechnungen) |

---

## 15. Quick Start

```python
from forensicagent.pipeline.orchestrator import ForensicPipeline

# With Semantica (default when installed):
with ForensicPipeline(case_id="CASE-2026-001", domain="general",
                      kb_dirs=["domains/general/knowledge"]) as pipeline:
    pipeline.ingest(["evidence/claim.txt", "evidence/police.txt"])
    pipeline.index_keywords()
    pipeline.extract_and_link()
    pipeline.build_graph()

    result = pipeline.query("Is there evidence of a collision?")
    print(result["answer"])              # grounded answer
    print(result["grounding"]["passed"]) # True if all claims verified

    report = pipeline.build_report()
    print(pipeline.export_markdown_report())

    # PROV-O export (when Semantica is available):
    prov = pipeline.export_provenance(format="turtle")
    print(f"PROV-O: {len(prov)} chars")

    # Conflicts detected during graph build:
    for f in pipeline.get_conflicts():
        print(f"CONFLICT: {f.statement}")

    # pipeline.close() destroys the volatile session.
```

---

## 16. Installation

```bash
uv sync
# The German transformer SpaCy model is installed separately (large download):
uv pip install "https://github.com/explosion/spacy-models/releases/download/de_dep_news_trf-3.8.0/de_dep_news_trf-3.8.0-py3-none-any.whl"
uv pip install -e .
```

Semantica is included in the dependencies (`semantica[agno]>=0.6.6,<0.7`). It brings
ContextGraph, Provenance, Conflict Detection, Deduplication, Datalog Reasoning, and
RDF Export. The pipeline works without Semantica in legacy mode
(`use_semantica=False`).

Ingestion notes:

- Documents are converted to Markdown locally by `firecrawl-anydoc` (`anydoc.to_markdown`
  / `to_markdown_bytes`) for doc, docx, odt, rtf, epub, pdf, ppt, xls, csv.
- Plain text (`.txt`, `.log`, `.md`) is read directly.
- Raster images (`.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`) fall back to OCR
  (`pytesseract`).

---

## 17. Usage

Run the end-to-end demo (sample insurance-fraud case):

```bash
.venv/bin/python run_demo.py
```

Run all 4 synthetic test cases (legal, cyber, financial, tax):

```bash
.venv/bin/python test_real_data.py
```

Run the CLI (ingest files/directories and answer a query):

```bash
.venv/bin/forensicagent ./sample_cases/insurance_fraud_001/evidence 'What is the total liability?'
```

Run the LLM (optional): set `OPENAI_API_KEY`; otherwise the pipeline runs in
deterministic (graph-query) mode.

Run the tests:

```bash
.venv/bin/python -m pytest tests/ -v --timeout=300
```

Run mutation tests (Phases 7-9):

```bash
.venv/bin/python tests/mutation_test_phases7_9.py
```

---

## 18. Project Structure

```
src/forensicagent/
+- agents/        Agno-based processing agents
|   +- ingestion.py         Parse PDF/DOCX/TXT/image/log (via firecrawl-anydoc)
|   +- quality_control.py   OCR / parse quality gates
|   +- classification.py    Classify document function
|   +- keyword_index.py     BM25 keyword extraction
|   +- fact_extraction.py   SpaCy NER + rules
|   +- evidence_linking.py  Atomic evidence linking
|   +- validation.py        Deterministic rule checks (pre-LLM)
|   +- retrieval.py         Multi-hop GraphRAG (Semantica) + BM25 fallback
|   +- knowledge_base.py    LLM-assisted authoring of KB documents
|   +- context_builder.py   Build evidence-constrained LLM context + AgnoKGToolkit
|   +- assessment.py        Agno LLM (constrained) + AgnoDecisionKit
|   +- grounding.py         Verify LLM output against evidence
|   +- reporting.py         Drafting-matrix report
|   +- review.py            Human-in-the-loop review
+- domains/       Pluggable domain configs (rules + KB paths)
|   +- general.json  legal.json  cyber.json  financial.json  tax.json
+- models/        Evidence, Fact, Finding, Source, Requirement, Relationship
+- pipeline/      Orchestration + Semantica integration
|   +- orchestrator.py         ForensicPipeline master class
|   +- graph.py               Evidentiary knowledge graph (NetworkX + ContextGraph)
|   +- lmdb_store.py           LMDB-backed volatile persistence (legacy fallback)
|   +- semantica_backend.py    SemanticaBackend factory (S-GRAPH, S-MEMORY)
|   +- provenance.py           ProvenanceTracker (S-PROV)
|   +- dedup.py                EntityDeduplicator (S-DEDUP)
|   +- conflicts.py            ConflictScanner (S-CONFLICT)
|   +- datalog_rules.py        DatalogValidator + JSON-to-Datalog translation (S-REASON)
|   +- semantica_retrieval.py  Multi-hop GraphRAG wrapper (S-RETRIEVE)
|   +- semantica_assessment.py AgnoDecisionKit wrapper (S-ASSESS, S-DECISION)
|   +- semantica_query.py      AgnoKGToolkit wrapper (S-QUERY)
|   +- prov_export.py          PROV-O RDF export (S-EXPORT)
+- utils/         BM25 wrapper, SpaCy wrappers, file parsers
```

---

## 19. Adding a New Forensic Domain

Create `domains/<name>.json` with `requirements` and `rules`:

```json
{
  "name": "tax",
  "label": "Steuerforensik",
  "requirements": [
    {"domain": "tax", "description": "Steuernummer des Steuerpflichtigen", "required_fact_types": ["PERSON", "TAX_CODE"]}
  ],
  "rules": [
    {"id": "tax-1", "name": "Steuernummer vorhanden", "fact_types": ["TAX_CODE"],
     "check": "type:TAX_CODE", "severity": "error"}
  ]
}
```

Point a knowledge base (KB) directory of `.json` / `.txt` / `.md` files at the pipeline
via `kb_dirs`. Then:

```python
ForensicPipeline(case_id, domain="tax", kb_dirs=["sample_cases/tax_001/domains/tax"])
```

---

## 20. Authoring KB Documents (LLM-assisted)

The `KnowledgeBaseAgent` helps a forensic professional author KB documents through
question-and-answer with the LLM:

```python
with ForensicPipeline(case_id="C", kb_dirs=["domains/cyber"]) as p:
    result = p.build_kb_document(
        "Eine IP-Adresse ist nur verwertbar, wenn sie mit einem Log-Eintrag verknuepft ist.",
        domain="cyber",
    )
    # result["document"] is a structured KB entry (id/title/body/tags)
    # result["path"] is the written .json file
```

- The LLM structures the free-form answer into a JSON KB entry.
- The document is written to `kb_dirs` and the BM25 retrieval index is re-indexed so it
  is immediately searchable.
- Without an `OPENAI_API_KEY`, the agent stores the raw text deterministically.

---

## 21. Extending Extraction

Entity patterns live in `utils/spacy_utils.py` (`extract_domain_entities`). Add a regex
or pattern per entity type. The `de_dep_news_trf` model handles German and English;
custom regex fallbacks compensate for NER on structured documents.

Supported entity types: PERSON, ORG, DATE, GERMAN_DATE, AMOUNT, TAX_CODE, TAX_ID, IBAN,
EMAIL, URL, IP_ADDRESS, PHONE, DEVICE_ID, TIMESTAMP, COURT_REF, ACCOUNT.

---

## 22. Tests

The test suite covers BM25 indexing, the evidentiary graph and LMDB persistence, fact
extraction and evidence linking, classification, quality control, keyword extraction,
the end-to-end pipeline, grounding, knowledge-base assistant, Semantica graph adapter,
provenance tracking, entity deduplication, conflict detection, Datalog validation,
PROV-O export, Semantica retrieval (GraphRAG), Semantica assessment (decision tracking),
Semantica KG query, and agent integration.

```
75 tests, 0 skipped
9/9 mutation tests killed (Phases 7-9)
4 real-data cases: legal, cyber, financial, tax
```

```bash
.venv/bin/python -m pytest tests/ -v --timeout=300
```

---

## License

MIT

---

## Note of Thanks

The inspiration for this system is the article:

*AI Forensic Agents: how a pipeline can read a case file, verify evidence, and help draft a Legal Document* — Andrea Belvedere.