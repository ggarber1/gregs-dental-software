from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.models.patient import Patient as PatientModel
from app.models.perio_chart import PerioChart as PerioChartModel
from app.models.perio_chart import PerioReading as PerioReadingModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    AddPerioReadings,
    ApiError,
    Error,
    Furcation,
    PerioChartComparison,
    PerioChartCreate,
    PerioChartDetail,
    PerioChartListResponse,
    PerioChartSummary,
    PerioReadingCreate,
    PerioReadingOut,
    PerioSite,
    PerioSiteDelta,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/patients/{patient_id}/perio-charts",
    tags=["perio-charts"],
)

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20


# ── Cursor helpers ─────────────────────────────────────────────────────────────


def _encode_cursor(chart_date: date, chart_id: uuid.UUID) -> str:
    payload = {"d": chart_date.isoformat(), "i": str(chart_id)}
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[date, uuid.UUID] | None:
    try:
        payload = json.loads(base64.b64decode(cursor).decode())
        return date.fromisoformat(payload["d"]), uuid.UUID(payload["i"])
    except Exception:
        return None


# ── PHI audit ─────────────────────────────────────────────────────────────────


async def _phi_audit(
    session: AsyncSession,
    chart_id: uuid.UUID,
    user_sub: str | None,
) -> None:
    await session.execute(
        update(PerioChartModel)
        .where(PerioChartModel.id == chart_id)
        .values(last_accessed_by=user_sub, last_accessed_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )


# ── Summary stats ──────────────────────────────────────────────────────────────


def _compute_summary(readings: list[PerioReadingModel]) -> dict[str, Any]:
    if not readings:
        return {
            "avgProbingDepthMm": 0.0,
            "sitesGte4mm": 0,
            "sitesGte6mm": 0,
            "bleedingSiteCount": 0,
        }
    depths = [r.probing_depth_mm for r in readings]
    return {
        "avgProbingDepthMm": round(sum(depths) / len(depths), 1),
        "sitesGte4mm": sum(1 for d in depths if d >= 4),
        "sitesGte6mm": sum(1 for d in depths if d >= 6),
        "bleedingSiteCount": sum(1 for r in readings if r.bleeding),
    }


# ── Serialisation ──────────────────────────────────────────────────────────────


def _reading_to_dict(row: PerioReadingModel) -> dict[str, Any]:
    return PerioReadingOut(
        id=row.id,
        perioChartId=row.perio_chart_id,
        toothNumber=row.tooth_number,
        site=PerioSite(row.site),
        probingDepthMm=row.probing_depth_mm,
        recessionMm=row.recession_mm,
        cal=row.probing_depth_mm + row.recession_mm,
        bleeding=row.bleeding,
        suppuration=row.suppuration,
        furcation=Furcation(row.furcation) if row.furcation else None,
        mobility=row.mobility,
        createdAt=row.created_at.replace(tzinfo=UTC),
    ).model_dump(by_alias=True)


def _chart_to_summary_dict(
    chart: PerioChartModel,
    avg_depth: float,
    sites_gte_4: int,
    sites_gte_6: int,
    bleeding_count: int,
) -> dict[str, Any]:
    return PerioChartSummary(
        id=chart.id,
        practiceId=chart.practice_id,
        patientId=chart.patient_id,
        appointmentId=chart.appointment_id,
        providerId=chart.provider_id,
        chartDate=chart.chart_date,
        notes=chart.notes,
        avgProbingDepthMm=round(float(avg_depth), 1),
        sitesGte4mm=int(sites_gte_4),
        sitesGte6mm=int(sites_gte_6),
        bleedingSiteCount=int(bleeding_count),
        createdAt=chart.created_at.replace(tzinfo=UTC),
        updatedAt=chart.updated_at.replace(tzinfo=UTC),
    ).model_dump(by_alias=True)


def _chart_to_detail(
    chart: PerioChartModel,
    readings: list[PerioReadingModel],
) -> PerioChartDetail:
    stats = _compute_summary(readings)
    return PerioChartDetail(
        id=chart.id,
        practiceId=chart.practice_id,
        patientId=chart.patient_id,
        appointmentId=chart.appointment_id,
        providerId=chart.provider_id,
        chartDate=chart.chart_date,
        notes=chart.notes,
        avgProbingDepthMm=stats["avgProbingDepthMm"],
        sitesGte4mm=stats["sitesGte4mm"],
        sitesGte6mm=stats["sitesGte6mm"],
        bleedingSiteCount=stats["bleedingSiteCount"],
        createdAt=chart.created_at.replace(tzinfo=UTC),
        updatedAt=chart.updated_at.replace(tzinfo=UTC),
        readings=[_reading_to_dict(r) for r in readings],
    )


# ── Upsert helper ──────────────────────────────────────────────────────────────


async def _upsert_readings(
    session: AsyncSession,
    chart_id: uuid.UUID,
    readings: list[PerioReadingCreate],
) -> None:
    if not readings:
        return
    ins = pg_insert(PerioReadingModel)
    values = [
        {
            "id": uuid.uuid4(),
            "perio_chart_id": chart_id,
            "tooth_number": r.tooth_number,
            "site": r.site.value,
            "probing_depth_mm": r.probing_depth_mm,
            "recession_mm": r.recession_mm,
            "bleeding": r.bleeding,
            "suppuration": r.suppuration,
            "furcation": r.furcation.value if r.furcation else None,
            "mobility": r.mobility,
        }
        for r in readings
    ]
    stmt = ins.values(values).on_conflict_do_update(
        constraint="uq_perio_readings_chart_tooth_site",
        set_={
            "probing_depth_mm": ins.excluded.probing_depth_mm,
            "recession_mm": ins.excluded.recession_mm,
            "bleeding": ins.excluded.bleeding,
            "suppuration": ins.excluded.suppuration,
            "furcation": ins.excluded.furcation,
            "mobility": ins.excluded.mobility,
        },
    )
    await session.execute(stmt)


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("", response_model=PerioChartListResponse)
async def list_perio_charts(
    patient_id: uuid.UUID,
    request: Request,
    limit: int = _DEFAULT_LIMIT,
    cursor: str | None = None,
) -> PerioChartListResponse:
    practice_id = _require_practice_scope(request)
    limit = min(max(limit, 1), _MAX_LIMIT)

    async with get_session_factory()() as session:
        q = (
            select(
                PerioChartModel,
                func.coalesce(func.avg(PerioReadingModel.probing_depth_mm), 0).label("avg_depth"),
                func.count(
                    case((PerioReadingModel.probing_depth_mm >= 4, 1), else_=None)
                ).label("sites_gte_4"),
                func.count(
                    case((PerioReadingModel.probing_depth_mm >= 6, 1), else_=None)
                ).label("sites_gte_6"),
                func.count(
                    case((PerioReadingModel.bleeding == True, 1), else_=None)  # noqa: E712
                ).label("bleeding_count"),
            )
            .outerjoin(
                PerioReadingModel,
                PerioReadingModel.perio_chart_id == PerioChartModel.id,
            )
            .where(
                PerioChartModel.patient_id == patient_id,
                PerioChartModel.practice_id == practice_id,
                PerioChartModel.deleted_at.is_(None),
            )
            .group_by(PerioChartModel.id)
        )

        if cursor is not None:
            decoded = _decode_cursor(cursor)
            if decoded is not None:
                cursor_date, cursor_id = decoded
                q = q.where(
                    or_(
                        PerioChartModel.chart_date < cursor_date,
                        and_(
                            PerioChartModel.chart_date == cursor_date,
                            PerioChartModel.id < cursor_id,
                        ),
                    )
                )

        q = q.order_by(
            PerioChartModel.chart_date.desc(), PerioChartModel.id.desc()
        ).limit(limit + 1)

        rows = (await session.execute(q)).all()

    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor: str | None = None
    if has_more and page:
        last_chart = page[-1][0]
        next_cursor = _encode_cursor(last_chart.chart_date, last_chart.id)

    items = [
        _chart_to_summary_dict(chart, avg_depth, gte4, gte6, bleeding)
        for chart, avg_depth, gte4, gte6, bleeding in page
    ]

    return PerioChartListResponse(
        items=items,  # type: ignore[arg-type]
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("", status_code=201, response_model=PerioChartDetail)
async def create_perio_chart(
    patient_id: uuid.UUID,
    body: PerioChartCreate,
    request: Request,
) -> PerioChartDetail:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

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

        chart = PerioChartModel(
            id=uuid.uuid4(),
            practice_id=practice_id,
            patient_id=patient_id,
            appointment_id=body.appointment_id,
            provider_id=body.provider_id,
            chart_date=body.chart_date,
            notes=body.notes,
        )
        session.add(chart)
        await session.flush()

        await _upsert_readings(session, chart.id, body.readings)
        await session.commit()
        await session.refresh(chart)

        readings = (
            await session.scalars(
                select(PerioReadingModel)
                .where(PerioReadingModel.perio_chart_id == chart.id)
                .order_by(PerioReadingModel.tooth_number, PerioReadingModel.site)
            )
        ).all()

    logger.info(
        "Perio chart created: patient_id=%s chart_id=%s readings=%d",
        patient_id,
        chart.id,
        len(readings),
    )

    return _chart_to_detail(chart, list(readings))


# /compare must be declared before /{chart_id} so FastAPI doesn't try to parse
# "compare" as a UUID.
@router.get("/compare", response_model=PerioChartComparison)
async def compare_perio_charts(
    patient_id: uuid.UUID,
    request: Request,
    chart_a_id: Annotated[uuid.UUID, Query(alias="chartA")],
    chart_b_id: Annotated[uuid.UUID, Query(alias="chartB")],
) -> PerioChartComparison:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)

    async with get_session_factory()() as session:
        chart_a = await session.scalar(
            select(PerioChartModel).where(
                PerioChartModel.id == chart_a_id,
                PerioChartModel.patient_id == patient_id,
                PerioChartModel.practice_id == practice_id,
                PerioChartModel.deleted_at.is_(None),
            )
        )
        chart_b = await session.scalar(
            select(PerioChartModel).where(
                PerioChartModel.id == chart_b_id,
                PerioChartModel.patient_id == patient_id,
                PerioChartModel.practice_id == practice_id,
                PerioChartModel.deleted_at.is_(None),
            )
        )
        if chart_a is None or chart_b is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(
                        code="CHART_NOT_FOUND",
                        message="One or both perio charts not found",
                    )
                ).model_dump(by_alias=True),
            )

        readings_a = (
            await session.scalars(
                select(PerioReadingModel).where(
                    PerioReadingModel.perio_chart_id == chart_a_id
                )
            )
        ).all()
        readings_b = (
            await session.scalars(
                select(PerioReadingModel).where(
                    PerioReadingModel.perio_chart_id == chart_b_id
                )
            )
        ).all()

        await _phi_audit(session, chart_a_id, user_sub)
        await _phi_audit(session, chart_b_id, user_sub)
        await session.commit()

    map_a = {(r.tooth_number, r.site): r for r in readings_a}
    map_b = {(r.tooth_number, r.site): r for r in readings_b}
    all_keys = sorted(map_a.keys() | map_b.keys())

    deltas = [
        PerioSiteDelta(
            toothNumber=tooth,
            site=PerioSite(site),
            depthA=map_a[tooth, site].probing_depth_mm if (tooth, site) in map_a else 0,
            depthB=map_b[tooth, site].probing_depth_mm if (tooth, site) in map_b else 0,
            delta=(map_b[tooth, site].probing_depth_mm if (tooth, site) in map_b else 0)
            - (map_a[tooth, site].probing_depth_mm if (tooth, site) in map_a else 0),
        ).model_dump(by_alias=True)
        for tooth, site in all_keys
    ]

    return PerioChartComparison(
        chartA=_chart_to_detail(chart_a, list(readings_a)).model_dump(by_alias=True),  # type: ignore[arg-type]
        chartB=_chart_to_detail(chart_b, list(readings_b)).model_dump(by_alias=True),  # type: ignore[arg-type]
        deltas=deltas,  # type: ignore[arg-type]
    )


