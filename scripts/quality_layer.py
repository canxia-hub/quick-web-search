from __future__ import annotations

import urllib.parse
from typing import Any

from authority_calibration import authority_breakdown, authority_score
from http_utils import keyword_overlap_score
from query_understanding import build_query_profile, focus_overlap_score
from source_adapter import NormalizedDocument

SOURCE_BASE = {
    "official": 0.90,
    "academic": 0.86,
    "newsroom": 0.72,
    "community": 0.60,
    "aggregator": 0.40,
}

HINT_BOOSTS = {
    "official_repo": 0.10,
    "academic_paper": 0.10,
    "citation_indexed": 0.06,
    "github_repo": 0.04,
    "hn_discussion": 0.03,
    "arxiv_preprint": 0.02,
    "official_docs": 0.10,
    "primary_source": 0.07,
    "product_page": 0.03,
    "vendor_blog": 0.01,
}

DOMAIN_BOOSTS = {
    "github.com": 0.08,
    "arxiv.org": 0.10,
    "semanticscholar.org": 0.08,
    "news.ycombinator.com": 0.03,
    "wikipedia.org": 0.03,
}

SUSPICIOUS_PATTERNS = [
    "assistant_response_preferences",
    "user_interaction_metadata",
    "notable_past_conversation_topic_highlights",
    "helpful_user_insights",
]

COMPARISON_TERMS = {"对比", "比较", "vs", "versus", "comparison", "compare"}
TREND_TERMS = {"trend", "trends", "趋势", "发展", "recent", "latest", "变化", "演进", "2024", "2025", "2026"}
RISK_TERMS = {"risk", "risks", "controversy", "controversies", "争议", "风险", "限制", "limitations", "trade-off", "tradeoffs", "security", "privacy", "verification"}
EXAMPLE_TERMS = {"example", "examples", "案例", "项目", "project", "projects", "repository", "repo", "tool", "assistant"}
DEFINITION_TERMS = {"what is", "definition", "定义", "范围", "边界", "assistant", "tool", "coding assistant"}


def domain_of(url: str) -> str:
    return (urllib.parse.urlparse(url).netloc or "").lower()


def credibility_score(doc: NormalizedDocument) -> float:
    domain = domain_of(doc.canonical_url or doc.url)
    score = max(SOURCE_BASE.get(doc.source_type, 0.5), authority_score(domain, doc.source_type, doc.credibility_hints))
    for hint in doc.credibility_hints:
        score += HINT_BOOSTS.get(hint, 0.0)
    score += DOMAIN_BOOSTS.get(domain, 0.0)
    if doc.author:
        score += 0.02
    if doc.published_at:
        score += 0.02
    score += min(sum(v for v in doc.engagement.values() if isinstance(v, (int, float))) / 100000.0, 0.08)
    return max(0.0, min(score, 0.99))


def language_region_fit(query: str, doc: NormalizedDocument) -> float:
    profile = build_query_profile(query)
    score = 0.0
    if "en" in doc.language.lower() and doc.platform in {"searxng", "web"}:
        score += 0.06
    text = f"{doc.title} {doc.snippet} {doc.body}".lower()
    for region_hint in profile.region_hints:
        if region_hint.lower() in text:
            score += 0.05
    return min(score, 0.18)


def suspicious_text_penalty(doc: NormalizedDocument) -> float:
    text = f"{doc.title} {doc.snippet} {doc.body}".lower()
    penalty = 0.0
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern in text:
            penalty += 0.25
    if text.count("{") + text.count("}") > 20:
        penalty += 0.12
    if len(text) > 2000:
        penalty += 0.08
    return min(penalty, 0.7)


def content_completeness_bonus(doc: NormalizedDocument) -> float:
    score = 0.0
    if len((doc.snippet or "").strip()) >= 80:
        score += 0.04
    if len((doc.body or "").strip()) >= 160:
        score += 0.05
    if doc.metadata:
        score += 0.03
    if len(doc.engagement) >= 2:
        score += 0.02
    return min(score, 0.12)


def _question_type(query: str) -> str:
    query_lc = query.lower()
    if any(term in query_lc for term in COMPARISON_TERMS):
        return "product-comparison"
    if any(term in query_lc for term in TREND_TERMS):
        return "trend"
    if any(term in query_lc for term in RISK_TERMS):
        return "risk"
    if any(term in query_lc for term in {"案例", "项目", "证据", "example", "project", "repository", "representative"}):
        return "examples"
    if any(term in query_lc for term in {"定义", "范围", "核心对象", "是什么", "what is", "definition"}):
        return "definition"
    return "generic-search"


def _aspect_overlap(query: str, doc: NormalizedDocument) -> float:
    question_type = _question_type(query)
    text = f"{doc.title} {doc.snippet} {doc.body}".lower()
    if question_type == "risk":
        matched = sum(1 for term in RISK_TERMS if term in text)
        return min(matched / 3.0, 1.0)
    if question_type == "trend":
        matched = sum(1 for term in TREND_TERMS if term in text)
        return min(matched / 3.0, 1.0)
    if question_type == "examples":
        matched = sum(1 for term in EXAMPLE_TERMS if term in text)
        return min(matched / 3.0, 1.0)
    if question_type == "definition":
        matched = sum(1 for term in DEFINITION_TERMS if term in text)
        return min(matched / 3.0, 1.0)
    return 0.0


