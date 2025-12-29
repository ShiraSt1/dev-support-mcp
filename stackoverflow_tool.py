from __future__ import annotations

from typing import Any, Dict, List
import httpx
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP


STACKEXCHANGE_API_BASE = "https://api.stackexchange.com/2.3"


async def _search_stackoverflow_api(full_error: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Call the StackExchange (Stack Overflow) search API and return parsed results."""
    params = {
        "order": "desc",
        "sort": "relevance",
        "site": "stackoverflow",
        "q": full_error,
        "pagesize": max(limit * 2, limit),  # get a few extra to filter by accepted answers
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{STACKEXCHANGE_API_BASE}/search/advanced", params=params)
        response.raise_for_status()
        data = response.json()

    items = data.get("items", [])

    # Prefer questions with an accepted answer, but fall back to others if needed
    with_accepted = [item for item in items if item.get("accepted_answer_id")]
    without_accepted = [item for item in items if not item.get("accepted_answer_id")]
    ordered = with_accepted + without_accepted

    results: List[Dict[str, Any]] = []
    for item in ordered[:limit]:
        title = item.get("title", "")
        score = item.get("score", 0)
        creation_ts = item.get("creation_date")
        creation_date = None
        if isinstance(creation_ts, (int, float)):
            creation_date = datetime.fromtimestamp(creation_ts, tz=timezone.utc).isoformat()

        accepted_answer_id = item.get("accepted_answer_id")
        has_accepted = bool(accepted_answer_id)
        if has_accepted:
            link = f"https://stackoverflow.com/a/{accepted_answer_id}"
        else:
            # Fallback to the question link if there is no accepted answer
            link = item.get("link") or f"https://stackoverflow.com/questions/{item.get('question_id')}"

        results.append(
            {
                "question_title": title,
                "has_accepted_answer": has_accepted,
                "link": link,
                "score": score,
                "creation_date": creation_date,
            }
        )

    return results


def _build_short_explanation(full_error: str) -> str:
    """Create a short, high-level explanation from the error text."""
    if not full_error:
        return "No error text was provided."

    first_line = full_error.strip().splitlines()[0]
    first_line = first_line.strip()
    if len(first_line) > 220:
        first_line = first_line[:217].rstrip() + "..."

    return f"A search was performed on Stack Overflow using this error: \"{first_line}\"."


def register_stackoverflow_tool(mcp: FastMCP) -> None:
    """Register the search_stackoverflow tool on the given FastMCP server."""

    @mcp.tool(
        name="search_stackoverflow",
        description=(
            "Searches Stack Overflow for questions related to a given error message or stack trace. "
            "Prefers questions with accepted answers and returns a small, relevant set of results."
        ),
    )
    async def search_stackoverflow(full_error: str) -> Dict[str, Any]:
        """
        Search Stack Overflow for questions related to a full error message or stack trace.

        Args:
            full_error: The full error message or stack trace text.
        """
        try:
            results = await _search_stackoverflow_api(full_error, limit=3)
        except httpx.HTTPError as e:
            # Graceful handling of network / API errors
            return {
                "error_message": full_error,
                "short_explanation": _build_short_explanation(full_error),
                "results": [],
                "api_error": f"Failed to query Stack Overflow API: {str(e)}",
            }

        return {
            "error_message": full_error,
            "short_explanation": _build_short_explanation(full_error),
            "results": results,
        }


