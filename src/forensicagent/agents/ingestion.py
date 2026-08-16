from __future__ import annotations

import logging
from pathlib import Path

from forensicagent.agents.base import BaseAgent
from forensicagent.models import Source, SourceStatus
from forensicagent.utils.parsers import parse_file, detect_mime

logger = logging.getLogger(__name__)


class IngestionAgent(BaseAgent):
    name = "ingestion"

    def ingest_files(self, paths: list[str]) -> list[Source]:
        sources: list[Source] = []
        for path_str in paths:
            path = Path(path_str)
            if not path.exists():
                logger.warning("File not found: %s", path_str)
                continue
            text, mime, ocr_used = parse_file(path)
            source = Source(
                id=f"S-{uuid_short()}",
                path=str(path),
                mime=mime,
                raw_text=text,
                ocr_used=ocr_used,
                metadata={"filename": path.name, "file_size": path.stat().st_size},
            )
            sources.append(source)
            logger.info("Ingested %s (%d chars, mime=%s)", path.name, len(text), mime)
        return sources

    def run(self, *args, **kwargs):
        return {"status": "ok", "data": {}}


def uuid_short() -> str:
    import uuid
    return uuid.uuid4().hex[:8]
