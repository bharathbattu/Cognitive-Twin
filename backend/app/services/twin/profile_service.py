from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, cast

from app.models.schemas.twin import TwinProfileResponse
from app.services.memory.memory_service import MemoryService
from app.utils.file_helpers import ensure_directory, safe_slug
from app.utils.session_manager import generate_new_session_id

COGNITIVE_EXTRACTION_ROLE = "cognitive_extraction"
COGNITIVE_PROFILE_ROLE = "cognitive_profile"
TRAINING_STATUS = "training"
DEPLOYED_STATUS = "deployed"
TwinStatus = Literal["training", "deployed"]
MIN_OBSERVATIONS = 8
PROFILE_KEYS = ("thinking_style", "decision_traits", "preferences", "contexts")
INSUFFICIENT_CONTEXT = "The message does not contain enough cognitive evidence."
CONTEXT_SUMMARY_LIMIT = 5
CONTEXT_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")
MEANINGFUL_INPUT_PATTERN = re.compile(r"[a-z0-9']+", flags=re.IGNORECASE)
CONTEXT_STOP_WORDS = {
    "the",
    "user",
    "they",
    "them",
    "their",
    "with",
    "from",
    "that",
    "this",
    "into",
    "when",
    "where",
    "have",
    "has",
    "been",
    "more",
    "less",
    "over",
    "under",
    "about",
}
CONTEXT_CLEANUP_RULES = (
    (re.compile(r"^(?:the user|they)\s+express(?:es)?\s+(?:a\s+)?preference\s+for\s+", flags=re.IGNORECASE), "prefers "),
    (re.compile(r"^(?:the user|they)\s+express(?:es)?\s+", flags=re.IGNORECASE), ""),
    (re.compile(r"^(?:the user|they)\s+prefer(?:s)?\s+", flags=re.IGNORECASE), "prefers "),
    (re.compile(r"^(?:the user|they)\s+value(?:s)?\s+", flags=re.IGNORECASE), "values "),
    (re.compile(r"^(?:the user|they)\s+balance(?:s)?\s+", flags=re.IGNORECASE), "balances "),
    (re.compile(r"^(?:the user|they)\s+seek(?:s)?\s+", flags=re.IGNORECASE), "seeks "),
    (re.compile(r"^(?:the user|they)\s+lean(?:s)?\s+toward\s+", flags=re.IGNORECASE), "leans toward "),
    (re.compile(r"^(?:the user|they)\s+tend(?:s)?\s+to\s+", flags=re.IGNORECASE), "tends to "),
)
logger = logging.getLogger(__name__)


