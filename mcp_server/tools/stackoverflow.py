from __future__ import annotations

import re
from typing import Any, Dict, List
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

import logging
logging.basicConfig(level=logging.INFO)

STACKEXCHANGE_API_BASE = "https://api.stackexchange.com/2.3"
CUSTOM_CA_BUNDLE = "C:/Users/shiri/Desktop/my_ca.pem"

async def _fetch_answer_content(client: httpx.AsyncClient, answer_id: int) -> Dict[str, Any] | None:
    """Fetch the content of a specific answer by its ID."""
    params = {
        "order": "desc",
        "sort": "activity",
        "site": "stackoverflow",
        "filter": "withbody",  # Include answer body in response
    }
    
    url = f"{STACKEXCHANGE_API_BASE}/answers/{answer_id}"
    logging.info("Step: Fetching answer content for answer_id=%s", answer_id)
    logging.info("Making request to %s", url)
    
    try:
        response = await client.get(url, params=params)
        logging.info("Response status: %s", response.status_code)
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        if items:
            logging.info("Successfully fetched answer content for answer_id=%s", answer_id)
            return items[0]
        else:
            logging.warning("No items found in response for answer_id=%s", answer_id)
    except httpx.HTTPError as e:
        logging.error("HTTP error fetching answer content: %s - %s", type(e).__name__, str(e))
    except Exception as e:  # noqa: BLE001
        logging.error("Unexpected error fetching answer content: %s", str(e))
    return None

async def _fetch_first_answer(client: httpx.AsyncClient, question_id: int) -> Dict[str, Any] | None:
    """Fetch the first (highest scored) answer for a question."""
    params = {
        "order": "desc",
        "sort": "votes",  # Get highest voted answer first
        "site": "stackoverflow",
        "filter": "withbody",  # Include answer body in response
    }
    
    url = f"{STACKEXCHANGE_API_BASE}/questions/{question_id}/answers"
    logging.info("Step: Fetching first answer for question_id=%s", question_id)
    logging.info("Making request to %s", url)
    
    try:
        response = await client.get(url, params=params)
        logging.info("Response status: %s", response.status_code)
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        if items:
            logging.info("Successfully fetched first answer for question_id=%s", question_id)
            return items[0]  # Return the first (highest scored) answer
        else:
            logging.warning("No answers found for question_id=%s", question_id)
    except httpx.HTTPError as e:
        logging.error("HTTP error fetching first answer: %s - %s", type(e).__name__, str(e))
    except Exception as e:  # noqa: BLE001
        logging.error("Unexpected error fetching first answer: %s", str(e))
    return None

