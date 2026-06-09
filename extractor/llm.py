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


def _extract_json_from_markdown(text: str):
    """Try to extract JSON from a markdown ```json ... ``` code fence."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
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

    # 3. Try last JSON object (from last { to last }) — the actual answer is
    #    usually the LAST JSON blob, while thinking blocks may contain earlier ones.
    last_brace = cleaned.rfind("}")
    if last_brace != -1:
        # Find the matching opening brace by walking backwards
        depth = 0
        start = -1
        for i in range(last_brace, -1, -1):
            ch = cleaned[i]
            if ch == "}":
                depth += 1
            elif ch == "{":
                depth -= 1
            if depth == 0:
                start = i
                break
        if start != -1:
            json_text = cleaned[start:last_brace + 1]
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                pass

    # 4. Fallback: first { to last } (original behavior, less robust)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    json_text = cleaned[start:end + 1]
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
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
        line.strip().lstrip('-*0123456789. ').strip()
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
