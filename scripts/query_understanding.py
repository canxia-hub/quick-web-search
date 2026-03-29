from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

PLATFORM_LANGUAGE_POLICY = {
    "github": "en",
    "hackernews": "en",
    "arxiv": "en",
    "semantic-scholar": "en",
}

COMPOSITE_ALIAS_RULES = [
    (["开源", "ai", "编码助手"], ["open source ai coding assistant", "ai coding assistant", "coding agent"]),
    (["开源", "代码助手"], ["open source ai code assistant", "code assistant", "coding agent"]),
    (["open", "source", "coding", "assistant"], ["open source ai coding assistant", "ai coding assistant", "coding agent"]),
    (["open", "source", "code", "assistant"], ["open source ai code assistant", "code assistant", "coding agent"]),
    (["browser", "automation", "agent"], ["browser automation agent", "browser agent", "web automation agent"]),
    (["deep", "research", "agent"], ["deep research agent", "research agent", "deep research assistant"]),
    (["deep", "research"], ["deep research", "deep research agent", "research assistant"]),
    (["meeting", "assistant"], ["meeting assistant", "meeting copilot", "meeting agent"]),
]

TERM_ALIAS_MAP = {
    "开源": "open source",
    "生态": "ecosystem",
    "编码助手": "coding assistant",
    "代码助手": "code assistant",
    "编程助手": "programming assistant",
    "deep research": "deep research",
    "research agent": "research agent",
    "browser": "browser",
    "automation": "automation",
    "meeting": "meeting",
    "assistant": "assistant",
    "代理": "agent",
    "智能体": "agent",
    "self-hosted": "self hosted",
    "趋势": "trends",
    "争议": "controversies",
    "限制": "limitations",
    "风险": "risks",
    "论文": "research papers",
    "研究": "research",
    "对比": "comparison",
    "比较": "comparison",
    "主流": "mainstream",
    "产品形态": "product patterns",
    "工作流": "workflow",
    "案例": "cases",
    "项目": "projects",
    "证据": "evidence",
}

REGION_ALIAS_MAP = {
    "中国": ["China", "Chinese"],
    "国内": ["China", "Chinese"],
    "美国": ["United States", "US", "American"],
    "欧洲": ["Europe", "European"],
    "日本": ["Japan", "Japanese"],
    "德国": ["Germany", "German"],
    "全球": ["global", "worldwide"],
    "国际": ["global", "international"],
}

GENERIC_FOCUS_BLACKLIST = {
    "research",
    "state",
    "recent",
    "developments",
    "trend",
    "trends",
    "risk",
    "risks",
    "controversies",
    "limitations",
    "examples",
    "projects",
    "evidence",
    "workflow",
    "comparison",
    "product",
    "patterns",
    "question",
}

FOCUS_PHRASE_HINTS = [
    "coding assistant",
    "code assistant",
    "programming assistant",
    "ai coding assistant",
    "ai code assistant",
    "browser automation",
    "browser agent",
    "meeting assistant",
    "meeting copilot",
    "deep research",
    "research agent",
    "open source",
    "agent",
    "copilot",
    "self hosted",
]


@dataclass
class QueryProfile:
    original: str
    detected_languages: list[str]
    region_hints: list[str]
    english_terms: list[str]
    ascii_terms: list[str]
    focus_terms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", text.lower()) if len(token) > 1]


def detect_languages(text: str) -> list[str]:
    langs: list[str] = []
    if re.search(r"[\u4e00-\u9fff]", text):
        langs.append("zh")
    if re.search(r"[A-Za-z]", text):
        langs.append("en")
    return langs or ["unknown"]


def extract_region_hints(text: str) -> list[str]:
    hints: list[str] = []
    for key, aliases in REGION_ALIAS_MAP.items():
        if key in text:
            hints.extend(aliases)
    return list(dict.fromkeys(hints))


def extract_english_terms(text: str) -> list[str]:
    lowered = text.lower()
    terms: list[str] = []
    for required_terms, expansions in COMPOSITE_ALIAS_RULES:
        if all(term.lower() in lowered for term in required_terms):
            terms.extend(expansions)
    for term, alias in TERM_ALIAS_MAP.items():
        if term.lower() in lowered:
            terms.append(alias)
    return list(dict.fromkeys(terms))


