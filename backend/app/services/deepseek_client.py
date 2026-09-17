from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from backend.app.core.config import get_settings


@dataclass(slots=True)
class DeepSeekResponse:
    raw_text: str
    json_data: dict | None = None


class DeepSeekClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.model = settings.deepseek_model

    async def extract_json(self, system_prompt: str, user_prompt: str) -> DeepSeekResponse | None:
        if not self.api_key:
            return None

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            raw_text = data["choices"][0]["message"]["content"]
            try:
                json_data = json.loads(raw_text)
            except json.JSONDecodeError:
                json_data = None
            return DeepSeekResponse(raw_text=raw_text, json_data=json_data)
