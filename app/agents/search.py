"""Gemini Google-Search grounding: returns candidate URLs (blogs, reviews, social) for a query.
We only use it to DISCOVER URLs. Content is then fetched by SafeFetcher and re-verified."""


def make_grounded_search(api_key: str, model: str):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)

    def search(query: str) -> list[str]:
        try:
            resp = client.models.generate_content(
                model=model, contents=query,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
            chunks = resp.candidates[0].grounding_metadata.grounding_chunks or []
            return [c.web.uri for c in chunks if getattr(c, "web", None) and c.web.uri]
        except Exception:
            return []

    return search
