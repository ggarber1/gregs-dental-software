from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.models.patient import Patient as PatientModel
from app.models.treatment_plan import TreatmentPlan as TreatmentPlanModel
from app.models.treatment_plan import TreatmentPlanItem as TreatmentPlanItemModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    ApiError,
    CreateTreatmentPlan,
    CreateTreatmentPlanItem,
    Error,
    OpenPlanQueueItem,
    TreatmentPlan,
    TreatmentPlanDetail,
    TreatmentPlanItem,
    TreatmentPlanListResponse,
    UpdateTreatmentPlan,
    UpdateTreatmentPlanItem,
)

logger = logging.getLogger(__name__)

# Patient-scoped router
router = APIRouter(
    prefix="/api/v1/patients/{patient_id}/treatment-plans",
    tags=["treatment-plans"],
)

# Practice-scoped router (open queue)
open_router = APIRouter(
    prefix="/api/v1/treatment-plans",
    tags=["treatment-plans"],
)

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20

# ── Valid status transitions ───────────────────────────────────────────────────

_PLAN_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"accepted", "refused"}),
    "accepted": frozenset({"in_progress", "refused", "superseded"}),
    "in_progress": frozenset({"completed", "refused", "superseded"}),
    "completed": frozenset(),
    "refused": frozenset(),
    "superseded": frozenset(),
}

_ITEM_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"accepted", "refused"}),
    "accepted": frozenset({"scheduled", "refused"}),
    "scheduled": frozenset({"completed", "refused"}),
    "completed": frozenset(),
    "refused": frozenset(),
}


# ── Cursor helpers ─────────────────────────────────────────────────────────────


def _encode_cursor(created_at: datetime, plan_id: uuid.UUID) -> str:
    payload = {"t": created_at.isoformat(), "i": str(plan_id)}
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID] | None:
    try:
        payload = json.loads(base64.b64decode(cursor).decode())
        return datetime.fromisoformat(payload["t"]), uuid.UUID(payload["i"])
    except Exception:
        return None


def _encode_queue_cursor(accepted_at: date, plan_id: uuid.UUID) -> str:
    payload = {"d": accepted_at.isoformat(), "i": str(plan_id)}
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _decode_queue_cursor(cursor: str) -> tuple[date, uuid.UUID] | None:
    try:
        payload = json.loads(base64.b64decode(cursor).decode())
        return date.fromisoformat(payload["d"]), uuid.UUID(payload["i"])
    except Exception:
        return None


# ── PHI audit ─────────────────────────────────────────────────────────────────


