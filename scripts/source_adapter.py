from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class NormalizedDocument:
    doc_id: str
    platform: str
    source_type: str
    title: str
    url: str
    canonical_url: str
    body: str = ""
    snippet: str = ""
    author: str = ""
    published_at: str = ""
    language: str = ""
    engagement: dict[str, Any] = field(default_factory=dict)
    parent_id: str | None = None
    credibility_hints: list[str] = field(default_factory=list)
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
