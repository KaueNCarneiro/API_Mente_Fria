"""Router de sugestões de marketing (Fase 5 — P5-61). Restrito a `ADMINISTRADOR`.

A tag no contrato é "Recomendações"; o router é separado por domínio, como pede o
STYLEGUIDE, mas preserva a tag declarada.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import SugestaoMarketing
from ..security import somente_administrador
from ..services import marketing as servico
from .comum import respostas

router = APIRouter(
    prefix="/sugestoes-marketing",
    tags=["Recomendações"],
    dependencies=[Depends(somente_administrador)],
)


@router.post(
    "",
    operation_id="gerarSugestoesMarketing",
    summary="Gerar sugestões de marketing",
    response_model=SugestaoMarketing,
    responses={
        200: {"description": "Sugestões geradas."},
        **respostas(401, 403, 503),
    },
)
def gerar_sugestoes_marketing(db: Annotated[Session, Depends(get_db)]) -> SugestaoMarketing:
    """Sugestões informativas: nada é publicado automaticamente nem armazenado."""
    return servico.gerar(db)
