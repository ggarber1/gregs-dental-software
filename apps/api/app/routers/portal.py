from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import AnyUrl
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.models.patient import Patient as PatientModel
from app.models.patient_portal_account import PatientPortalAccount
from app.models.practice import Practice
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    ApiError,
    Error,
    PortalAccountStatusResponse,
    PortalInviteTokenInfo,
    PortalProfile,
    SendPortalInvite,
    SendPortalInviteResponse,
)
from app.services import email

logger = logging.getLogger(__name__)

_PORTAL_INVITE_TTL_HOURS = 168  # 7 days

public_router = APIRouter(prefix="/api", tags=["portal-public"])
staff_router = APIRouter(prefix="/api/v1/portal", tags=["portal"])
patient_router = APIRouter(prefix="/api/v1/portal", tags=["portal-patient"])


def _portal_invite_url(token: str) -> str:
    settings = get_settings()
    base = settings.patient_portal_url.rstrip("/")
    return f"{base}/accept/{token}"


def _invite_is_expired(account: PatientPortalAccount, now: datetime) -> bool:
    if account.status != "invited" or account.invite_expires_at is None:
        return False
    return account.invite_expires_at.replace(tzinfo=UTC) < now


def _status_response(
    patient_id: uuid.UUID,
    account: PatientPortalAccount | None,
) -> PortalAccountStatusResponse:
    if account is None:
        return PortalAccountStatusResponse(
            patientId=patient_id,
            status="none",
            email=None,
            invitedAt=None,
            enrolledAt=None,
            inviteExpiresAt=None,
        )

    status = account.status
    if status == "invited" and _invite_is_expired(account, datetime.now(UTC)):
        status = "none"

    return PortalAccountStatusResponse(
        patientId=patient_id,
        status=status,  # type: ignore[arg-type]
        email=account.email,
        invitedAt=account.invited_at.replace(tzinfo=UTC) if account.invited_at else None,
        enrolledAt=account.enrolled_at.replace(tzinfo=UTC) if account.enrolled_at else None,
        inviteExpiresAt=(
            account.invite_expires_at.replace(tzinfo=UTC) if account.invite_expires_at else None
        ),
    )


def _require_patient_scope(request: Request) -> PatientPortalAccount:
    patient = getattr(request.state, "patient", None)
    if patient is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Patient authentication required"}},
        )
    return patient


@public_router.get("/portal/invite/{token}", response_model=PortalInviteTokenInfo)
async def get_portal_invite_public(token: str) -> PortalInviteTokenInfo:
    """Validate an invite token and return the minimum context for enrollment."""
    now = datetime.now(UTC)

    async with get_session_factory()() as session:
        account = await session.scalar(
            select(PatientPortalAccount).where(PatientPortalAccount.invite_token == token)
        )
        if account is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {"code": "PORTAL_INVITE_NOT_FOUND", "message": "Portal invite not found"}
                },
            )

        if account.status != "invited":
            raise HTTPException(
                status_code=410,
                detail={
                    "error": {
                        "code": "PORTAL_INVITE_INACTIVE",
                        "message": "This portal invite is no longer active",
                    }
                },
            )

        if _invite_is_expired(account, now):
            raise HTTPException(
                status_code=410,
                detail={
                    "error": {
                        "code": "PORTAL_INVITE_EXPIRED",
                        "message": "This portal invite has expired",
                    }
                },
            )

        practice = await session.scalar(select(Practice).where(Practice.id == account.practice_id))
        patient = await session.scalar(
            select(PatientModel).where(PatientModel.id == account.patient_id)
        )

    return PortalInviteTokenInfo(
        practiceName=practice.name if practice else "Your dental practice",
        patientFirstName=patient.first_name if patient else "Patient",
        email=account.email,
    )


@public_router.post("/portal/invite/{token}/complete", status_code=204)
async def complete_portal_invite(token: str, request: Request) -> None:
    """Link the authenticated patient Cognito account to a pending portal invite."""
    settings = get_settings()
    if not settings.has_patient_auth:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "PATIENT_AUTH_UNAVAILABLE",
                    "message": "Patient portal authentication is not configured",
                }
            },
        )

    patient_account = _require_patient_scope(request)
    now = datetime.now(UTC)

    async with get_session_factory()() as session:
        invite = await session.scalar(
            select(PatientPortalAccount).where(PatientPortalAccount.invite_token == token)
        )
        if invite is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {"code": "PORTAL_INVITE_NOT_FOUND", "message": "Portal invite not found"}
                },
            )

        if invite.status != "invited":
            raise HTTPException(
                status_code=410,
                detail={
                    "error": {
                        "code": "PORTAL_INVITE_INACTIVE",
                        "message": "This portal invite is no longer active",
                    }
                },
            )

        if _invite_is_expired(invite, now):
            raise HTTPException(
                status_code=410,
                detail={
                    "error": {
                        "code": "PORTAL_INVITE_EXPIRED",
                        "message": "This portal invite has expired",
                    }
                },
            )

        if patient_account.email.lower() != invite.email.lower():
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "PORTAL_EMAIL_MISMATCH",
                        "message": "Signed-in email does not match the invite",
                    }
                },
            )

        existing_active = await session.scalar(
            select(PatientPortalAccount).where(
                PatientPortalAccount.cognito_sub == patient_account.sub,
                PatientPortalAccount.status == "active",
                PatientPortalAccount.id != invite.id,
            )
        )
        if existing_active is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "PORTAL_ACCOUNT_EXISTS",
                        "message": "This account is already linked to another patient portal profile",
                    }
                },
            )

        await session.execute(
            update(PatientPortalAccount)
            .where(PatientPortalAccount.id == invite.id)
            .values(
                cognito_sub=patient_account.sub,
                status="active",
                invite_token=None,
                invite_expires_at=None,
                enrolled_at=now,
                updated_at=now,
            )
        )
        await session.commit()