async def _search_stackoverflow_api(full_error: str, limit: int = 3, language: str | None = None) -> List[Dict[str, Any]]:
    """Call the StackExchange (Stack Overflow) search API and return parsed results."""
    params = {
        "order": "desc",
        "sort": "relevance",
        "site": "stackoverflow",
        "q": full_error,
        "pagesize": max(limit * 2, limit),  # get a few extra to filter by accepted answers
    }

    if language:
        params["tagged"] = language
        logging.info("Adding language tag: %s", language)
        
    url = f"{STACKEXCHANGE_API_BASE}/search/advanced"
    logging.info("Step 1: Searching Stack Overflow API")
    logging.info("Search query: %s", full_error[:100] + "..." if len(full_error) > 100 else full_error)
    logging.info("Making request to %s", url)

    async with httpx.AsyncClient(timeout=15.0, verify=CUSTOM_CA_BUNDLE, trust_env=False) as client:
        response = await client.get(url, params=params)
        logging.info("Response status: %s", response.status_code)
        response.raise_for_status()
        data = response.json()
        logging.info("Response data keys: %s", data.keys() if data else "None")

        items = data.get("items", [])
        logging.info("Found %d items in search results", len(items))

        # Prefer questions with an accepted answer, but fall back to others if needed
        with_accepted = [item for item in items if item.get("accepted_answer_id")]
        without_accepted = [item for item in items if not item.get("accepted_answer_id")]
        ordered = with_accepted + without_accepted
        logging.info("Step 2: Processing results - %d with accepted answers, %d without", len(with_accepted), len(without_accepted))

        results: List[Dict[str, Any]] = []
        for idx, item in enumerate(ordered[:limit], 1):
            logging.info("Step 2.%d: Processing result %d of %d", idx, idx, min(limit, len(ordered)))
            title = item.get("title", "")
            score = item.get("score", 0)
            creation_ts = item.get("creation_date")
            creation_date = None
            if isinstance(creation_ts, (int, float)):
                creation_date = datetime.fromtimestamp(creation_ts, tz=timezone.utc).isoformat()

            accepted_answer_id = item.get("accepted_answer_id")
            has_accepted = bool(accepted_answer_id)
            question_id = item.get("question_id")
            logging.info("Question ID: %s, Has accepted answer: %s", question_id, has_accepted)
            
            answer_text = None
            answer_is_accepted = False
            
            if has_accepted:
                # Fetch the accepted answer content
                logging.info("Step 2.%d.1: Fetching accepted answer for question_id=%s", idx, question_id)
                answer_data = await _fetch_answer_content(client, accepted_answer_id)
                if answer_data:
                    answer_text = answer_data.get("body", "")
                    answer_is_accepted = answer_data.get("is_accepted", False)
                    logging.info("Step 2.%d.2: Successfully fetched accepted answer (length: %d chars)", idx, len(answer_text) if answer_text else 0)
                else:
                    logging.warning("Step 2.%d.2: Failed to fetch accepted answer", idx)
                link = f"https://stackoverflow.com/a/{accepted_answer_id}"
            else:
                # Fetch the first answer if available
                if question_id:
                    logging.info("Step 2.%d.1: Fetching first answer for question_id=%s", idx, question_id)
                    answer_data = await _fetch_first_answer(client, question_id)
                    if answer_data:
                        answer_text = answer_data.get("body", "")
                        answer_is_accepted = answer_data.get("is_accepted", False)
                        logging.info("Step 2.%d.2: Successfully fetched first answer (length: %d chars)", idx, len(answer_text) if answer_text else 0)
                    else:
                        logging.warning("Step 2.%d.2: No answer found for question_id=%s", idx, question_id)
                # Fallback to the question link if there is no accepted answer
                link = item.get("link") or f"https://stackoverflow.com/questions/{question_id}"

            result = {
                "question_title": title,
                "has_accepted_answer": has_accepted,
                "link": link,
                "score": score,
                "creation_date": creation_date,
            }
            
            # Add answer content if available
            if answer_text:
                result["answer_text"] = answer_text
                result["answer_is_accepted"] = answer_is_accepted
            else:
                result["answer_text"] = None
                result["answer_is_accepted"] = False

            results.append(result)
            logging.info("Step 2.%d.3: Completed processing result %d", idx, idx)

    logging.info("Step 3: Completed processing all results. Returning %d results", len(results))
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
    """Register the search_stackoverflow tool on the given FastMCP server.
    
    The tool searches Stack Overflow for questions related to error messages or stack traces,
    with optional language filtering to narrow results to specific programming languages.
    """

    @mcp.tool(
        name="search_stackoverflow",
        description=(
            "Searches Stack Overflow for questions related to a given error message or stack trace. "
            "Prefers questions with accepted answers and returns a small, relevant set of results. "
            "Includes the full answer text (accepted answer if available, otherwise the first answer). "
            "Optionally filters results by programming language tag (e.g., 'python', 'javascript', 'java')."
        ),
    )
    async def search_stackoverflow(full_error: str, language: str | None = None) -> Dict[str, Any]:
        """
        Search Stack Overflow for questions related to a full error message or stack trace.

        Args:
            full_error: The full error message or stack trace text.
            language: Optional programming language tag to filter results (e.g., 'python', 'javascript', 'java').
                     If provided, only questions tagged with this language will be returned.
        """
        logging.info("Tool called: search_stackoverflow")
        logging.info("Error message length: %d characters", len(full_error))
        if language:
            logging.info("Language filter: %s", language)
        
        try:
            results = await _search_stackoverflow_api(full_error, limit=3, language=language)
            logging.info("Successfully retrieved %d results from Stack Overflow", len(results))
        except httpx.HTTPError as e:
            # Graceful handling of network / API errors
            logging.error("HTTP error in search_stackoverflow: %s - %s", type(e).__name__, str(e))
            return {
                "error_message": full_error,
                "short_explanation": _build_short_explanation(full_error),
                "results": [],
                "api_error": f"Failed to query Stack Overflow API: {str(e)}",
            }
        except Exception as e:  # noqa: BLE001
            logging.error("Unexpected error in search_stackoverflow: %s", str(e))
            raise

        logging.info("Returning results from search_stackoverflow")
        return {
            "error_message": full_error,
            "short_explanation": _build_short_explanation(full_error),
            "results": results,
        }

