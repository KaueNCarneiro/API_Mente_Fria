"""Router de movimentações de estoque (Fase 5 — P5-43, P5-44, P5-45).

As três operações exigem Bearer, mas **não** restringem perfil nas descrições do
contrato: usam `get_current_user`, sem `require_role` inventado.

Inclui `GET /ingredientes/{id}/movimentacoes`, que pertence a este domínio (tag
"Movimentações de Estoque") embora o caminho fique sob `/ingredientes`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    CreateMovimentacaoEstoqueDTO,
    MovimentacaoEstoque,
    PageMetadata,
    PaginatedMovimentacoesEstoque,
)
from ..security import UsuarioAutenticado
from ..services import estoque as servico
from .comum import (
    IdPath,
    PageQuery,
    SizeQuery,
    SortQuery,
    location,
    resposta_criado,
    respostas,
)

router = APIRouter(tags=["Movimentações de Estoque"])

TipoFiltro = Annotated[
    Literal["ENTRADA", "SAIDA"] | None, Query(description="Filtra pelo tipo da movimentação.")
]
DataInicioFiltro = Annotated[date | None, Query(description="Data inicial inclusiva.")]
DataFimFiltro = Annotated[date | None, Query(description="Data final inclusiva.")]
IngredienteFiltro = Annotated[
    int | None, Query(ge=1, description="Filtra movimentações de um ingrediente.")
]


def _pagina(pagina: servico.Pagina[object]) -> PaginatedMovimentacoesEstoque:
    return PaginatedMovimentacoesEstoque(
        data=[MovimentacaoEstoque.model_validate(m) for m in pagina.itens],
        paginacao=PageMetadata.model_validate(pagina.paginacao),
    )


@router.get(
    "/ingredientes/{id}/movimentacoes",
    operation_id="listarMovimentacoesDoIngrediente",
    summary="Listar movimentações de um ingrediente",
    response_model=PaginatedMovimentacoesEstoque,
    responses={200: {"description": "Página de movimentações."}, **respostas(401, 403, 404)},
)
def listar_movimentacoes_do_ingrediente(
    id: IdPath,
    usuario: UsuarioAutenticado,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 0,
    size: SizeQuery = 20,
    tipo: TipoFiltro = None,
    dataInicio: DataInicioFiltro = None,
    dataFim: DataFimFiltro = None,
) -> PaginatedMovimentacoesEstoque:
    """Histórico de entradas e saídas de um ingrediente específico."""
    return _pagina(
        servico.listar_movimentacoes_do_ingrediente(
            db,
            id,
            page=page,
            size=size,
            tipo=tipo,
            data_inicio=dataInicio,
            data_fim=dataFim,
        )
    )


@router.get(
    "/movimentacoes-estoque",
    operation_id="listarMovimentacoesEstoque",
    summary="Listar movimentações de estoque",
    response_model=PaginatedMovimentacoesEstoque,
    responses={200: {"description": "Página de movimentações."}, **respostas(400, 401, 403)},
)
def listar_movimentacoes_estoque(
    usuario: UsuarioAutenticado,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 0,
    size: SizeQuery = 20,
    sort: SortQuery = None,
    ingredienteId: IngredienteFiltro = None,
    tipo: TipoFiltro = None,
    dataInicio: DataInicioFiltro = None,
    dataFim: DataFimFiltro = None,
) -> PaginatedMovimentacoesEstoque:
    """Livro de movimentações: somente leitura, para preservar a auditoria."""
    return _pagina(
        servico.listar_movimentacoes(
            db,
            page=page,
            size=size,
            sort=sort,
            ingrediente_id=ingredienteId,
            tipo=tipo,
            data_inicio=dataInicio,
            data_fim=dataFim,
        )
    )


@router.post(
    "/movimentacoes-estoque",
    operation_id="registrarMovimentacaoEstoque",
    summary="Registrar movimentação de estoque",
    status_code=status.HTTP_201_CREATED,
    response_model=MovimentacaoEstoque,
    responses={
        201: resposta_criado("Movimentação registrada.", "/api/v1/movimentacoes-estoque/31"),
        **respostas(400, 401, 403, 404, 409, 422),
    },
)
def registrar_movimentacao_estoque(
    dto: CreateMovimentacaoEstoqueDTO,
    response: Response,
    usuario: UsuarioAutenticado,
    db: Annotated[Session, Depends(get_db)],
) -> MovimentacaoEstoque:
    """ENTRADA cria lote; SAIDA consome lotes válidos em FEFO. `usuarioId` vem do token."""
    movimentacao = servico.registrar_movimentacao(db, dto, usuario_id=usuario.id)
    location(response, f"/api/v1/movimentacoes-estoque/{movimentacao.id}")
    return MovimentacaoEstoque.model_validate(movimentacao)
