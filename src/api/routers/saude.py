"""Router de saúde (Fase 5 — P5-20). Operação pública: `consultarSaude`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import HealthStatus
from ..services import saude as servico
from .comum import respostas

router = APIRouter(tags=["Saúde"])


@router.get(
    "/saude",
    operation_id="consultarSaude",
    summary="Consultar saúde da API",
    response_model=HealthStatus,
    responses={200: {"description": "API e banco disponíveis."}, **respostas(503)},
)
def consultar_saude(db: Annotated[Session, Depends(get_db)]) -> HealthStatus:
    """Endpoint público de diagnóstico da aplicação e do banco."""
    return servico.verificar(db)