@router.get("/{chart_id}", response_model=PerioChartDetail)
async def get_perio_chart(
    patient_id: uuid.UUID,
    chart_id: uuid.UUID,
    request: Request,
) -> PerioChartDetail:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)

    async with get_session_factory()() as session:
        chart = await session.scalar(
            select(PerioChartModel).where(
                PerioChartModel.id == chart_id,
                PerioChartModel.patient_id == patient_id,
                PerioChartModel.practice_id == practice_id,
                PerioChartModel.deleted_at.is_(None),
            )
        )
        if chart is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="CHART_NOT_FOUND", message="Perio chart not found")
                ).model_dump(by_alias=True),
            )

        readings = (
            await session.scalars(
                select(PerioReadingModel)
                .where(PerioReadingModel.perio_chart_id == chart_id)
                .order_by(PerioReadingModel.tooth_number, PerioReadingModel.site)
            )
        ).all()

        await _phi_audit(session, chart_id, user_sub)
        await session.commit()

    return _chart_to_detail(chart, list(readings))


@router.post("/{chart_id}/readings", status_code=200, response_model=PerioChartDetail)
async def upsert_readings(
    patient_id: uuid.UUID,
    chart_id: uuid.UUID,
    body: AddPerioReadings,
    request: Request,
) -> PerioChartDetail:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        chart = await session.scalar(
            select(PerioChartModel).where(
                PerioChartModel.id == chart_id,
                PerioChartModel.patient_id == patient_id,
                PerioChartModel.practice_id == practice_id,
                PerioChartModel.deleted_at.is_(None),
            )
        )
        if chart is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="CHART_NOT_FOUND", message="Perio chart not found")
                ).model_dump(by_alias=True),
            )

        await _upsert_readings(session, chart_id, body.readings)
        await session.commit()
        await session.refresh(chart)

        readings = (
            await session.scalars(
                select(PerioReadingModel)
                .where(PerioReadingModel.perio_chart_id == chart_id)
                .order_by(PerioReadingModel.tooth_number, PerioReadingModel.site)
            )
        ).all()

    logger.info(
        "Perio readings upserted: patient_id=%s chart_id=%s count=%d",
        patient_id,
        chart_id,
        len(body.readings),
    )

    return _chart_to_detail(chart, list(readings))


@router.delete("/{chart_id}", status_code=204)
async def delete_perio_chart(
    patient_id: uuid.UUID,
    chart_id: uuid.UUID,
    request: Request,
) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        chart = await session.scalar(
            select(PerioChartModel)
            .where(
                PerioChartModel.id == chart_id,
                PerioChartModel.patient_id == patient_id,
                PerioChartModel.practice_id == practice_id,
                PerioChartModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if chart is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="CHART_NOT_FOUND", message="Perio chart not found")
                ).model_dump(by_alias=True),
            )

        now = datetime.now(UTC)
        chart.deleted_at = now
        chart.updated_at = now
        await session.commit()

    logger.info("Perio chart deleted: patient_id=%s chart_id=%s", patient_id, chart_id)