class ProfileService:
    def __init__(self, memory_service: MemoryService, archive_path: Path | None = None) -> None:
        self.memory_service = memory_service
        self.archive_path = archive_path or Path(__file__).resolve().parents[3] / "data" / "json" / "archive"
        ensure_directory(self.archive_path)

    def get_profile(self, session_id: str) -> dict[str, list[str]]:
        latest_profile = self.memory_service.latest_memory(
            session_id=session_id,
            role=COGNITIVE_PROFILE_ROLE,
            metadata_key="profile",
        )
        if latest_profile and isinstance((profile := latest_profile.metadata.get("profile")), dict):
            return self._sanitize_profile(profile)

        extraction_entries = self.memory_service.get_memories(session_id, role=COGNITIVE_EXTRACTION_ROLE)
        extraction_payloads = [
            extraction
            for entry in extraction_entries
            if isinstance((extraction := entry.metadata.get("extraction")), dict)
        ]
        if not extraction_payloads:
            return self._empty_profile()

        profile, _weights = self._build_from_extractions(extraction_payloads)
        return profile

    def update_profile(self, session_id: str, extracted_data: dict[str, Any]) -> dict[str, list[str]]:
        logger.info("Updating profile for session '%s'.", session_id)
        previous_status = self.get_twin_status(session_id)
        twin_status = DEPLOYED_STATUS if self.is_ready_for_deployment(session_id) else TRAINING_STATUS
        deployment_completed = previous_status != DEPLOYED_STATUS and twin_status == DEPLOYED_STATUS
        current_weights = self._get_weights(session_id)
        normalized_extraction = self._normalize_extracted_data(extracted_data)
        if twin_status == DEPLOYED_STATUS:
            merged_weights = self._merge_weights_deployed(current_weights, normalized_extraction)
        else:
            merged_weights = self._merge_weights(current_weights, normalized_extraction)
        profile = self._profile_from_weights(merged_weights)

        self.memory_service.remember(
            session_id=session_id,
            text=self._build_summary(profile, merged_weights),
            metadata={
                "profile": profile,
                "weights": merged_weights,
                "twin_status": twin_status,
                "deployment_completed": deployment_completed,
            },
            role=COGNITIVE_PROFILE_ROLE,
        )
        if deployment_completed:
            logger.info("Twin reached deployment threshold for session '%s'.", session_id)
        logger.info("Profile updated for session '%s' with twin_status='%s'.", session_id, twin_status)
        return profile

    def transition_lifecycle_if_deployed(self, session_id: str) -> dict[str, Any]:
        status = self.get_twin_status(session_id)
        if status != DEPLOYED_STATUS:
            logger.info("Lifecycle transition skipped for session '%s': twin is still training.", session_id)
            return {
                "message": "Cognitive Twin is still training",
                "new_session_id": None,
                "previous_session_archived": False,
            }

        archived = self._archive_session_snapshot(session_id)
        if not archived:
            logger.error("Lifecycle transition blocked for session '%s': archive failed.", session_id)
            return {
                "message": "Deployment completed but archive failed",
                "new_session_id": None,
                "previous_session_archived": False,
            }

        new_session_id = generate_new_session_id()
        self.memory_service.reset_session(new_session_id)
        self.memory_service.remember(
            session_id=new_session_id,
            text="Cognitive Twin session initialized.",
            metadata={
                "profile": self._empty_profile(),
                "weights": self._empty_weights(),
                "twin_status": TRAINING_STATUS,
                "lifecycle_event": "session_initialized",
            },
            role=COGNITIVE_PROFILE_ROLE,
        )

        logger.info(
            "Lifecycle transition complete for session '%s'. Archived and initialized new session '%s'.",
            session_id,
            new_session_id,
        )
        return {
            "message": "Cognitive Twin deployed successfully",
            "new_session_id": new_session_id,
            "previous_session_archived": True,
        }

    def is_ready_for_deployment(self, session_id: str) -> bool:
        user_entries = self.memory_service.get_memories(session_id=session_id, role="user")
        meaningful_observations = sum(1 for entry in user_entries if self._is_meaningful_user_input(entry.text))
        return meaningful_observations >= MIN_OBSERVATIONS

    def get_twin_status(self, session_id: str) -> TwinStatus:
        latest_profile = self.memory_service.latest_memory(
            session_id=session_id,
            role=COGNITIVE_PROFILE_ROLE,
            metadata_key="twin_status",
        )
        if latest_profile:
            status = latest_profile.metadata.get("twin_status")
            if status in {TRAINING_STATUS, DEPLOYED_STATUS}:
                return cast(TwinStatus, status)
        return cast(TwinStatus, DEPLOYED_STATUS if self.is_ready_for_deployment(session_id) else TRAINING_STATUS)

    def build_profile(self, session_id: str) -> TwinProfileResponse:
        logger.info("Building profile response for session '%s'.", session_id)
        profile = self.get_profile(session_id)
        weights = self._get_weights(session_id)
        memory_list = self.memory_service.list_memories(session_id)
        twin_status = self.get_twin_status(session_id)

        latest_topics = profile["contexts"][:5]
        if not latest_topics:
            latest_topics = [item.text[:60] for item in memory_list.items[-5:]]

        response = TwinProfileResponse(
            session_id=session_id,
            summary=self._build_summary(profile, weights),
            memory_count=memory_list.count,
            latest_topics=latest_topics,
            twin_status=twin_status,
        )
        logger.info(
            "Built profile response for session '%s' memory_count=%s twin_status='%s'.",
            session_id,
            response.memory_count,
            response.twin_status,
        )
        return response

    def _build_from_extractions(self, extraction_payloads: list[dict[str, Any]]) -> tuple[dict[str, list[str]], dict[str, dict[str, int]]]:
        weights = self._empty_weights()
        for extraction in extraction_payloads:
            normalized = self._normalize_extracted_data(extraction)
            weights = self._merge_weights(weights, normalized)
        return self._profile_from_weights(weights), weights

    def _get_weights(self, session_id: str) -> dict[str, dict[str, int]]:
        latest_profile = self.memory_service.latest_memory(
            session_id=session_id,
            role=COGNITIVE_PROFILE_ROLE,
            metadata_key="weights",
        )
        if latest_profile and isinstance((weights := latest_profile.metadata.get("weights")), dict):
            return self._sanitize_weights(weights)

        extraction_entries = self.memory_service.get_memories(session_id, role=COGNITIVE_EXTRACTION_ROLE)
        extraction_payloads = [
            extraction
            for entry in extraction_entries
            if isinstance((extraction := entry.metadata.get("extraction")), dict)
        ]
        if not extraction_payloads:
            return self._empty_weights()

        _profile, weights = self._build_from_extractions(extraction_payloads)
        return weights

    def _normalize_extracted_data(self, extracted_data: dict[str, Any]) -> dict[str, list[str]]:
        thinking_styles: list[str] = []
        style = extracted_data.get("thinking_style")
        if isinstance(style, str):
            normalized_style = self._normalize_value(style)
            if normalized_style and normalized_style != "unknown":
                thinking_styles.append(normalized_style)

        contexts: list[str] = []
        context = extracted_data.get("context")
        if isinstance(context, str):
            normalized_context = self._normalize_value(context)
            if normalized_context and normalized_context != self._normalize_value(INSUFFICIENT_CONTEXT):
                contexts.append(normalized_context)

        return {
            "thinking_style": thinking_styles,
            "decision_traits": self._normalize_iterable(extracted_data.get("decision_traits")),
            "preferences": self._normalize_iterable(extracted_data.get("preferences")),
            "contexts": contexts,
        }

    def _merge_weights(
        self,
        current_weights: dict[str, dict[str, int]],
        extracted_data: dict[str, list[str]],
    ) -> dict[str, dict[str, int]]:
        merged_weights = {
            key: dict(current_weights.get(key, {}))
            for key in PROFILE_KEYS
        }

        for key in PROFILE_KEYS:
            for value in extracted_data.get(key, []):
                merged_weights[key][value] = merged_weights[key].get(value, 0) + 1

        return merged_weights

    def _profile_from_weights(self, weights: dict[str, dict[str, int]]) -> dict[str, list[str]]:
        profile = self._empty_profile()
        for key in PROFILE_KEYS:
            ordered_values = sorted(weights.get(key, {}).items(), key=lambda item: item[1], reverse=True)
            profile[key] = [value for value, count in ordered_values if count > 0][:5]
        return profile

    def _merge_weights_deployed(
        self,
        current_weights: dict[str, dict[str, int]],
        extracted_data: dict[str, list[str]],
    ) -> dict[str, dict[str, int]]:
        merged_weights = {
            key: dict(current_weights.get(key, {}))
            for key in PROFILE_KEYS
        }

        for key in PROFILE_KEYS:
            for value in extracted_data.get(key, []):
                value_exists = value in merged_weights[key]
                if value_exists:
                    merged_weights[key][value] = merged_weights[key].get(value, 0) + 1
                    continue

                if not merged_weights[key]:
                    merged_weights[key][value] = 1
                    continue

                # During deployment, require repeated observations before new core traits can influence profile.
                merged_weights[key][value] = 1 if key == "contexts" else 0

        return merged_weights

    def _build_summary(self, profile: dict[str, list[str]], weights: dict[str, dict[str, int]]) -> str:
        summary_parts: list[str] = []

        thinking_styles = profile["thinking_style"]
        if thinking_styles:
            top_style = thinking_styles[0]
            summary_parts.append(
                f"Dominant thinking style: {top_style} ({weights['thinking_style'].get(top_style, 0)} observations)."
            )
        else:
            summary_parts.append("Dominant thinking style: unknown.")

        if profile["decision_traits"]:
            summary_parts.append(
                "Decision traits: "
                + ", ".join(self._weighted_labels("decision_traits", profile["decision_traits"], weights))
                + "."
            )
        if profile["preferences"]:
            summary_parts.append(
                "Preferences: "
                + ", ".join(self._weighted_labels("preferences", profile["preferences"], weights))
                + "."
            )
        context_summary = self._build_context_summary(profile["contexts"])
        if context_summary:
            summary_parts.append(context_summary)

        return "\n".join(summary_parts)

    def _build_context_summary(self, contexts: list[str]) -> str:
        cleaned_contexts: list[str] = []
        for context in contexts:
            cleaned_context = self._clean_context(context)
            if not cleaned_context:
                continue
            if any(self._contexts_are_similar(cleaned_context, existing) for existing in cleaned_contexts):
                continue
            cleaned_contexts.append(cleaned_context)
            if len(cleaned_contexts) >= CONTEXT_SUMMARY_LIMIT:
                break

        if not cleaned_contexts:
            return ""

        lines = ["Recent contexts:"]
        lines.extend(f"- {context}" for context in cleaned_contexts[:CONTEXT_SUMMARY_LIMIT])
        return "\n".join(lines)

    def _weighted_labels(
        self,
        key: str,
        values: list[str],
        weights: dict[str, dict[str, int]],
    ) -> list[str]:
        return [f"{value} ({weights[key].get(value, 0)})" for value in values[:3]]

    def _sanitize_profile(self, profile: dict[str, Any]) -> dict[str, list[str]]:
        sanitized = self._empty_profile()
        for key in PROFILE_KEYS:
            sanitized[key] = self._normalize_iterable(profile.get(key))
        return sanitized

    def _sanitize_weights(self, weights: dict[str, Any]) -> dict[str, dict[str, int]]:
        sanitized = self._empty_weights()
        for key in PROFILE_KEYS:
            raw_bucket = weights.get(key, {})
            if not isinstance(raw_bucket, dict):
                continue
            for value, count in raw_bucket.items():
                normalized_value = self._normalize_value(value)
                if normalized_value and isinstance(count, int) and count > 0:
                    sanitized[key][normalized_value] = count
        return sanitized

    def _normalize_iterable(self, value: Any) -> list[str]:
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized_item = self._normalize_value(item)
            if not normalized_item or normalized_item in seen:
                continue
            seen.add(normalized_item)
            normalized.append(normalized_item)
        return normalized[:5]

    def _clean_context(self, context: str) -> str:
        cleaned = " ".join(context.strip().split()).strip(" ,.;:-")
        for pattern, replacement in CONTEXT_CLEANUP_RULES:
            cleaned = pattern.sub(replacement, cleaned)
        cleaned = re.sub(r"^(?:a\s+)?preference\s+for\s+", "prefers ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^(?:the user|they)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(" ,.;:-")
        if not cleaned:
            return ""
        cleaned = cleaned[0].upper() + cleaned[1:]
        if cleaned[-1] not in ".!?":
            cleaned = f"{cleaned}."
        return cleaned

    def _contexts_are_similar(self, left: str, right: str) -> bool:
        left_normalized = left.lower().rstrip(".!?")
        right_normalized = right.lower().rstrip(".!?")
        if left_normalized == right_normalized:
            return True
        if left_normalized in right_normalized or right_normalized in left_normalized:
            return True

        left_tokens = self._context_tokens(left_normalized)
        right_tokens = self._context_tokens(right_normalized)
        if not left_tokens or not right_tokens:
            return False

        overlap = left_tokens.intersection(right_tokens)
        return len(overlap) / min(len(left_tokens), len(right_tokens)) >= 0.8

    def _context_tokens(self, value: str) -> set[str]:
        return {
            token
            for token in CONTEXT_TOKEN_PATTERN.findall(value)
            if len(token) > 3 and token not in CONTEXT_STOP_WORDS
        }

    def _normalize_value(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.strip().split()).lower()

    def _is_meaningful_user_input(self, value: str) -> bool:
        if not isinstance(value, str):
            return False
        tokens = [token for token in MEANINGFUL_INPUT_PATTERN.findall(value.lower()) if len(token) > 2]
        return len(tokens) >= 3

    def _archive_session_snapshot(self, session_id: str) -> bool:
        profile = self.get_profile(session_id)
        memory_list = self.memory_service.list_memories(session_id)
        timestamp = datetime.now(UTC).isoformat()

        archive_payload = {
            "session_id": session_id,
            "status": "archived",
            "profile": profile,
            "memory_count": memory_list.count,
            "timestamp": timestamp,
        }
        archive_file = self.archive_path / f"{safe_slug(session_id)}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
        try:
            archive_file.write_text(json.dumps(archive_payload, indent=2), encoding="utf-8")
        except OSError:
            logger.exception("Failed to archive deployed twin session '%s'.", session_id)
            return False

        self.memory_service.remember(
            session_id=session_id,
            text="Cognitive Twin session archived after deployment.",
            metadata={
                "profile": profile,
                "weights": self._get_weights(session_id),
                "twin_status": DEPLOYED_STATUS,
                "lifecycle_event": "session_archived",
                "archive_file": archive_file.name,
                "archived_at": timestamp,
            },
            role=COGNITIVE_PROFILE_ROLE,
        )
        return True

    def _empty_profile(self) -> dict[str, list[str]]:
        return {key: [] for key in PROFILE_KEYS}

    def _empty_weights(self) -> dict[str, dict[str, int]]:
        return {key: {} for key in PROFILE_KEYS}
