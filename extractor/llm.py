import os
import requests

def extract_text_from_image(base64_image_uri: str) -> str:
    """
    Sends the image to a local Vue / Llama.cpp / OpenAI-compatible endpoint.
    Retrieves the extracted text.
    """
    api_base = os.getenv("VL_API_BASE", "http://127.0.0.1:8080/v1")
    model_name = os.getenv("VL_MODEL", "llava")
    timeout_val = int(os.getenv("LLM_TIMEOUT", 120))
    
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

    try:
        response = requests.post(
            f"{api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout_val
        )
        response.raise_for_status()
        
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
        
    except Exception as e:
        print(f"LLM Error: {e}")
        return f"[Error connecting to VL Model: {e}]"
