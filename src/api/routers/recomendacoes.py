"""Router de recomendações (Fase 5 — P5-59, P5-60). Restrito a `ADMINISTRADOR`.

Resultados são calculados sob demanda e não criam histórico persistido. Quando o solver
está indisponível, o service levanta `DependenciaIndisponivelError` e o handler devolve
`503` com `ApiError`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import CreateReposicaoDTO, ProducaoRecomendacao, ReposicaoRecomendacao
from ..security import somente_administrador
from ..services import recomendacoes as servico
from .comum import respostas

router = APIRouter(
    prefix="/recomendacoes",
    tags=["Recomendações"],
    dependencies=[Depends(somente_administrador)],
)


@router.post(
    "/producao",
    operation_id="calcularRecomendacaoProducao",
    summary="Calcular recomendação de produção",
    response_model=ProducaoRecomendacao,
    responses={
        200: {"description": "Recomendação calculada."},
        **respostas(401, 403, 422, 503),
    },
)
def calcular_recomendacao_producao(
    db: Annotated[Session, Depends(get_db)],
) -> ProducaoRecomendacao:
    """PLI que maximiza o lucro estimado respeitando o estoque válido."""
    return servico.recomendar_producao(db)


@router.post(
    "/reposicao",
    operation_id="calcularRecomendacaoReposicao",
    summary="Calcular recomendação de reposição",
    response_model=ReposicaoRecomendacao,
    responses={
        200: {"description": "Recomendação calculada."},
        **respostas(400, 401, 403, 422, 503),
    },
)
def calcular_recomendacao_reposicao(
    dto: CreateReposicaoDTO, db: Annotated[Session, Depends(get_db)]
) -> ReposicaoRecomendacao:
    """Compras sugeridas para o período informado, dentro do orçamento."""
    return servico.recomendar_reposicao(db, dto)