async def _phi_audit_plan(
    session: AsyncSession,
    row_id: uuid.UUID,
    user_sub: str | None,
) -> None:
    await session.execute(
        update(TreatmentPlanModel)
        .where(TreatmentPlanModel.id == row_id)
        .values(last_accessed_by=user_sub, last_accessed_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )


# ── Serialisation ──────────────────────────────────────────────────────────────


def _item_to_dict(row: TreatmentPlanItemModel) -> dict[str, Any]:
    return TreatmentPlanItem(
        id=row.id,
        practiceId=row.practice_id,
        treatmentPlanId=row.treatment_plan_id,
        patientId=row.patient_id,
        toothNumber=row.tooth_number,
        procedureCode=row.procedure_code,
        procedureName=row.procedure_name,
        surface=row.surface,
        feeCents=row.fee_cents,
        insuranceEstCents=row.insurance_est_cents,  # type: ignore[arg-type]
        patientEstCents=row.patient_est_cents,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        priority=row.priority,
        appointmentId=row.appointment_id,
        completedAppointmentId=row.completed_appointment_id,
        notes=row.notes,
        createdAt=row.created_at.replace(tzinfo=UTC),
        updatedAt=row.updated_at.replace(tzinfo=UTC),
    ).model_dump(by_alias=True)


def _item_to_schema(row: TreatmentPlanItemModel) -> TreatmentPlanItem:
    return TreatmentPlanItem(
        id=row.id,
        practiceId=row.practice_id,
        treatmentPlanId=row.treatment_plan_id,
        patientId=row.patient_id,
        toothNumber=row.tooth_number,
        procedureCode=row.procedure_code,
        procedureName=row.procedure_name,
        surface=row.surface,
        feeCents=row.fee_cents,
        insuranceEstCents=row.insurance_est_cents,  # type: ignore[arg-type]
        patientEstCents=row.patient_est_cents,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        priority=row.priority,
        appointmentId=row.appointment_id,
        completedAppointmentId=row.completed_appointment_id,
        notes=row.notes,
        createdAt=row.created_at.replace(tzinfo=UTC),
        updatedAt=row.updated_at.replace(tzinfo=UTC),
    )


def _plan_to_schema(row: TreatmentPlanModel) -> TreatmentPlan:
    return TreatmentPlan(
        id=row.id,
        practiceId=row.practice_id,
        patientId=row.patient_id,
        name=row.name,
        status=row.status,  # type: ignore[arg-type]
        presentedAt=row.presented_at,
        acceptedAt=row.accepted_at,
        completedAt=row.completed_at,
        notes=row.notes,
        createdBy=row.created_by,
        createdAt=row.created_at.replace(tzinfo=UTC),
        updatedAt=row.updated_at.replace(tzinfo=UTC),
    )


def _plan_to_detail(
    row: TreatmentPlanModel,
    items: list[TreatmentPlanItemModel],
) -> TreatmentPlanDetail:
    return TreatmentPlanDetail(
        id=row.id,
        practiceId=row.practice_id,
        patientId=row.patient_id,
        name=row.name,
        status=row.status,  # type: ignore[arg-type]
        presentedAt=row.presented_at,
        acceptedAt=row.accepted_at,
        completedAt=row.completed_at,
        notes=row.notes,
        createdBy=row.created_by,
        createdAt=row.created_at.replace(tzinfo=UTC),
        updatedAt=row.updated_at.replace(tzinfo=UTC),
        items=[_item_to_dict(i) for i in items],  # type: ignore[misc]
    )


# ── Auto-transition plan status based on item states ──────────────────────────


async def _maybe_auto_transition_plan(
    session: AsyncSession,
    plan: TreatmentPlanModel,
) -> None:
    items = (
        await session.scalars(
            select(TreatmentPlanItemModel).where(
                TreatmentPlanItemModel.treatment_plan_id == plan.id,
                TreatmentPlanItemModel.deleted_at.is_(None),
            )
        )
    ).all()

    if not items:
        return

    statuses = {item.status for item in items}
    terminal = {"completed", "refused"}
    now = datetime.now(UTC)

    if statuses <= terminal:
        # All items are terminal — plan is done if any completed, else all refused
        if plan.status not in ("completed", "refused", "superseded"):
            plan.status = "completed"
            plan.completed_at = now.date()
            plan.updated_at = now
    elif plan.status == "accepted" and statuses & {"completed", "scheduled"}:
        plan.status = "in_progress"
        plan.updated_at = now


# ── Patient-scoped endpoints ───────────────────────────────────────────────────


@router.get("", response_model=TreatmentPlanListResponse)
async def list_treatment_plans(
    patient_id: uuid.UUID,
    request: Request,
    limit: int = _DEFAULT_LIMIT,
    cursor: str | None = None,
    status: str | None = None,
) -> TreatmentPlanListResponse:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)
    limit = min(max(limit, 1), _MAX_LIMIT)

    async with get_session_factory()() as session:
        q = select(TreatmentPlanModel).where(
            TreatmentPlanModel.patient_id == patient_id,
            TreatmentPlanModel.practice_id == practice_id,
            TreatmentPlanModel.deleted_at.is_(None),
        )

        if status is not None:
            q = q.where(TreatmentPlanModel.status == status)

        if cursor is not None:
            decoded = _decode_cursor(cursor)
            if decoded is not None:
                cursor_dt, cursor_id = decoded
                q = q.where(
                    or_(
                        TreatmentPlanModel.created_at < cursor_dt,
                        and_(
                            TreatmentPlanModel.created_at == cursor_dt,
                            TreatmentPlanModel.id < cursor_id,
                        ),
                    )
                )

        q = q.order_by(TreatmentPlanModel.created_at.desc(), TreatmentPlanModel.id.desc()).limit(
            limit + 1
        )
        rows = (await session.scalars(q)).all()

        has_more = len(rows) > limit
        items = list(rows[:limit])

        next_cursor: str | None = None
        if has_more and items:
            last = items[-1]
            next_cursor = _encode_cursor(last.created_at, last.id)

        for item in items:
            await _phi_audit_plan(session, item.id, user_sub)
        if items:
            await session.commit()

    return TreatmentPlanListResponse(
        items=[_plan_to_schema(r).model_dump(by_alias=True) for r in items],  # type: ignore[misc]
        nextCursor=next_cursor,
        hasMore=has_more,
    )


