import json
import os
import re
import requests


def _normalize_message_content(content) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                text_part = item
            elif isinstance(item, dict):
                text_part = item.get("text") or item.get("content") or ""
            else:
                text_part = ""

            text_part = text_part.strip()
            if text_part:
                parts.append(text_part)

        return "\n".join(parts).strip()

    return ""


def extract_text_from_image(base64_image_uri: str) -> str:
    """
    Sends the image to a local Vue / Llama.cpp / OpenAI-compatible endpoint.
    Retrieves the extracted text.
    """
    api_base = os.getenv("VL_API_BASE", "http://127.0.0.1:8080/v1")
    model_name = os.getenv("VL_MODEL", "llava")
    timeout_val = int(os.getenv("LLM_TIMEOUT", 120))
    retry_count = max(int(os.getenv("LLM_RETRIES", 1)), 0)
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", 8192))
    enable_thinking = os.getenv("LLM_ENABLE_THINKING", "false").lower() == "true"

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer not-needed"
    }

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract all text from this image exactly as it appears. Do not add any conversational filler. Just the text."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": base64_image_uri
                        }
                    }
                ]
            }
        ],
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": enable_thinking}
    }

    last_error = None

    for _ in range(retry_count + 1):
        try:
            response = requests.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout_val
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            extracted_text = _normalize_message_content(content)
            if not extracted_text:
                raise ValueError("Vision model returned empty text.")

            return extracted_text
        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"VL extraction failed after {retry_count + 1} attempt(s): {last_error}"
    ) from last_error


def chat_completion(messages, max_tokens=None):
    api_base = os.getenv("VL_API_BASE", "http://127.0.0.1:8080/v1")
    model_name = os.getenv("VL_MODEL", "llava")
    timeout_val = int(os.getenv("LLM_TIMEOUT", 120))
    max_tokens_val = max_tokens if max_tokens is not None else int(os.getenv("LLM_MAX_TOKENS", 8192))
    retry_count = max(int(os.getenv("LLM_RETRIES", 1)), 0)
    enable_thinking = os.getenv("LLM_ENABLE_THINKING", "false").lower() == "true"

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer not-needed"
    }

    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tokens_val,
        "chat_template_kwargs": {"enable_thinking": enable_thinking}
    }

    last_error = None
    for _ in range(retry_count + 1):
        try:
            response = requests.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout_val
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return _normalize_message_content(content)
        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"Text completion failed after {retry_count + 1} attempt(s): {last_error}"
    ) from last_error


def _strip_thinking_blocks(text: str) -> str:
    """Remove <think>...</think> blocks that Qwen-style models emit during reasoning."""
    # Remove well-formed think blocks
    result = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Also handle unclosed <think> tag (model started thinking but tag never closed)
    result = re.sub(r"<think>.*", "", result, flags=re.DOTALL)
    return result.strip()


def _find_balanced_json(text: str, start_at: int = 0) -> str | None:
    """Find the first balanced { ... } JSON object in *text*, respecting
    JSON string boundaries (so braces inside "reasoning": "foo {bar} baz"
    don't break the brace counter).  Returns the substring (inclusive of
    both braces) or None."""
    # find the first opening brace
    i = text.find("{", start_at)
    if i == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    n = len(text)

    for j in range(i, n):
        ch = text[j]
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        # not in a string
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    return None


def _extract_json_from_markdown(text: str):
    """Try to extract JSON from a markdown ```json ... ``` code fence.

    Uses string-aware brace matching so braces inside JSON string values
    don't cause premature truncation."""
    fence = re.search(r"```(?:json)?\s*\n?", text)
    if not fence:
        return None
    body_start = fence.end()
    candidate = _find_balanced_json(text, start_at=body_start)
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _parse_json_output(raw_text):
    if not isinstance(raw_text, str):
        return None

    # 1. Strip thinking blocks first (Qwen models emit these when enable_thinking=true)
    cleaned = _strip_thinking_blocks(raw_text)

    # 2. Try markdown code-fence extraction
    result = _extract_json_from_markdown(cleaned)
    if result is not None:
        return result

    # 3. Try last JSON object — walk backwards finding } then match {
    #    to { using string-aware balancing (the actual answer is usually
    #    the LAST JSON blob, while thinking blocks may contain earlier ones).
    for i in range(len(cleaned) - 1, -1, -1):
        ch = cleaned[i]
        if ch != "}":
            continue
        # Walk backwards from each } to find its matching {, respecting strings
        depth = 0
        in_string = False
        escape = False
        for j in range(i, -1, -1):
            c = cleaned[j]
            # When walking backwards, an unescaped " toggles string state
            if escape:
                escape = False
                continue
            if c == '"':
                # Check if this quote is escaped: look backward for odd backslashes
                bs = 0
                k = j - 1
                while k >= 0 and cleaned[k] == "\\":
                    bs += 1
                    k -= 1
                if bs % 2 == 0:  # even backslashes → not escaped
                    in_string = not in_string
                continue
            if in_string:
                continue
            if c == "}":
                depth += 1
            elif c == "{":
                depth -= 1
            if depth == 0:
                start = j
                json_text = cleaned[start:i + 1]
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    break  # try the next }
        break  # only try the very last }, then fall through

    # 4. Fallback: first { to its matching } using string-aware matching
    candidate = _find_balanced_json(cleaned)
    if candidate:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    return None


def generate_search_queries(title):
    prompt = (
        "Generate 2 to 3 concise DuckDuckGo search queries to find the publication year "
        f"for the following book title:\n\n{title}\n\n"
        "Output one query per line only."
    )
    messages = [
        {"role": "system", "content": "You are a concise search query generation assistant."},
        {"role": "user", "content": prompt}
    ]
    response = chat_completion(messages)
    lines = [
        re.sub(r'^[\d.\-*\s]+', '', line.strip())
        for line in response.splitlines()
        if line.strip()
    ]
    return [line for line in lines if line][:3]


def extract_year_from_results(title, snippets):
    prompt = (
        "You are given a book title and search result snippets. Identify the most likely publication year "
        "for that work. If you cannot determine a year, return null for year. Always output valid JSON exactly in the format:\n"
        "{\"year\": <number|null>, \"confidence\": \"low|medium|high\", \"reasoning\": \"...\"}\n\n"
        f"Title: {title}\n\n"
        "Search snippets:\n"
        f"{snippets}\n\n"
        "Be concise and honest about your confidence."
    )
    messages = [
        {"role": "system", "content": "You are a structured extraction assistant."},
        {"role": "user", "content": prompt}
    ]
    response = chat_completion(messages)
    parsed = _parse_json_output(response)
    if parsed and isinstance(parsed, dict):
        year = parsed.get("year")
        confidence = parsed.get("confidence") or "low"
        reasoning = parsed.get("reasoning") or "Could not parse model output."
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                year = None
        return {
            "year": year,
            "confidence": confidence,
            "reasoning": reasoning.strip()
        }

    year_match = re.search(r"(19\d{2}|20\d{2})", response)
    year = int(year_match.group(1)) if year_match else None
    confidence = "medium" if year else "low"
    reasoning = (
        "Parsed year from partial model output." if year else
        "Model did not return valid JSON; using fallback heuristics."
    )
    return {
        "year": year,
        "confidence": confidence,
        "reasoning": reasoning
    }
