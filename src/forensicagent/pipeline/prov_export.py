"""PROV-O export wrapper for ForensicAgent (S-EXPORT).

Exports the case graph as W3C PROV-O Turtle/JSON-LD using Semantica's RDFExporter.
The exporter writes to a file; we read it back and return the content.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def export_provenance(
    context_graph: Optional[Any],
    rdf_exporter: Optional[Any],
    format: str = "turtle",
) -> str:
    """Export case graph as PROV-O in the given format.

    Args:
        context_graph: Semantica ContextGraph instance.
        rdf_exporter: Semantica RDFExporter instance.
        format: Output format -- "turtle", "json-ld", "xml".

    Returns:
        RDF string in the requested format, or empty string if unavailable.
    """
    if context_graph is None or rdf_exporter is None:
        return ""

    try:
        kg = context_graph.to_kg_dict()
    except Exception as exc:
        logger.warning("to_kg_dict failed: %s", exc)
        return ""

    # RDFExporter.export() writes to a file, so use a temp file and read back.
    suffix = {".ttl": ".ttl", "turtle": ".ttl", "xml": ".rdf", "json-ld": ".jsonld"}.get(format, ".ttl")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="w") as f:
        tmp_path = f.name

    try:
        rdf_exporter.export(kg, file_path=tmp_path, format=format)
        content = Path(tmp_path).read_text(encoding="utf-8")
        logger.info("PROV-O export: %d chars in %s format", len(content), format)
        return content
    except Exception as exc:
        logger.warning("PROV-O export failed: %s", exc)
        return ""
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def export_provenance_to_file(
    context_graph: Optional[Any],
    rdf_exporter: Optional[Any],
    path: str,
    format: str = "turtle",
) -> bool:
    """Export PROV-O to a file. Returns True on success."""
    if context_graph is None or rdf_exporter is None:
        return False

    try:
        kg = context_graph.to_kg_dict()
        rdf_exporter.export(kg, file_path=path, format=format)
        logger.info("PROV-O written to %s", path)
        return True
    except Exception as exc:
        logger.warning("PROV-O file write failed: %s", exc)
        return False