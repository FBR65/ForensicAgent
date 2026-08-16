# ForensicAgent

A general-purpose AI forensic agent pipeline applicable to any forensic activity:
legal case files, cyber-incident investigations, financial fraud analysis, insurance
claims, medical-examiner reports, and other investigation types.

The system is built with **Agno** (agent framework), **SpaCy** (`de_dep_news_trf`),
**BM25** (`rank-bm25`), and **LMDB** for volatile per-session case storage. Document
ingestion is handled by **`firecrawl-anydoc`** (`anydoc`) — a fully local
document-to-Markdown converter that requires no API key and no external service.

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
   │
   ├─ 1. Ingestion        Parse doc/docx/odt/rtf/epub/pdf/ppt/xls/csv (anydoc), TXT, OCR
   ├─ 2. Quality Control  Measure OCR / parse quality
   ├─ 3. Classification   Categorise by evidentiary function
   ├─ 4. Keyword Index    BM25 index of every source
   ├─ 5. Fact Extraction  SpaCy NER + custom entity rules
   ├─ 6. Evidence Linking Atomic evidence -> fact edges
   ├─ 7. Graph Build      Case knowledge graph (NetworkX + LMDB)
   ├─ 8. Validation       Deterministic checks and quality gates
   ├─ 9. Knowledge RAG    Retrieve domain rules / precedents
   ├─10. Context Build    Construct controlled LLM context
   ├─11. Assessment       LLM reasoning within evidence perimeter
   ├─12. Grounding        Verify LLM output against evidence
   ├─13. Reporting        Section-by-section draft + audit
   └─14. Review           Human-in-the-loop corrections
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
| 7 | **ValidationAgent** | Rule-based fact verification (deterministic, pre-LLM) |
| 8 | **KnowledgeRetrievalAgent** | RAG retrieval from the persistent domain knowledge base (BM25) |
| 9 | **KnowledgeBaseAgent** | LLM-assisted authoring of KB documents via Q&A |
|10 | **ContextBuilderAgent** | Assemble the controlled context window for the LLM |
|11 | **AssessmentAgent** | LLM reasoning constrained by evidence only (or deterministic fallback) |
|12 | **GroundingAgent** | Post-generation verification of every claim against evidence |
|13 | **ReportingAgent** | Section-by-section report assembly from a drafting matrix |
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
  - id, case_id, type (PERSON / AMOUNT / DATE / TAX_ID / ...)
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

CaseGraph     (volatile, per-session)
  - nodes: Case | Source | Fact | Evidence | Requirement | Finding | Relationship
  - edges: HAS_SOURCE, HAS_FACT, SUPPORTS, CONTAINS, HAS_EVIDENCE, REQUIRES, SATISFIES
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
| **Case Graph** | Volatile (LMDB) | Case-specific evidence, facts, findings | Read-write; destroyed on session end |
| **Domain KB** | Persistent (BM25) | Statutes, procedures, protocols, templates, checklists | Read-only; shared across cases |

This separation guarantees that client / case data is never mixed into general knowledge.
One client's case must never become a source for another client. The case file lives in a
volatile session: deletion removes the graph, excerpts, and sensitive data; legal sources
remain separate.

---

## 6. Core Principles

1. **Evidence-first**: facts are only usable if they trace to atomic evidence
   (Fact -> Evidence -> Source) in the case graph.
2. **Deterministic before probabilistic**: rule-based validation runs before any LLM
   invocation.
3. **Two knowledge stores**:
   - Volatile case graph (LMDB), destroyed on `close()` / `destroy()`.
   - Persistent domain KB (BM25 index), read-only and shared.
4. **Constrained LLM**: the LLM may only use `CONFIRMED` / `APPROVED` facts; output is
   verified by the `GroundingAgent`.

---

## 7. BM25 — Keyword Extraction and Retrieval

`rank-bm25` is used for two purposes.

1. **Keyword extraction per source**: the top-k BM25-weighted terms become the source's
   keyword vector, stored on the `Source` node. These keywords drive:
   - duplicate detection across the case file,
   - semantic search within the case corpus,
   - fast evidence lookup during grounding.

2. **Domain-KB retrieval**: the persistent KB is tokenised and indexed with BM25. The
   `KnowledgeRetrievalAgent` selects the most relevant domain rules and precedents for
   the current case. Retrieved KB sources explain the rules; they never become evidence
   for the specific case.

---

## 8. SpaCy — NLP Layer

SpaCy (`de_dep_news_trf`, a German transformer model) provides:

- tokenisation and lemmatisation for BM25 indexing,
- NER for persons, organisations, locations, dates, and identifiers,
- sentence segmentation for atomic evidence snippets,
- dependency parsing for relationship extraction.

Because the German model's NER can be unreliable on mixed-language or highly structured
forensic documents, custom regex patterns in `utils/spacy_utils.py`
(`extract_domain_entities`) compensate for TAX_ID, IBAN, email, URL, IP address, phone,
dates, amounts, and structured person fields. SpaCy remains a support library; the LLM
agents handle high-level reasoning.

---

## 9. Deterministic Validation Layer

Before the LLM ever sees data, the `ValidationAgent` runs a declarative rule set stored
as JSON. Each rule carries a `fact_types` filter so it only applies to matching facts.

```
{
  "id": "general-2",
  "name": "Amount Must Have Source",
  "description": "Every monetary amount must have documented evidence",
  "fact_types": ["AMOUNT"],
  "check": "has_evidence",
  "severity": "error"
}
```

