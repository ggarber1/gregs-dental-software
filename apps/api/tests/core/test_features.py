from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.features import require_feature


async def test_require_feature_passes_when_enabled():
    session = MagicMock()
    session.scalar = AsyncMock(return_value=MagicMock(features={"eligibility_verification": True}))
    await require_feature(session, uuid.uuid4(), "eligibility_verification")  # no raise


async def test_require_feature_403_when_disabled():
    session = MagicMock()
    session.scalar = AsyncMock(return_value=MagicMock(features={}))
    with pytest.raises(HTTPException) as exc:
        await require_feature(session, uuid.uuid4(), "eligibility_verification")
    assert exc.value.status_code == 403


async def test_require_feature_403_when_practice_not_found():
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await require_feature(session, uuid.uuid4(), "eligibility_verification")
    assert exc.value.status_code == 403
