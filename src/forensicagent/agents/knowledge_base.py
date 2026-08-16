from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from forensicagent.agents.base import BaseAgent

logger = logging.getLogger(__name__)

_AGNO_AVAILABLE = False
try:
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    _AGNO_AVAILABLE = True
except Exception:
    pass


class KnowledgeBaseAgent(BaseAgent):
    """Assists the forensic professional in *building and refining* the
    domain Knowledge Base (KB) through an interactive Q&A with the LLM.

    Whereas ``KnowledgeRetrievalAgent`` *reads* an existing KB, this agent
    *writes* new KB documents.  It runs a guided dialogue:

        1. The professional describes a rule / precedent / procedure.
        2. The LLM turns the answer into a structured KB document
           (JSON: id, title, body, tags).
        3. The agent appends it to a KB file and re-indexes.

    The LLM is optional: without an API key, the agent stores the raw text
    as a ``.md`` KB document so the workflow still works deterministically.
    """

    name = "knowledge_base"

    _KB_EXTENSIONS = (".json", ".txt", ".md")

    def __init__(self, case_id: str, kb_dirs: list[str | Path] | None = None) -> None:
        super().__init__(case_id)
        self._kb_dirs = [Path(d) for d in (kb_dirs or [])]
        self._llm: Agent | None = None
        if _AGNO_AVAILABLE and os.getenv("OPENAI_API_KEY"):
            self._llm = Agent(
                name="forensic-kb-assistant",
                model=OpenAIChat(id="gpt-4o-mini"),
                instructions=[
                    "You help a forensic professional author knowledge-base documents.",
                    "Turn the user's description into a clean, factual KB entry.",
                    "Keep statements precise, neutral, and domain-general.",
                    "Output ONLY valid JSON with keys: id, title, body, tags.",
                ],
                markdown=False,
            )

    # ---- guided dialogue ----

    def draft_from_description(self, description: str, domain: str = "general") -> dict[str, Any]:
        """Convert a professional's free-form description into a KB document."""
        if self._llm is not None:
            prompt = (
                "Turn the following into a structured knowledge-base document "
                f"for the '{domain}' forensic domain. Output ONLY JSON "
                "with keys: id, title, body, tags.\n\nDescription:\n" + description
            )
            try:
                response = self._llm.run(prompt, stream=False)
                raw = response.content if hasattr(response, "content") else str(response)
                doc = self._parse_llm_json(raw)
                if doc and doc.get("body"):
                    return self._ensure_schema(doc)
            except Exception as exc:
                logger.warning("LLM KB drafting failed, falling back to raw: %s", exc)

        # Deterministic fallback: store as a markdown doc.
        slug = self._slugify(description)
        return {
            "id": slug or f"kb-{self.new_id()}",
            "title": slug.replace("-", " ").title() or domain,
            "body": description,
            "tags": [domain],
        }

    def add_document(self, doc: dict[str, Any], file: str | Path | None = None) -> Path:
        """Persist a KB document. Writes JSON (structured) or MD (fallback)."""
        if not self._kb_dirs:
            raise RuntimeError("No kb_dirs configured — pass kb_dirs to KnowledgeBaseAgent.")
        target_dir = self._kb_dirs[0]
        target_dir.mkdir(parents=True, exist_ok=True)
        doc = self._ensure_schema(doc)

        if file is None:
            file = target_dir / f"{self._safe_id(doc['id'])}.json"
        else:
            file = Path(file)

        if file.suffix.lower() == ".json":
            self._append_json(file, doc)
        else:
            file.write_text(doc["body"] + "\n", encoding="utf-8")

        logger.info("KB document written: %s", file)
        return file

    def add_document_from_description(
        self, description: str, domain: str = "general"
    ) -> tuple[dict[str, Any], Path]:
        doc = self.draft_from_description(description, domain)
        path = self.add_document(doc)
        return doc, path

    # ---- helpers ----

    def _ensure_schema(self, doc: dict[str, Any]) -> dict[str, Any]:
        doc.setdefault("id", f"kb-{self.new_id()}")
        doc.setdefault("title", doc["id"].replace("_", " ").title())
        doc.setdefault("body", "")
        doc.setdefault("tags", [])
        return doc

    def _append_json(self, file: Path, doc: dict[str, Any]) -> None:
        items: list[dict[str, Any]] = []
        if file.exists():
            with open(file) as f:
                data = json.load(f)
            items = data if isinstance(data, list) else data.get("items", [])
        # Replace by id if it already exists.
        items = [it for it in items if it.get("id") != doc["id"]]
        items.append(doc)
        with open(file, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
            f.write("\n")

    @staticmethod
    def _parse_llm_json(raw: str) -> dict[str, Any] | None:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    @staticmethod
    def _slugify(text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
        return slug[:64]

    @staticmethod
    def _safe_id(text: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_\-]+", "_", text)

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}
