"""Persistence-backed idempotency claims for caller-owned transactions."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.db_models import IdempotencyRecord
from src.core.errors import DomainError
from src.models.schemas import ErrorCode


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    record: IdempotencyRecord
    should_execute: bool


def request_fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class IdempotencyService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def claim(
        self,
        *,
        user_id: str,
        operation: str,
        key: str | None,
        payload: object,
    ) -> IdempotencyClaim | None:
        if key is None:
            return None
        if not key.strip() or len(key) > 128:
            raise DomainError(
                ErrorCode.IDEMPOTENCY_KEY_INVALID,
                "Idempotency-Key must contain between 1 and 128 characters.",
            )
        fingerprint = request_fingerprint(payload)
        record = IdempotencyRecord(
            user_id=user_id,
            operation=operation,
            key=key,
            request_hash=fingerprint,
            state="PENDING",
            response_body=None,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.settings.idempotency_ttl_seconds),
        )
        try:
            async with self.session.begin_nested():
                self.session.add(record)
                await self.session.flush()
            return IdempotencyClaim(record=record, should_execute=True)
        except IntegrityError:
            existing = await self.session.scalar(
                select(IdempotencyRecord)
                .where(
                    IdempotencyRecord.user_id == user_id,
                    IdempotencyRecord.operation == operation,
                    IdempotencyRecord.key == key,
                )
                .with_for_update()
            )
            if existing is None:
                raise
            now = datetime.now(UTC)
            if existing.expires_at <= now:
                existing.request_hash = fingerprint
                existing.state = "PENDING"
                existing.response_body = None
                existing.created_at = now
                existing.expires_at = now + timedelta(seconds=self.settings.idempotency_ttl_seconds)
                await self.session.flush()
                return IdempotencyClaim(record=existing, should_execute=True)
            if existing.request_hash != fingerprint:
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_KEY_REUSED,
                    "Idempotency-Key was already used with a different request.",
                    details={"operation": operation},
                )
            return IdempotencyClaim(record=existing, should_execute=False)

    async def complete(
        self,
        claim: IdempotencyClaim | None,
        response_body: dict[str, object],
    ) -> None:
        if claim is None:
            return
        claim.record.response_body = response_body
        claim.record.state = "COMPLETED"
        await self.session.flush()

    @staticmethod
    def replay(claim: IdempotencyClaim | None) -> dict[str, object] | None:
        if claim is None or claim.should_execute:
            return None
        if claim.record.state != "COMPLETED" or claim.record.response_body is None:
            raise RuntimeError("Idempotency record is not completed")
        return dict(claim.record.response_body)


__all__ = ["IdempotencyClaim", "IdempotencyService", "request_fingerprint"]
