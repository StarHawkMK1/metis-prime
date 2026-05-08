from __future__ import annotations

from typing import Literal

TaskType = Literal["ingest_summary", "synthesis_complex", "vision", "lint_check", "graph_traversal"]
Sensitivity = Literal["normal", "private"]
