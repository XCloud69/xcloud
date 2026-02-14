from ddgs import DDGS


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web using DuckDuckGo and return results.
    Returns a list of dicts with 'title', 'href', and 'body' keys.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return results
    except Exception as e:
        return [{"error": str(e)}]


def format_search_results_as_context(query: str, max_results: int = 5) -> str:
    """
    Search the web and format results as context text for the LLM.
    """
    results = web_search(query, max_results)

    if not results:
        return "No web search results found."
    if "error" in results[0]:
        return f"Web search failed: {results[0]['error']}"
    context_parts = []
    for i, result in enumerate(results, 1):
        context_parts.append(
            f"[Web Source {i}]\n"
            f"Title: {result.get('title', 'N/A')}\n"
            f"URL: {result.get('href', 'N/A')}\n"
            f"Snippet: {result.get('body', 'N/A')}\n"
        )
    return "\n".join(context_parts)