def _normalize_error_string(raw_error: str) -> str:
    """Normalize and clean a raw error string by removing file paths, line numbers, timestamps, and noise."""
    logging.info("Step: Normalizing error string")
    logging.info("Raw error length: %d characters, %d lines", len(raw_error), len(raw_error.splitlines()) if raw_error else 0)
    
    if not raw_error:
        logging.warning("Empty raw error string provided")
        return ""
    
    lines = raw_error.splitlines()
    normalized_lines = []
    logging.info("Processing %d lines", len(lines))
    
    # Patterns to remove completely (entire lines)
    # Traceback header lines
    traceback_pattern = re.compile(r'^Traceback\s*\(most recent call last\):', re.IGNORECASE)
    # Python file reference lines: "File "path", line X" or "File <path>, line X"
    file_reference_pattern = re.compile(r'^\s*File\s+["<].*', re.IGNORECASE)
    # Lines that are just indentation (common in tracebacks)
    indentation_only_pattern = re.compile(r'^\s+$')
    
    # Patterns to remove from lines (partial removal)
    # Windows paths: C:\..., D:\..., etc.
    windows_path_pattern = re.compile(r'[A-Za-z]:\\[^\s]+')
    # Unix paths: /path/to/file, ~/path/to/file, ./path/to/file
    unix_path_pattern = re.compile(r'(?:^|\s)(?:~|\.)?/[^\s]+')
    # Line numbers: "line 42", "line:42", "line 42,", "at line 42", etc.
    line_number_pattern = re.compile(r'\b(?:line|Line)\s*:?\s*\d+\b', re.IGNORECASE)
    # Timestamps: various formats
    timestamp_pattern = re.compile(r'\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?')
    # File references with line numbers: "file.py:42", "file.py, line 42"
    file_line_pattern = re.compile(r'[^\s]+\.(?:py|js|ts|java|cpp|c|h|go|rs|rb|php|tsx|jsx):\d+')
    # Common local machine noise patterns
    local_noise_patterns = [
        re.compile(r'File\s+"[^"]+"', re.IGNORECASE),  # File "path"
        re.compile(r'File\s+<[^>]+>', re.IGNORECASE),  # File <path>
        re.compile(r'in\s+<module>', re.IGNORECASE),  # in <module>
    ]
    
    for line in lines:
        # Skip entire lines that are just noise
        if traceback_pattern.match(line):
            logging.info("Skipping traceback header line: %s", line[:50])
            continue
        if file_reference_pattern.match(line):
            logging.info("Skipping file reference line: %s", line[:50])
            continue
        if indentation_only_pattern.match(line):
            continue
        
        # Remove Windows paths
        line = windows_path_pattern.sub('', line)
        # Remove Unix paths
        line = unix_path_pattern.sub('', line)
        # Remove line numbers
        line = line_number_pattern.sub('', line)
        # Remove timestamps
        line = timestamp_pattern.sub('', line)
        # Remove file:line patterns
        line = file_line_pattern.sub('', line)
        # Remove local noise patterns
        for pattern in local_noise_patterns:
            line = pattern.sub('', line)
        
        # Clean up extra whitespace
        line = re.sub(r'\s+', ' ', line).strip()
        
        # Skip empty lines and lines that are mostly noise
        if line and len(line) > 2:
            normalized_lines.append(line)
            logging.info("Keeping line: %s", line[:100] + "..." if len(line) > 100 else line)
    
    # Filter: prioritize error lines (lines containing error types)
    # If we have error lines, keep only those; otherwise keep all normalized lines
    error_line_pattern = re.compile(r'\b([A-Z][a-zA-Z]*(?:Error|Exception|Warning))', re.IGNORECASE)
    error_lines = [line for line in normalized_lines if error_line_pattern.search(line)]
    
    if error_lines:
        logging.info("Found %d error lines, filtering to keep only error lines", len(error_lines))
        normalized_lines = error_lines
    
    # Join lines and do final cleanup
    normalized = '\n'.join(normalized_lines)
    # Remove multiple consecutive newlines
    normalized = re.sub(r'\n{3,}', '\n\n', normalized)
    # Remove leading/trailing whitespace
    normalized = normalized.strip()
    
    logging.info("Normalization complete: %d lines kept (from %d original), final length: %d characters", 
                 len(normalized_lines), len(lines), len(normalized))
    
    return normalized

