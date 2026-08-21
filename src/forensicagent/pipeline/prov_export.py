"""PROV-O export wrapper for ForensicAgent (S-EXPORT).

Exports the case graph as W3C PROV-O Turtle/JSON-LD using Semantica's RDFExporter.
"""

from __future__ import annotations

import logging
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
        format: Output format — "turtle", "json-ld", "xml".

    Returns:
        RDF string in the requested format, or empty string if unavailable.
    """
    if context_graph is None or rdf_exporter is None:
        return ""

    try:
        kg = context_graph.to_kg_dict()
        result = rdf_exporter.export(kg, format=format)
        logger.info("PROV-O export: %d chars in %s format", len(str(result)), format)
        return str(result)
    except Exception as exc:
        logger.warning("PROV-O export failed: %s", exc)
        # Fallback: try export_rdf function
        try:
            from semantica.export import export_rdf
            result = export_rdf(kg, format=format)
            return str(result)
        except Exception as exc2:
            logger.warning("PROV-O fallback export failed: %s", exc2)
            return ""


def export_provenance_to_file(
    context_graph: Optional[Any],
    rdf_exporter: Optional[Any],
    path: str,
    format: str = "turtle",
) -> bool:
    """Export PROV-O to a file. Returns True on success."""
    content = export_provenance(context_graph, rdf_exporter, format)
    if not content:
        return False
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("PROV-O written to %s", path)
        return True
    except Exception as exc:
        logger.warning("PROV-O file write failed: %s", exc)
        return False