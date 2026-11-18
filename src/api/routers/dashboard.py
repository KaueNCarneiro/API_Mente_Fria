"""Router do dashboard e da exportação CSV (Fase 5 — P5-62, P5-63).

Restrito a `ADMINISTRADOR`. A exportação responde **`text/csv` UTF-8**, não JSON, e traz
o cabeçalho `Content-Disposition` declarado no contrato.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import Dashboard
from ..security import somente_administrador
from ..services import dashboard as servico
from .comum import respostas

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(somente_administrador)],
)

DataInicio = Annotated[date, Query(description="Data inicial inclusiva.")]
DataFim = Annotated[date, Query(description="Data final inclusiva.")]

MEDIA_TYPE_CSV = "text/csv; charset=utf-8"


@router.get(
    "",
    operation_id="consultarDashboard",
    summary="Consultar indicadores do dashboard",
    response_model=Dashboard,
    responses={200: {"description": "Indicadores do período."}, **respostas(400, 401, 403)},
)
def consultar_dashboard(
    dataInicio: DataInicio, dataFim: DataFim, db: Annotated[Session, Depends(get_db)]
) -> Dashboard:
    """Somente pedidos ATIVOS entram nos indicadores financeiros e no ranking."""
    return servico.consultar(db, data_inicio=dataInicio, data_fim=dataFim)


@router.get(
    "/exportacao",
    operation_id="exportarDashboardCsv",
    summary="Exportar dashboard em CSV",
    response_class=Response,
    responses={
        200: {
            "description": "Arquivo CSV gerado.",
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
            "headers": {
                "Content-Disposition": {
                    "description": "Nome sugerido do arquivo exportado.",
                    "schema": {
                        "type": "string",
                        "example": "mente-fria-dashboard-2026-10.csv",
                    },
                }
            },
        },
        **respostas(400, 401, 403),
    },
)
def exportar_dashboard_csv(
    dataInicio: DataInicio, dataFim: DataFim, db: Annotated[Session, Depends(get_db)]
) -> Response:
    """Mesmas regras de período e de pedidos ativos do dashboard, em CSV UTF-8."""
    csv_texto = servico.exportar_csv(db, data_inicio=dataInicio, data_fim=dataFim)
    nome = servico.nome_do_arquivo(dataInicio, dataFim)
    return Response(
        content=csv_texto.encode("utf-8"),
        media_type=MEDIA_TYPE_CSV,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
