from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

EXTRACTION_MODEL = "google/gemma-3-27b-it"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_TOKENS = 1200
RETRY_ATTEMPTS = 2
CONTROLLED_CHAT_FAILURE = "The AI service is temporarily unavailable. Please try again shortly."


class OpenRouterService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.chat_completions_url = f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions"
        api_key = self._require_api_key()
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.settings.openrouter_base_url,
            timeout=10.0,
            max_retries=2,
        )

    async def call_model(
        self,
        task_type: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
    ) -> str:
        api_key = self._require_api_key()
        model = self._resolve_model(task_type)
        last_error: Exception | None = None
        total_attempts = RETRY_ATTEMPTS + 1

        for attempt in range(1, total_attempts + 1):
            logger.info(
                "Calling OpenRouter model='%s' for task_type='%s' attempt=%s/%s",
                model,
                task_type,
                attempt,
                total_attempts,
            )
            try:
                response_text = await self._request_completion(
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                )
                cleaned_response = response_text.strip()
                if not cleaned_response:
                    raise RuntimeError("OpenRouter response content was empty.")
                logger.info(
                    "OpenRouter call succeeded for task_type='%s' model='%s'",
                    task_type,
                    model,
                )
                return cleaned_response
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "OpenRouter call failed for task_type='%s' model='%s' attempt=%s/%s: %s",
                    task_type,
                    model,
                    attempt,
                    total_attempts,
                    exc,
                    exc_info=True,
                )

        logger.error(
            "OpenRouter failed for task_type='%s' model='%s' after %s attempts: %s",
            task_type,
            model,
            total_attempts,
            last_error,
        )
        return self._controlled_failure_response(task_type)

    def call_model_sync(
        self,
        task_type: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        if self.client is None:
            raise RuntimeError("OpenRouter client is not configured.")

        model = self._resolve_model(task_type)
        last_error: Exception | None = None
        total_attempts = RETRY_ATTEMPTS + 1

        for attempt in range(1, total_attempts + 1):
            logger.info(
                "Calling OpenRouter sync model='%s' for task_type='%s' attempt=%s/%s",
                model,
                task_type,
                attempt,
                total_attempts,
            )
            try:
                request_payload: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if response_format is not None:
                    request_payload["response_format"] = response_format

                response = self.client.chat.completions.create(**request_payload)
                cleaned_response = self._extract_openai_text(response).strip()
                if not cleaned_response:
                    raise RuntimeError("OpenRouter response content was empty.")
                logger.info(
                    "OpenRouter sync call succeeded for task_type='%s' model='%s'",
                    task_type,
                    model,
                )
                return cleaned_response
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "OpenRouter sync call failed for task_type='%s' model='%s' attempt=%s/%s: %s",
                    task_type,
                    model,
                    attempt,
                    total_attempts,
                    exc,
                    exc_info=True,
                )

        logger.error(
            "OpenRouter sync failed for task_type='%s' model='%s' after %s attempts: %s",
            task_type,
            model,
            total_attempts,
            last_error,
        )
        return self._controlled_failure_response(task_type)

    async def generate_reply(self, message: str, memories: list[dict]) -> str:
        context = "\n".join(f"- {item['text']}" for item in memories)
        prompt = (
            "You are the Cognitive Twin. Answer clearly and use the memory context when helpful.\n"
            f"Memory context:\n{context or '- No relevant memories yet.'}\n\n"
            f"User message: {message}"
        )

        try:
            return await self.call_model(
                task_type="chat",
                messages=[
                    {"role": "system", "content": "You are a thoughtful digital cognitive twin."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
        except (RuntimeError, ValueError):
            logger.exception("OpenRouter reply generation failed.")
            raise
        except Exception:
            logger.exception("OpenRouter reply generation failed unexpectedly.")
            return self._controlled_failure_response("chat")

    async def _request_completion(
        self,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
    ) -> str:
        async with httpx.AsyncClient(timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS)) as client:
            response = await client.post(
                self.chat_completions_url,
                headers=self._build_headers(api_key),
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": DEFAULT_MAX_TOKENS,
                },
            )

        self._raise_for_error(response)
        return self._extract_text(response.json())

    def _build_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _require_api_key(self) -> str:
        api_key = self.settings.openrouter_api_key.strip()
        if not api_key:
            raise RuntimeError("Missing OPENROUTER_API_KEY. Set it in backend/.env")
        return api_key

    def _resolve_model(self, task_type: str) -> str:
        normalized_task = task_type.strip().lower()
        if normalized_task == "extraction":
            model = EXTRACTION_MODEL
        elif normalized_task == "simulation":
            model = self.settings.default_model
        else:
            model = self.settings.default_model

        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("Model configuration missing")
        return normalized_model

    def _controlled_failure_response(self, task_type: str) -> str:
        normalized_task = task_type.strip().lower()
        if normalized_task == "extraction":
            return json.dumps(
                {
                    "thinking_style": "unknown",
                    "decision_traits": [],
                    "preferences": [],
                    "context": "OpenRouter extraction is temporarily unavailable.",
                }
            )
        if normalized_task == "simulation":
            return json.dumps(
                {
                    "decision": "I would pause until the AI service is available again.",
                    "reasoning": "The simulation model is temporarily unavailable, so this response is a controlled fallback.",
                }
            )
        return CONTROLLED_CHAT_FAILURE

    def _raise_for_error(self, response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error_message = self._extract_error_message(exc.response)
            raise RuntimeError(error_message) from exc

    def _extract_openai_text(self, response: Any) -> str:
        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenRouter response did not include choices.")

        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        if message is None:
            raise RuntimeError("OpenRouter response did not include a message.")

        content = getattr(message, "content", None)
        if isinstance(content, str):
            cleaned = content.strip()
            if cleaned:
                return cleaned

        if isinstance(content, list):
            text_parts = [
                str(getattr(item, "text", item.get("text", "")) if isinstance(item, dict) else getattr(item, "text", ""))
                .strip()
                for item in content
                if (
                    isinstance(item, dict)
                    and item.get("type") == "text"
                ) or getattr(item, "type", None) == "text"
            ]
            cleaned = "\n".join(part for part in text_parts if part).strip()
            if cleaned:
                return cleaned

        raise RuntimeError("OpenRouter response content was empty.")

    def _extract_error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return f"OpenRouter returned HTTP {response.status_code}."

        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return " ".join(message.strip().split())
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return " ".join(message.strip().split())
        return f"OpenRouter returned HTTP {response.status_code}."

    def _extract_text(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenRouter response did not include choices.")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise RuntimeError("OpenRouter response choice format is invalid.")

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("OpenRouter response did not include a message.")

        content = message.get("content")
        if isinstance(content, str):
            cleaned = content.strip()
            if cleaned:
                return cleaned

        if isinstance(content, list):
            text_parts = [
                str(item.get("text", "")).strip()
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            cleaned = "\n".join(part for part in text_parts if part).strip()
            if cleaned:
                return cleaned

        raise RuntimeError("OpenRouter response content was empty.")