def query_signal_bonus(query: str, doc: NormalizedDocument) -> float:
    query_lc = query.lower()
    text = f"{doc.title} {doc.snippet} {doc.body}".lower()
    bonus = 0.0
    if any(term in query_lc for term in COMPARISON_TERMS):
        if any(term in text for term in ["compare", "comparison", "versus", "vs", "benchmark", "pricing", "feature"]):
            bonus += 0.08
    if any(term in query_lc for term in TREND_TERMS):
        if doc.published_at:
            bonus += 0.04
        if any(term in text for term in ["trend", "latest", "recent", "2024", "2025", "2026"]):
            bonus += 0.05
    if any(term in query_lc for term in RISK_TERMS):
        if any(term in text for term in ["risk", "limitation", "controvers", "trade-off", "tradeoffs", "constraint", "security", "privacy", "verify", "verification"]):
            bonus += 0.08
    if any(term in query_lc for term in {"案例", "项目", "证据", "example", "project", "repository", "representative"}):
        if any(term in text for term in ["github", "repository", "repo", "extension", "assistant"]):
            bonus += 0.05
    if any(term in query_lc for term in {"定义", "范围", "核心对象", "是什么", "what is", "definition"}):
        if any(term in text for term in ["assistant", "tool", "open-source", "open source", "self-hosted"]):
            bonus += 0.05
    return min(bonus, 0.16)


def query_mismatch_penalty(query: str, doc: NormalizedDocument) -> float:
    text = f"{doc.title} {doc.snippet} {doc.body}"
    focus = focus_overlap_score(query, text)
    aspect_overlap = _aspect_overlap(query, doc)
    query_type = _question_type(query)
    penalty = 0.0
    if focus == 0.0:
        penalty += 0.10
    elif focus < 0.2:
        penalty += 0.04
    if query_type == "risk":
        if aspect_overlap == 0.0:
            penalty += 0.10
        elif aspect_overlap < 0.2:
            penalty += 0.05
    elif query_type == "trend":
        if aspect_overlap == 0.0:
            penalty += 0.07
        elif aspect_overlap < 0.2:
            penalty += 0.03
    elif query_type == "examples" and aspect_overlap == 0.0:
        penalty += 0.05
    elif query_type == "definition" and aspect_overlap == 0.0:
        penalty += 0.04
    return min(penalty, 0.22)


def relevance_score(query: str, doc: NormalizedDocument) -> float:
    text = " ".join([doc.title, doc.snippet, doc.body]).strip()
    lexical = keyword_overlap_score(query, text)
    fit = language_region_fit(query, doc)
    penalty = suspicious_text_penalty(doc)
    completeness = content_completeness_bonus(doc)
    signal_bonus = query_signal_bonus(query, doc)
    mismatch_penalty = query_mismatch_penalty(query, doc)
    return max(0.0, lexical + fit + completeness + signal_bonus - mismatch_penalty - penalty)


def combined_score(query: str, doc: NormalizedDocument) -> float:
    rel = relevance_score(query, doc)
    cred = credibility_score(doc)
    engagement = min(sum(v for v in doc.engagement.values() if isinstance(v, (int, float))) / 5000.0, 0.12)
    penalty = suspicious_text_penalty(doc)
    mismatch_penalty = query_mismatch_penalty(query, doc)
    return max(0.0, rel * 0.58 + cred * 0.30 + engagement * 0.08 + content_completeness_bonus(doc) * 0.04 - penalty * 0.35 - mismatch_penalty * 0.28)


def annotate_documents(query: str, documents: list[NormalizedDocument]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for doc in documents:
        rel = relevance_score(query, doc)
        cred = credibility_score(doc)
        combined = combined_score(query, doc)
        fit = language_region_fit(query, doc)
        suspicious = suspicious_text_penalty(doc)
        completeness = content_completeness_bonus(doc)
        signal_bonus = query_signal_bonus(query, doc)
        mismatch_penalty = query_mismatch_penalty(query, doc)
        domain = domain_of(doc.canonical_url or doc.url)
        authority = authority_breakdown(domain, doc.source_type, doc.credibility_hints)
        payload = doc.to_dict()
        payload["quality"] = {
            "relevance": round(rel, 4),
            "credibility": round(cred, 4),
            "combined": round(combined, 4),
            "languageRegionFit": round(fit, 4),
            "suspiciousPenalty": round(suspicious, 4),
            "contentCompleteness": round(completeness, 4),
            "querySignal": round(signal_bonus, 4),
            "queryMismatchPenalty": round(mismatch_penalty, 4),
            "focusOverlap": round(focus_overlap_score(query, f"{doc.title} {doc.snippet} {doc.body}"), 4),
            "domain": domain,
            "authorityTier": authority.get("tier"),
            "authorityLabel": authority.get("ruleLabel"),
            "authorityBreakdown": authority,
        }
        annotated.append(payload)
    annotated.sort(key=lambda item: item["quality"]["combined"], reverse=True)
    return annotated


def lightweight_rerank(query: str, documents: list[NormalizedDocument]) -> list[NormalizedDocument]:
    ranked = sorted(documents, key=lambda doc: combined_score(query, doc), reverse=True)
    filtered = [doc for doc in ranked if combined_score(query, doc) >= 0.18 and suspicious_text_penalty(doc) < 0.45]
    if not filtered:
        filtered = ranked[:3]
    return filtered