def _extract_error_signature(normalized_error: str) -> str | None:
    """Extract the main exception/error type from the normalized error string."""
    logging.info("Step: Extracting error signature")
    
    if not normalized_error:
        logging.warning("Empty normalized error, cannot extract signature")
        return None
    
    # Common exception patterns: ValueError, TypeError, KeyError, ImportError, etc.
    # Look for patterns like "ErrorType: message" or "ErrorType(message)" anywhere in the text
    # This pattern matches: ErrorType at word boundary, followed by : or ( or end of line/string
    exception_pattern = re.compile(r'\b([A-Z][a-zA-Z]*(?:Error|Exception|Warning))(?:\s*:|\(|$|\s)', re.IGNORECASE)
    
    # Search in all lines, but prioritize the first line
    all_lines = normalized_error.splitlines()
    logging.info("Checking %d lines for error signature", len(all_lines))
    
    # First try the first line
    if all_lines:
        first_line = all_lines[0]
        logging.info("Checking first line for error signature: %s", first_line[:100] + "..." if len(first_line) > 100 else first_line)
        match = exception_pattern.search(first_line)
        if match:
            signature = match.group(1)
            logging.info("Extracted error signature from first line: %s", signature)
            return signature
    
    # If not found in first line, search all lines
    for idx, line in enumerate(all_lines):
        match = exception_pattern.search(line)
        if match:
            signature = match.group(1)
            logging.info("Extracted error signature from line %d: %s", idx + 1, signature)
            return signature
    
    logging.info("No error signature found")
    return None

def _detect_language(normalized_error: str) -> str | None:
    """Trivially detect the programming language from error patterns."""
    logging.info("Step: Detecting programming language")
    
    if not normalized_error:
        logging.warning("Empty normalized error, cannot detect language")
        return None
    
    error_lower = normalized_error.lower()
    
    # Python-specific patterns - check for common Python exceptions and keywords
    python_patterns = [
        'traceback',
        'python',
        'nameerror',
        'attributeerror',
        'indentationerror',
        'importerror',
        'valueerror',
        'typeerror',
        'keyerror',
        'indexerror',
        'syntaxerror',
        'runtimeerror',
        'ioerror',
        'oserror',
        'filenotfounderror',
        'permissionerror',
        'zerodivisionerror',
        'assertionerror',
        'modulenotfounderror',
        'cannot import',
        'from . import',
        'import ',
    ]
    if any(pattern in error_lower for pattern in python_patterns):
        logging.info("Detected language: python")
        return "python"
    
    # JavaScript/TypeScript patterns
    if any(pattern in error_lower for pattern in ['uncaught', 'undefined is not a function', 'cannot read property']):
        logging.info("Detected language: javascript")
        return "javascript"
    
    # Java patterns
    if any(pattern in error_lower for pattern in ['exception in thread', 'java.lang', 'at java.']):
        logging.info("Detected language: java")
        return "java"
    
    # C/C++ patterns
    if any(pattern in error_lower for pattern in ['segmentation fault', 'core dumped', 'undefined reference']):
        logging.info("Detected language: c")
        return "c"
    
    logging.info("No language detected")
    return None

def register_normalize_error_tool(mcp: FastMCP) -> None:
    """Register the normalize_error tool on the given FastMCP server."""

    @mcp.tool(
        name="normalize_error",
        description=(
            "Normalizes and cleans a raw error string or stack trace by removing file paths, "
            "line numbers, timestamps, and local machine-specific noise. Returns only the essential "
            "error message with the exception type and core error details."
        ),
    )
    async def normalize_error(raw_error: str) -> Dict[str, Any]:
        """
        Normalize and clean a raw error string or stack trace.

        Args:
            raw_error: The full raw error message or stack trace text to normalize.
        """
        logging.info("Tool called: normalize_error")
        logging.info("Raw error length: %d characters", len(raw_error))
        
        normalized = _normalize_error_string(raw_error)
        error_signature = _extract_error_signature(normalized)
        detected_language = _detect_language(normalized)
        
        logging.info("Normalization complete - signature: %s, language: %s", error_signature, detected_language)
        logging.info("Returning normalized error (length: %d characters)", len(normalized))
        
        return {
            "normalized_error": normalized,
            "error_signature": error_signature,
            "detected_language": detected_language,
        }