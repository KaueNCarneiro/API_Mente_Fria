"""Router de unidades de medida (Fase 5 — P5-33 a P5-37). Restrito a `ADMINISTRADOR`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..exceptions import resposta_sem_conteudo
from ..schemas import (
    CreateUnidadeMedidaDTO,
    PageMetadata,
    PaginatedUnidadesMedida,
    UnidadeMedida,
    UpdateUnidadeMedidaDTO,
)
from ..security import somente_administrador
from ..services import unidades_medida as servico
from .comum import (
    PageQuery,
    SizeQuery,
    SortQuery,
    UnidadePath,
    location,
    resposta_criado,
    respostas,
)

router = APIRouter(
    prefix="/unidades-medida",
    tags=["Unidades de Medida"],
    dependencies=[Depends(somente_administrador)],
)


@router.get(
    "",
    operation_id="listarUnidadesMedida",
    summary="Listar unidades de medida",
    response_model=PaginatedUnidadesMedida,
    responses={200: {"description": "Página de unidades."}, **respostas(401, 403)},
)
def listar_unidades_medida(
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 0,
    size: SizeQuery = 20,
    sort: SortQuery = None,
) -> PaginatedUnidadesMedida:
    pagina = servico.listar(db, page=page, size=size, sort=sort)
    return PaginatedUnidadesMedida(
        data=[UnidadeMedida.model_validate(u) for u in pagina.itens],
        paginacao=PageMetadata.model_validate(pagina.paginacao),
    )


@router.post(
    "",
    operation_id="cadastrarUnidadeMedida",
    summary="Cadastrar unidade de medida",
    status_code=status.HTTP_201_CREATED,
    response_model=UnidadeMedida,
    responses={
        201: resposta_criado("Unidade criada.", "/api/v1/unidades-medida/g"),
        **respostas(400, 401, 403, 409, 422),
    },
)
def cadastrar_unidade_medida(
    dto: CreateUnidadeMedidaDTO, response: Response, db: Annotated[Session, Depends(get_db)]
) -> UnidadeMedida:
    unidade = servico.cadastrar(db, dto)
    location(response, f"/api/v1/unidades-medida/{unidade.unidadeMedida}")
    return UnidadeMedida.model_validate(unidade)


@router.get(
    "/{unidadeMedida}",
    operation_id="consultarUnidadeMedida",
    summary="Consultar unidade de medida",
    response_model=UnidadeMedida,
    responses={200: {"description": "Unidade encontrada."}, **respostas(401, 403, 404)},
)
def consultar_unidade_medida(
    unidadeMedida: UnidadePath, db: Annotated[Session, Depends(get_db)]
) -> UnidadeMedida:
    return UnidadeMedida.model_validate(servico.obter(db, unidadeMedida))


@router.put(
    "/{unidadeMedida}",
    operation_id="atualizarUnidadeMedida",
    summary="Atualizar porção padrão da unidade",
    response_model=UnidadeMedida,
    responses={
        200: {"description": "Unidade atualizada."},
        **respostas(400, 401, 403, 404, 422),
    },
)
def atualizar_unidade_medida(
    unidadeMedida: UnidadePath,
    dto: UpdateUnidadeMedidaDTO,
    db: Annotated[Session, Depends(get_db)],
) -> UnidadeMedida:
    """Altera a sugestão para novos ingredientes; não recalcula os existentes."""
    return UnidadeMedida.model_validate(servico.atualizar(db, unidadeMedida, dto))


@router.delete(
    "/{unidadeMedida}",
    operation_id="excluirUnidadeMedida",
    summary="Excluir unidade de medida",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Unidade excluída."},
        **respostas(401, 403, 404, 409),
    },
)
def excluir_unidade_medida(
    unidadeMedida: UnidadePath, db: Annotated[Session, Depends(get_db)]
) -> Response:
    """Unidade em uso por ingrediente não é excluída: responde 409."""
    servico.excluir(db, unidadeMedida)
    return resposta_sem_conteudo()
