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
        "temperature": 0.1,
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


def chat_completion(messages, max_tokens=None, temperature=0.1):
    api_base = os.getenv("VL_API_BASE", "http://127.0.0.1:8080/v1")
    model_name = os.getenv("VL_MODEL", "llava")
    timeout_val = int(os.getenv("LLM_TIMEOUT", 120))
    retry_count = max(int(os.getenv("LLM_RETRIES", 1)), 0)
    enable_thinking = os.getenv("LLM_ENABLE_THINKING", "false").lower() == "true"

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer not-needed"
    }

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": enable_thinking}
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

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


def _parse_json_output(raw_text):
    if not isinstance(raw_text, str):
        return None
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    json_text = raw_text[start:end+1]
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
    response = chat_completion(messages, max_tokens=200)
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
    response = chat_completion(messages, max_tokens=256)
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