@router.post("", status_code=201, response_model=TreatmentPlanDetail)
async def create_treatment_plan(
    patient_id: uuid.UUID,
    body: CreateTreatmentPlan,
    request: Request,
) -> TreatmentPlanDetail:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_id = getattr(request.state.user, "user_id", None)

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

        plan = TreatmentPlanModel(
            id=uuid.uuid4(),
            practice_id=practice_id,
            patient_id=patient_id,
            name=body.name or "Treatment Plan",
            status="proposed",
            notes=body.notes,
            created_by=user_id or patient_id,
        )
        session.add(plan)
        await session.flush()

        item_rows: list[TreatmentPlanItemModel] = []
        for item_body in body.items or []:
            item = TreatmentPlanItemModel(
                id=uuid.uuid4(),
                practice_id=practice_id,
                treatment_plan_id=plan.id,
                patient_id=patient_id,
                tooth_number=item_body.tooth_number,
                procedure_code=item_body.procedure_code,
                procedure_name=item_body.procedure_name,
                surface=item_body.surface,
                fee_cents=item_body.fee_cents,
                insurance_est_cents=item_body.insurance_est_cents,
                patient_est_cents=item_body.patient_est_cents,
                status="proposed",
                priority=item_body.priority or 1,
                notes=item_body.notes,
            )
            session.add(item)
            item_rows.append(item)

        await session.commit()
        await session.refresh(plan)
        for item in item_rows:
            await session.refresh(item)

    logger.info(
        "Treatment plan created: patient_id=%s plan_id=%s items=%d",
        patient_id,
        plan.id,
        len(item_rows),
    )

    return _plan_to_detail(plan, item_rows)


@router.get("/{plan_id}", response_model=TreatmentPlanDetail)
async def get_treatment_plan(
    patient_id: uuid.UUID,
    plan_id: uuid.UUID,
    request: Request,
) -> TreatmentPlanDetail:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)

    async with get_session_factory()() as session:
        plan = await session.scalar(
            select(TreatmentPlanModel).where(
                TreatmentPlanModel.id == plan_id,
                TreatmentPlanModel.patient_id == patient_id,
                TreatmentPlanModel.practice_id == practice_id,
                TreatmentPlanModel.deleted_at.is_(None),
            )
        )
        if plan is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="PLAN_NOT_FOUND", message="Treatment plan not found")
                ).model_dump(by_alias=True),
            )

        items = (
            await session.scalars(
                select(TreatmentPlanItemModel)
                .where(
                    TreatmentPlanItemModel.treatment_plan_id == plan_id,
                    TreatmentPlanItemModel.deleted_at.is_(None),
                )
                .order_by(
                    TreatmentPlanItemModel.priority.asc(),
                    TreatmentPlanItemModel.created_at.asc(),
                )
            )
        ).all()

        await _phi_audit_plan(session, plan.id, user_sub)
        await session.commit()

    return _plan_to_detail(plan, list(items))


@router.patch("/{plan_id}", response_model=TreatmentPlan)
async def update_treatment_plan(
    patient_id: uuid.UUID,
    plan_id: uuid.UUID,
    body: UpdateTreatmentPlan,
    request: Request,
) -> TreatmentPlan:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        plan = await session.scalar(
            select(TreatmentPlanModel)
            .where(
                TreatmentPlanModel.id == plan_id,
                TreatmentPlanModel.patient_id == patient_id,
                TreatmentPlanModel.practice_id == practice_id,
                TreatmentPlanModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if plan is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="PLAN_NOT_FOUND", message="Treatment plan not found")
                ).model_dump(by_alias=True),
            )

        now = datetime.now(UTC)

        if body.status is not None and body.status != plan.status:
            allowed = _PLAN_TRANSITIONS.get(plan.status, frozenset())
            if body.status not in allowed:
                raise HTTPException(
                    status_code=409,
                    detail=ApiError(
                        error=Error(
                            code="INVALID_STATUS_TRANSITION",
                            message=(
                                f"Cannot transition plan from '{plan.status}' to '{body.status}'"
                            ),
                        )
                    ).model_dump(by_alias=True),
                )
            plan.status = body.status
            if body.status == "accepted" and plan.accepted_at is None:
                plan.accepted_at = now.date()
            elif body.status == "completed" and plan.completed_at is None:
                plan.completed_at = now.date()

        if body.name is not None:
            plan.name = body.name
        if body.notes is not None:
            plan.notes = body.notes
        if body.presented_at is not None:
            plan.presented_at = body.presented_at

        plan.updated_at = now
        await session.commit()
        await session.refresh(plan)

    logger.info(
        "Treatment plan updated: patient_id=%s plan_id=%s status=%s",
        patient_id,
        plan_id,
        plan.status,
    )

    return _plan_to_schema(plan)


