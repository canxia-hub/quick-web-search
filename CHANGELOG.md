# Changelog

All notable changes to this project will be documented in this file.

## 2.0.0 - 2026-10-04

### Added
- Unified search/read/research/auto/batch/health CLI and shared lightweight core.
- Conditional WeChat/Bilibili/Xiaohongshu/GitHub adapters; body/PDF/subtitle evidence.
- Query variants, stable-ID deduplication, bounded work, cancellation and resumable material packages.
- RSS/WeChat compatibility scripts and portable installation/configuration instructions.

### Fixed
- WeChat normal-click title matching and visible-body readiness.
- Bilibili exact-part CID/login status and character-budgeted complete subtitle evidence.
- Short Xiaohongshu video descriptions remain metadata, not transcripts.

### Boundaries
- Lexical ranking by default; no newly required model/search service or paid API.
- Real representative samples passed; platform limits and coverage gaps remain explicit.
- Existing legacy files remain available.

## 1.2.0 - 2026-08-14

### Added
- `scripts/rss_fetch.py` for RSS/Atom fetching, subscriptions, incremental monitoring, and feed health checks
- `scripts/weixin_search.py` for optional WeChat article/account discovery through Sogou Weixin
- Requests fallback mode for WeChat retrieval when Scrapling is unavailable or intentionally bypassed

### Documentation
- Updated README requirements, quick-start commands, repository layout, and external-service limitations
- Updated the public-release audit to include both new entrypoints and their runtime verification evidence

## 1.1.0 - 2026-04-20

### Added
- **Search Standards Section**: Integrated commercial-grade search methodology into SKILL.md
  - Evidence chain standards with 5-level source classification
  - Source priority hierarchy (official > authoritative > media > secondary > social)
  - Time-sensitivity rules (10% change probability triggers verification)
  - Standard output format (5-part structure: summary, evidence, logic, uncertainties, suggestions)
  - Quality self-check checklist
  - Query rewriting templates (exact/recall/official/temporal/cross)

- **Templates Directory**: Added reusable templates
  - `templates/output-format.md` - Standard output format template with examples
  - `templates/quality-checklist.md` - Quality verification checklist for search results

### Improved
- Better source credibility tracking with explicit type labels
- Uncertainty disclosure guidelines for transparent reporting
- Evidence chain requirements by risk level (low/medium/high)

### Compatibility
- All changes are additive and backward-compatible
- Standards marked as "recommended" (not enforced) for flexibility