Supported `check` operators: `type:<T>`, `min_confidence:<N>`, `regex:<pattern>`,
`has_evidence`. A fact failing an `error` rule is `REJECTED`; failing a `warning` rule
marks it `REQUIRES_REVIEW`.

---

## 10. Controlled LLM Prompt

The `ContextBuilderAgent` assembles a context window containing only usable facts
(`CONFIRMED` / `APPROVED`), the requirement satisfaction map, domain rules, and relevant
KB snippets. The `AssessmentAgent` prompt enforces:

```
You are a forensic reasoning agent.
You may ONLY use facts whose status is CONFIRMED or APPROVED.
For each claim you make, cite the fact id and evidence id that support it.
Never invent amounts, identifiers, courts, or dates.
```

Rejected or unproven data is excluded from the context entirely.

---

## 11. Output Grounding

After the LLM generates text, the `GroundingAgent` verifies the output:

1. Extract every numerical, identifier, court, or date claim.
2. Verify each claim maps to a `CONFIRMED` fact in the graph.
3. Any claim with no evidence path rejects the output and feeds it back into the graph
   as a `REQUIRES_REVIEW` item.

The system does not trust the model; it uses the model and then checks it. A rejected
output produces an operational indication rather than a generic error.

---

## 12. Reporting

The `ReportingAgent` compiles a **Drafting Matrix** — a per-section checklist that maps
each required section to its required facts, the evidence path, and its status.

| Section | Required Facts | Status | Notes |
|---------|----------------|--------|-------|
| Identity | PERSON, TAX_ID | SATISFIED | |
| Liabilities | AMOUNT x 3 | PARTIAL | one amount needs review |

The final output is an **assisted draft + audit report**, not an automated decision.
Sections that are incomplete carry explicit warnings; the professional performs the
final review.

---

## 13. Quick Start

```python
from forensicagent.pipeline.orchestrator import ForensicPipeline

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
    # pipeline.close() destroys the volatile LMDB session.
```

---

## 14. Installation

```bash
uv sync
# The German transformer SpaCy model is installed separately (large download):
uv pip install "https://github.com/explosion/spacy-models/releases/download/de_dep_news_trf-3.8.0/de_dep_news_trf-3.8.0-py3-none-any.whl"
uv pip install -e .
```

Ingestion notes:

- Documents are converted to Markdown locally by `firecrawl-anydoc` (`anydoc.to_markdown`
  / `to_markdown_bytes`) for doc, docx, odt, rtf, epub, pdf, ppt, xls, csv.
- Plain text (`.txt`, `.log`, `.md`) is read directly.
- Raster images (`.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`) fall back to OCR
  (`pytesseract`).

---

## 15. Usage

Run the end-to-end demo (sample insurance-fraud case):

```bash
.venv/bin/python test_pipeline.py
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

---

## 16. Project Structure

```
src/forensicagent/
├── agents/        Agno-based processing agents
│   ├── ingestion.py         Parse PDF/DOCX/TXT/image/log (via firecrawl-anydoc)
│   ├── quality_control.py   OCR / parse quality gates
│   ├── classification.py    Classify document function
│   ├── keyword_index.py     BM25 keyword extraction
│   ├── fact_extraction.py   SpaCy NER + rules
│   ├── evidence_linking.py  Atomic evidence linking
│   ├── validation.py        Deterministic rule checks (pre-LLM)
│   ├── retrieval.py         RAG over domain knowledge base (BM25)
│   ├── knowledge_base.py    LLM-assisted authoring of KB documents
│   ├── context_builder.py   Build evidence-constrained LLM context
│   ├── assessment.py        Agno LLM (constrained) or deterministic
│   ├── grounding.py         Verify LLM output against evidence
│   ├── reporting.py         Drafting-matrix report
│   └── review.py            Human-in-the-loop review
├── domains/       Pluggable domain configs (rules + KB paths)
├── models/        Evidence, Fact, Finding, Source, Requirement
├── pipeline/      Orchestration
│   ├── orchestrator.py      ForensicPipeline master class
│   ├── graph.py             Evidentiary knowledge graph (NetworkX)
│   └── lmdb_store.py        LMDB-backed volatile persistence
└── utils/         BM25 wrapper, SpaCy wrappers, file parsers
```

---

## 17. Adding a New Forensic Domain

Create `domains/<name>.json` with `requirements` and `rules`:

```json
{
  "name": "cyber",
  "label": "Cyber Forensics",
  "requirements": [
    {"description": "Identify suspect device", "required_fact_types": ["IP_ADDRESS", "DEVICE_ID"]}
  ],
  "rules": [
    {"id": "cyber-1", "name": "IP has evidence", "fact_types": ["IP_ADDRESS"],
     "check": "has_evidence", "severity": "error"}
  ]
}
```

Point a knowledge base (KB) directory of `.json` / `.txt` / `.md` files at the pipeline
via `kb_dirs`. Then:

```python
ForensicPipeline(case_id, domain="cyber", kb_dirs=[...])
```

---

## 18. Authoring KB Documents (LLM-assisted)

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

## 19. Extending Extraction

Entity patterns live in `utils/spacy_utils.py` (`extract_domain_entities`). Add a regex
or pattern per entity type. The `de_dep_news_trf` model handles German and English;
custom regex fallbacks compensate for NER on structured documents.

---

## 20. Tests

The test suite covers BM25 indexing, the evidentiary graph and LMDB persistence, fact
extraction and evidence linking, classification, quality control, keyword extraction,
the end-to-end pipeline, grounding, and the knowledge-base assistant.

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