@staff_router.post("/invite", status_code=201, response_model=SendPortalInviteResponse)
async def send_portal_invite(body: SendPortalInvite, request: Request) -> SendPortalInviteResponse:
    """Create or refresh a portal invite and email it to the patient."""
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_id = getattr(request.state.user, "user_id", None)
    now = datetime.now(UTC)

    async with get_session_factory()() as session:
        patient = await session.scalar(
            select(PatientModel).where(
                PatientModel.id == body.patient_id,
                PatientModel.practice_id == practice_id,
                PatientModel.deleted_at.is_(None),
            )
        )
        if patient is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="PATIENT_NOT_FOUND", message="Patient not found")
                ).model_dump(by_alias=True),
            )

        if not patient.email:
            raise HTTPException(
                status_code=422,
                detail=ApiError(
                    error=Error(
                        code="PATIENT_NO_EMAIL",
                        message="Patient does not have an email address on file",
                    )
                ).model_dump(by_alias=True),
            )

        account = await session.scalar(
            select(PatientPortalAccount).where(
                PatientPortalAccount.practice_id == practice_id,
                PatientPortalAccount.patient_id == body.patient_id,
            )
        )

        if account is not None and account.status == "active":
            return SendPortalInviteResponse(
                portalAccountId=account.id,
                status="active",
                expiresAt=None,
                inviteUrl=None,
            )

        token = secrets.token_hex(32)
        expires_at = now + timedelta(hours=_PORTAL_INVITE_TTL_HOURS)

        if account is None:
            account = PatientPortalAccount(
                id=uuid.uuid4(),
                practice_id=practice_id,
                patient_id=body.patient_id,
                email=patient.email,
                status="invited",
                invite_token=token,
                invite_expires_at=expires_at,
                invited_at=now,
                invited_by=user_id,
            )
            session.add(account)
        else:
            account.email = patient.email
            account.status = "invited"
            account.invite_token = token
            account.invite_expires_at = expires_at
            account.invited_at = now
            account.invited_by = user_id
            account.cognito_sub = None
            account.enrolled_at = None

        await session.commit()
        await session.refresh(account)

        practice = await session.scalar(select(Practice).where(Practice.id == practice_id))

    settings = get_settings()
    practice_name = practice.name if practice else "Your dental practice"
    invite_url = _portal_invite_url(token)
    subject = f"{practice_name} — your patient portal access"
    text_body = (
        f"Hi {patient.first_name},\n\n"
        f"{practice_name} has invited you to access your secure patient portal.\n\n"
        f"Create your account here: {invite_url}\n\n"
        f"This link expires in {_PORTAL_INVITE_TTL_HOURS // 24} days."
    )
    html_body = (
        f"<p>Hi {patient.first_name},</p>"
        f"<p>{practice_name} has invited you to access your secure patient portal.</p>"
        f'<p><a href="{invite_url}">Create your portal account</a></p>'
        f"<p>This link expires in {_PORTAL_INVITE_TTL_HOURS // 24} days.</p>"
    )

    try:
        await email.send_email(
            to=patient.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
    except Exception:
        logger.warning(
            "Email delivery failed for portal invite %s (patient %s) — invite created; invite_url=%s",
            account.id,
            body.patient_id,
            invite_url,
            exc_info=True,
        )

    return SendPortalInviteResponse(
        portalAccountId=account.id,
        status="active" if account.status == "active" else "invited",
        expiresAt=account.invite_expires_at.replace(tzinfo=UTC) if account.invite_expires_at else None,
        inviteUrl=AnyUrl(invite_url) if account.invite_token else None,
    )


@staff_router.get("/status", response_model=PortalAccountStatusResponse)
async def get_portal_status(
    request: Request,
    patient_id: uuid.UUID,
) -> PortalAccountStatusResponse:
    """Return portal enrollment status for a patient."""
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        patient = await session.scalar(
            select(PatientModel).where(
                PatientModel.id == patient_id,
                PatientModel.practice_id == practice_id,
                PatientModel.deleted_at.is_(None),
            )
        )
        if patient is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="PATIENT_NOT_FOUND", message="Patient not found")
                ).model_dump(by_alias=True),
            )

        account = await session.scalar(
            select(PatientPortalAccount).where(
                PatientPortalAccount.practice_id == practice_id,
                PatientPortalAccount.patient_id == patient_id,
            )
        )

    return _status_response(patient_id, account)


@patient_router.get("/me", response_model=PortalProfile)
async def get_portal_profile(request: Request) -> PortalProfile:
    """Return the authenticated patient's portal profile."""
    account = _require_patient_scope(request)

    async with get_session_factory()() as session:
        patient = await session.scalar(
            select(PatientModel).where(
                PatientModel.id == account.patient_id,
                PatientModel.practice_id == account.practice_id,
                PatientModel.deleted_at.is_(None),
            )
        )
        practice = await session.scalar(select(Practice).where(Practice.id == account.practice_id))

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "PATIENT_NOT_FOUND", "message": "Patient record not found"}},
        )

    return PortalProfile(
        patientId=patient.id,
        practiceId=account.practice_id,
        practiceName=practice.name if practice else "Your dental practice",
        firstName=patient.first_name,
        lastName=patient.last_name,
        email=patient.email,
    )
