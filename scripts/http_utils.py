from __future__ import annotations

import hashlib
import html
import re
import urllib.parse


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def sanitize_extracted_text(text: str, max_length: int = 1200) -> str:
    value = html.unescape(text or "")
    value = re.sub(r"\{[^{}]{400,}\}", " [structured content omitted] ", value, flags=re.DOTALL)
    value = re.sub(
        r"assistant_response_preferences|user_interaction_metadata|notable_past_conversation_topic_highlights",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", value)
    value = re.sub(r"([{}\[\]\"']){8,}", " ", value)
    value = normalize_whitespace(value)
    if len(value) > max_length:
        value = value[:max_length].rstrip() + "..."
    return value


def stable_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def canonicalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    filtered_query = [(k, v) for k, v in query if not k.lower().startswith("utm_")]
    normalized = parsed._replace(query=urllib.parse.urlencode(filtered_query), fragment="")
    return urllib.parse.urlunparse(normalized)


def keyword_overlap_score(query: str, text: str) -> float:
    query_terms = {token for token in re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", query.lower()) if len(token) > 1}
    text_terms = {token for token in re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", text.lower()) if len(token) > 1}
    if not query_terms:
        return 0.0
    overlap = query_terms & text_terms
    return len(overlap) / max(len(query_terms), 1)
