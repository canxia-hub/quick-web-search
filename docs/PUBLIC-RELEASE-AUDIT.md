# Public Release Audit — searxng-web-search

Date: 2026-03-30

## Release scope

This repository publishes a cleaned public version of the `searxng-web-search` skill.

Included:
- `SKILL.md`
- `scripts/authority_calibration.py`
- `scripts/http_utils.py`
- `scripts/quality_layer.py`
- `scripts/query_understanding.py`
- `scripts/searxng_search.py`
- `scripts/source_adapter.py`
- `README.md`
- `.gitignore`

Excluded on purpose:
- old `references/` notes and deployment diaries
- old `assets/settings.example.yml`
- `__pycache__/`
- workspace-only artifacts
- packaged workspace history and unrelated local files

## Sensitive-data audit

Checked for:
- API keys
- bearer tokens
- passwords
- private config files
- local secret placeholders that could be mistaken for real deployment secrets
- user-specific absolute paths

Results:
- No real API keys found
- No bearer tokens found
- No passwords found
- No `openclaw.json` or local runtime config included
- No user-specific absolute Windows home path left in published source

## Sanitization changes before publication

1. Removed old reference documents that contained local-path deployment notes.
2. Removed `assets/settings.example.yml` to avoid carrying a fake secret placeholder (`secret_key`) into the public repo.
3. Removed `__pycache__/` artifacts.
4. Replaced hard-coded local startup paths with `Path.home() / '.openclaw' / 'searxng'` style path construction.
5. Kept the default local endpoint `http://localhost:8888` because it is a non-secret local service default, not a credential.

## Functional verification

Verified locally before publication:
- Python syntax compilation passed
- quick search execution passed
- packaged skill validation passed via `package_skill.py`

## Publication intent

The public repository is intended to expose a reusable OpenClaw skill project, not the full private workspace.
