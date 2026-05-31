import os
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
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer not-needed"
    }

    # Standard OpenAI Vision format
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
        "max_tokens": 2048,
        "temperature": 0.1
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
