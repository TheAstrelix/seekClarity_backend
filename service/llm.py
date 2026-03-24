# session_manager/utils.py

import requests
from decouple import config

API_KEY = config("MISTRAL_API_KEY")
API_URL = "https://api.mistral.ai/v1/chat/completions"


def query_mixtral(prompt, max_tokens=500, temperature=0.3):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "open-mixtral-8x7b",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        return data["choices"][0]["message"]["content"]

    except Exception as e:
        return f"Error: {str(e)}"