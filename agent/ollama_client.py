from __future__ import annotations

import requests


class OllamaClient:
    def __init__(
        self,
        model: str = "gemma3:4b",
        base_url: str = "http://127.0.0.1:11434",
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def chat(self, prompt: str, system: str | None = None, timeout: int = 300) -> str:
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
            },
            timeout=timeout,
        )
        response.raise_for_status()

        data = response.json()
        return data["message"]["content"].strip()