"""Router de alertas (Fase 5 — P5-57, P5-58).

As duas operações exigem Bearer, sem restrição de perfil nas descrições do contrato.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ListaAlertasReposicao, ListaAlertasValidade
from ..security import UsuarioAutenticado
from ..services import alertas as servico
from .comum import respostas

router = APIRouter(prefix="/alertas", tags=["Alertas"])

SomenteCriticos = Annotated[
    bool,
    Query(description="Quando true, retorna somente ingredientes com saldo válido igual a zero."),
]
DiasAntecedencia = Annotated[
    int,
    Query(
        ge=0,
        le=365,
        description="Quantidade de dias para considerar uma linha próxima do vencimento.",
    ),
]
IncluirVencidos = Annotated[
    bool, Query(description="Inclui linhas cuja data de validade já passou.")
]


@router.get(
    "/reposicao",
    operation_id="listarAlertasReposicao",
    summary="Listar alertas de reposição",
    response_model=ListaAlertasReposicao,
    responses={200: {"description": "Alertas de reposição."}, **respostas(401, 403)},
)
def listar_alertas_reposicao(
    usuario: UsuarioAutenticado,
    db: Annotated[Session, Depends(get_db)],
    somenteCriticos: SomenteCriticos = False,
) -> ListaAlertasReposicao:
    """Ingredientes cujo saldo válido está abaixo da quantidade mínima."""
    return servico.listar_reposicao(db, somente_criticos=somenteCriticos)


@router.get(
    "/validade",
    operation_id="listarAlertasValidade",
    summary="Listar alertas de validade",
    response_model=ListaAlertasValidade,
    responses={200: {"description": "Alertas de validade."}, **respostas(400, 401, 403)},
)
def listar_alertas_validade(
    usuario: UsuarioAutenticado,
    db: Annotated[Session, Depends(get_db)],
    diasAntecedencia: DiasAntecedencia = 7,
    incluirVencidos: IncluirVencidos = True,
) -> ListaAlertasValidade:
    """Somente linhas de ENTRADA com validade informada e saldo restante."""
    return servico.listar_validade(
        db, dias_antecedencia=diasAntecedencia, incluir_vencidos=incluirVencidos
    )
