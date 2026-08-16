from __future__ import annotations

import logging

from forensicagent.pipeline.orchestrator import ForensicPipeline

__version__ = "0.1.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(name)s: %(message)s",
)


def main() -> None:
    print("forensicagent — general-purpose AI forensic agent pipeline")


if __name__ == "__main__":
    main()