@router.post("/{plan_id}/items", status_code=201, response_model=TreatmentPlanItem)
async def add_treatment_plan_item(
    patient_id: uuid.UUID,
    plan_id: uuid.UUID,
    body: CreateTreatmentPlanItem,
    request: Request,
) -> TreatmentPlanItem:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        plan = await session.scalar(
            select(TreatmentPlanModel).where(
                TreatmentPlanModel.id == plan_id,
                TreatmentPlanModel.patient_id == patient_id,
                TreatmentPlanModel.practice_id == practice_id,
                TreatmentPlanModel.deleted_at.is_(None),
            )
        )
        if plan is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="PLAN_NOT_FOUND", message="Treatment plan not found")
                ).model_dump(by_alias=True),
            )

        item = TreatmentPlanItemModel(
            id=uuid.uuid4(),
            practice_id=practice_id,
            treatment_plan_id=plan_id,
            patient_id=patient_id,
            tooth_number=body.tooth_number,
            procedure_code=body.procedure_code,
            procedure_name=body.procedure_name,
            surface=body.surface,
            fee_cents=body.fee_cents,
            insurance_est_cents=body.insurance_est_cents,
            patient_est_cents=body.patient_est_cents,
            status="proposed",
            priority=body.priority or 1,
            notes=body.notes,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)

    logger.info(
        "Treatment plan item added: plan_id=%s item_id=%s code=%s",
        plan_id,
        item.id,
        body.procedure_code,
    )

    return _item_to_schema(item)


@router.patch("/{plan_id}/items/{item_id}", response_model=TreatmentPlanItem)
async def update_treatment_plan_item(
    patient_id: uuid.UUID,
    plan_id: uuid.UUID,
    item_id: uuid.UUID,
    body: UpdateTreatmentPlanItem,
    request: Request,
) -> TreatmentPlanItem:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        item = await session.scalar(
            select(TreatmentPlanItemModel)
            .where(
                TreatmentPlanItemModel.id == item_id,
                TreatmentPlanItemModel.treatment_plan_id == plan_id,
                TreatmentPlanItemModel.patient_id == patient_id,
                TreatmentPlanItemModel.practice_id == practice_id,
                TreatmentPlanItemModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if item is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="ITEM_NOT_FOUND", message="Treatment plan item not found")
                ).model_dump(by_alias=True),
            )

        now = datetime.now(UTC)

        if body.status is not None and body.status != item.status:
            allowed = _ITEM_TRANSITIONS.get(item.status, frozenset())
            if body.status not in allowed:
                raise HTTPException(
                    status_code=409,
                    detail=ApiError(
                        error=Error(
                            code="INVALID_STATUS_TRANSITION",
                            message=(
                                f"Cannot transition item from '{item.status}' to '{body.status}'"
                            ),
                        )
                    ).model_dump(by_alias=True),
                )
            item.status = body.status

        update_data: dict[str, Any] = {}
        if body.fee_cents is not None:
            update_data["fee_cents"] = body.fee_cents
        if body.insurance_est_cents is not None:
            update_data["insurance_est_cents"] = body.insurance_est_cents
        if body.patient_est_cents is not None:
            update_data["patient_est_cents"] = body.patient_est_cents
        if body.appointment_id is not None:
            update_data["appointment_id"] = body.appointment_id
        if body.completed_appointment_id is not None:
            update_data["completed_appointment_id"] = body.completed_appointment_id
        if body.notes is not None:
            update_data["notes"] = body.notes
        if body.priority is not None:
            update_data["priority"] = body.priority

        for key, value in update_data.items():
            setattr(item, key, value)
        item.updated_at = now

        # Re-fetch plan inside same transaction for auto-transition
        plan = await session.scalar(
            select(TreatmentPlanModel)
            .where(TreatmentPlanModel.id == plan_id)
            .with_for_update()
        )
        if plan is not None:
            await _maybe_auto_transition_plan(session, plan)

        await session.commit()
        await session.refresh(item)

    logger.info(
        "Treatment plan item updated: plan_id=%s item_id=%s status=%s",
        plan_id,
        item_id,
        item.status,
    )

    return _item_to_schema(item)