def extract_focus_terms(text: str, english_terms: list[str] | None = None, ascii_terms: list[str] | None = None) -> list[str]:
    english_terms = english_terms or extract_english_terms(text)
    ascii_terms = ascii_terms or re.findall(r"[A-Za-z0-9][A-Za-z0-9\-+/]*", text)

    candidates: list[str] = []
    candidates.extend(term for term in english_terms if any(hint in term.lower() for hint in FOCUS_PHRASE_HINTS))
    candidates.extend(ascii_terms)

    lowered = text.lower()
    if "open source" in lowered:
        candidates.append("open source")
    if "coding assistant" in lowered:
        candidates.append("coding assistant")
    if "code assistant" in lowered:
        candidates.append("code assistant")
    if "copilot" in lowered:
        candidates.append("copilot")
    if "agent" in lowered:
        candidates.append("agent")

    focus_tokens: list[str] = []
    for candidate in candidates:
        for token in _tokenize(candidate):
            if token in GENERIC_FOCUS_BLACKLIST:
                continue
            focus_tokens.append(token)

    return list(dict.fromkeys(focus_tokens))


def build_query_profile(text: str) -> QueryProfile:
    ascii_terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-+/]*", text)
    english_terms = extract_english_terms(text)
    return QueryProfile(
        original=text,
        detected_languages=detect_languages(text),
        region_hints=extract_region_hints(text),
        english_terms=english_terms,
        ascii_terms=ascii_terms,
        focus_terms=extract_focus_terms(text, english_terms=english_terms, ascii_terms=ascii_terms),
    )


def _phrase_priority(phrase: str) -> tuple[int, int]:
    lowered = phrase.lower()
    keywords = [
        "ai",
        "assistant",
        "coding",
        "code",
        "agent",
        "open source",
        "copilot",
        "workflow",
        "self hosted",
        "browser",
        "automation",
        "web",
    ]
    hit_score = sum(1 for keyword in keywords if keyword in lowered)
    return hit_score, len(phrase.split())


def _extract_aspect_terms(text: str) -> list[str]:
    lowered = text.lower()
    aspects: list[str] = []
    if any(marker in lowered for marker in ["风险", "争议", "限制", "risk", "controvers", "limitation"]):
        aspects.extend(["risks", "limitations", "controversies"])
    if any(marker in lowered for marker in ["趋势", "变化", "trend", "recent development", "evolution"]):
        aspects.extend(["trends", "recent developments"])
    if any(marker in lowered for marker in ["案例", "项目", "证据", "example", "project", "evidence"]):
        aspects.extend(["representative projects", "examples"])
    if any(marker in lowered for marker in ["对比", "比较", "compare", "comparison", "差异", "workflow", "产品形态"]):
        aspects.extend(["comparison", "workflow", "product patterns"])
    return list(dict.fromkeys(aspects))


def _build_focus_phrase(profile: QueryProfile) -> str:
    phrase_candidates = [term for term in profile.english_terms if any(hint in term.lower() for hint in FOCUS_PHRASE_HINTS)]
    if phrase_candidates:
        return max(phrase_candidates, key=_phrase_priority)
    if profile.focus_terms:
        return " ".join(profile.focus_terms[:5]).strip()
    if profile.english_terms:
        return max(profile.english_terms, key=_phrase_priority)
    return ""


def build_platform_query(text: str, platform: str) -> str:
    profile = build_query_profile(text)
    policy = PLATFORM_LANGUAGE_POLICY.get(platform, "en")
    if policy == "zh":
        return text

    focus_phrase = _build_focus_phrase(profile)
    aspect_terms = _extract_aspect_terms(text)
    region_terms = profile.region_hints[:1]

    if platform == "github":
        selected = [focus_phrase, *region_terms]
    elif platform == "hackernews":
        selected = [focus_phrase, *aspect_terms[:1], *region_terms]
    elif platform in {"arxiv", "semantic-scholar"}:
        selected = [focus_phrase, *aspect_terms[:2], *region_terms]
    else:
        selected = [focus_phrase, *aspect_terms[:1], *region_terms]

    selected = list(dict.fromkeys([part.strip() for part in selected if part and part.strip()]))
    if selected:
        return " ".join(selected)

    fallback = [*profile.english_terms[:3], *region_terms, *profile.ascii_terms[:3]]
    fallback = list(dict.fromkeys([part.strip() for part in fallback if part and part.strip()]))
    return " ".join(fallback).strip() or text


def focus_overlap_score(query: str, text: str) -> float:
    focus_terms = set(extract_focus_terms(query))
    if not focus_terms:
        return 0.0
    text_terms = set(_tokenize(text))
    overlap = focus_terms & text_terms
    return len(overlap) / max(len(focus_terms), 1)
