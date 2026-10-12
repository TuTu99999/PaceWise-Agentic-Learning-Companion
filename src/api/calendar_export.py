from fastapi import APIRouter, Depends
from fastapi.responses import Response

from src.models.calendar import IcsExportRequest
from src.security import SessionContext, require_csrf
from src.services.ics_calendar import build_ics

router = APIRouter(prefix="/calendar", tags=["Calendar export"])


@router.post("/pacewise-study-plan.ics", response_class=Response)
def export_ics(
    payload: IcsExportRequest,
    session: SessionContext = Depends(require_csrf),
) -> Response:
    content = build_ics(session.user_id, payload.calendar_name, payload.blocks)
    return Response(
        content=content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="pacewise-study-plan.ics"',
            "Cache-Control": "no-store",
        },
    )