@router.delete("/{plan_id}/items/{item_id}", status_code=204)
async def delete_treatment_plan_item(
    patient_id: uuid.UUID,
    plan_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        item = await session.scalar(
            select(TreatmentPlanItemModel)
            .where(
                TreatmentPlanItemModel.id == item_id,
                TreatmentPlanItemModel.treatment_plan_id == plan_id,
                TreatmentPlanItemModel.patient_id == patient_id,
                TreatmentPlanItemModel.practice_id == practice_id,
                TreatmentPlanItemModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if item is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="ITEM_NOT_FOUND", message="Treatment plan item not found")
                ).model_dump(by_alias=True),
            )

        now = datetime.now(UTC)
        item.deleted_at = now
        item.updated_at = now
        await session.commit()

    logger.info(
        "Treatment plan item deleted: plan_id=%s item_id=%s",
        plan_id,
        item_id,
    )


# ── Practice-scoped: open treatment plan queue ────────────────────────────────


@open_router.get("/open", response_model=list[OpenPlanQueueItem])
async def get_open_treatment_plans(
    request: Request,
    limit: int = _DEFAULT_LIMIT,
    cursor: str | None = None,
) -> list[OpenPlanQueueItem]:
    practice_id = _require_practice_scope(request)
    limit = min(max(limit, 1), _MAX_LIMIT)

    async with get_session_factory()() as session:
        # Subquery: plan IDs that have at least one unscheduled active item
        unscheduled_plan_ids = (
            select(TreatmentPlanItemModel.treatment_plan_id)
            .where(
                TreatmentPlanItemModel.practice_id == practice_id,
                TreatmentPlanItemModel.status.in_(["proposed", "accepted"]),
                TreatmentPlanItemModel.deleted_at.is_(None),
            )
            .distinct()
            .scalar_subquery()
        )

        q = (
            select(
                TreatmentPlanModel,
                PatientModel,
                func.count(TreatmentPlanItemModel.id).label("pending_count"),
            )
            .join(
                PatientModel,
                and_(
                    PatientModel.id == TreatmentPlanModel.patient_id,
                    PatientModel.deleted_at.is_(None),
                ),
            )
            .join(
                TreatmentPlanItemModel,
                and_(
                    TreatmentPlanItemModel.treatment_plan_id == TreatmentPlanModel.id,
                    TreatmentPlanItemModel.status.in_(["proposed", "accepted"]),
                    TreatmentPlanItemModel.deleted_at.is_(None),
                ),
            )
            .where(
                TreatmentPlanModel.practice_id == practice_id,
                TreatmentPlanModel.status == "accepted",
                TreatmentPlanModel.deleted_at.is_(None),
                TreatmentPlanModel.id.in_(unscheduled_plan_ids),
            )
            .group_by(TreatmentPlanModel.id, PatientModel.id)
        )

        if cursor is not None:
            decoded = _decode_queue_cursor(cursor)
            if decoded is not None:
                cursor_date, cursor_id = decoded
                q = q.where(
                    or_(
                        TreatmentPlanModel.accepted_at > cursor_date,
                        and_(
                            TreatmentPlanModel.accepted_at == cursor_date,
                            TreatmentPlanModel.id > cursor_id,
                        ),
                    )
                )

        q = q.order_by(
            TreatmentPlanModel.accepted_at.asc(),
            TreatmentPlanModel.id.asc(),
        ).limit(limit + 1)

        rows = (await session.execute(q)).all()

    today = date.today()
    results: list[OpenPlanQueueItem] = []
    for plan, patient, pending_count in rows[:limit]:
        days_since = (
            (today - plan.accepted_at).days if plan.accepted_at else 0
        )
        results.append(
            OpenPlanQueueItem(
                planId=plan.id,
                planName=plan.name,
                patientId=patient.id,
                patientName=f"{patient.first_name} {patient.last_name}",
                pendingItemCount=pending_count,
                daysSinceAcceptance=days_since,
                acceptedAt=plan.accepted_at,
            )
        )

    return results
