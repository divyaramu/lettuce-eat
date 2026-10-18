# Lettuce Eat

Find restaurants where **every** member of a group has sourced, verifiable options (allergies, halal/kosher, vegan/vegetarian/gluten-free). Seattle demo.

## How credibility works
Every claim shown is a **verbatim quote re-found in the fetched page text** (LLM can't invent evidence), with its URL.
Tiers per restriction: `official_verified` > `community_verified` (Reddit/blogs/reviews/social; clearly labelled, "call to confirm") > `questionable` (couldn't verify: call) / `reported_unsafe` (cross-contact warnings).
Venue score = the **weakest** member's tier (so one unfed person sinks a venue).

## Run (sandboxed)
```bash
cp .env.example .env            # add GEMINI_API_KEY; set SOURCE_MODE=live for real web
docker compose --profile test run --rm tests   # offline tests (network disabled)
docker compose up --build                      # app on http://127.0.0.1:8000
```
No Docker? `pip install -r requirements.txt && pytest -q && uvicorn app.main:app`.

## Modes
- `SOURCE_MODE=fixture`: deterministic Seattle-style fixtures, no network, rule extractor.
- `SOURCE_MODE=live`: OSM venues + official sites + Reddit + Gemini-grounded web search; Gemini extracts, verifier checks.

## Safety
SSRF-guarded fetcher (https only, public IPs, redirects re-checked, size/time caps), untrusted text never executed or rendered as HTML,
strict CSP, unguessable tokens, input validation, rate limits, non-root read-only container with no capabilities, secrets only via `.env`.
