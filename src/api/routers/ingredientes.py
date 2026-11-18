"""Router de ingredientes (Fase 5 — P5-38 a P5-42). Restrito a `ADMINISTRADOR`.

`GET /ingredientes/{id}/movimentacoes` pertence ao contrato de estoque e fica em
`movimentacoes_estoque.py`, porque sua descrição **não** restringe perfil.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..exceptions import resposta_sem_conteudo
from ..schemas import (
    CreateIngredienteDTO,
    Ingrediente,
    PageMetadata,
    PaginatedIngredientes,
    UpdateIngredienteDTO,
)
from ..security import somente_administrador
from ..services import ingredientes as servico
from .comum import (
    BuscaQuery,
    IdPath,
    PageQuery,
    SizeQuery,
    SortQuery,
    location,
    resposta_criado,
    respostas,
)

router = APIRouter(
    prefix="/ingredientes",
    tags=["Ingredientes"],
    dependencies=[Depends(somente_administrador)],
)

UnidadeFiltro = Annotated[
    str | None, Query(max_length=20, description="Filtra ingredientes por unidade de medida.")
]
ReposicaoFiltro = Annotated[
    bool | None,
    Query(description="Filtra ingredientes conforme a necessidade de reposição."),
]


@router.get(
    "",
    operation_id="listarIngredientes",
    summary="Listar ingredientes",
    response_model=PaginatedIngredientes,
    responses={200: {"description": "Página de ingredientes."}, **respostas(400, 401, 403)},
)
def listar_ingredientes(
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 0,
    size: SizeQuery = 20,
    sort: SortQuery = None,
    q: BuscaQuery = None,
    unidadeMedida: UnidadeFiltro = None,
    precisaReposicao: ReposicaoFiltro = None,
) -> PaginatedIngredientes:
    pagina = servico.listar(
        db,
        page=page,
        size=size,
        sort=sort,
        q=q,
        unidade_medida=unidadeMedida,
        precisa_reposicao=precisaReposicao,
    )
    return PaginatedIngredientes(
        data=[Ingrediente.model_validate(i) for i in pagina.itens],
        paginacao=PageMetadata.model_validate(pagina.paginacao),
    )


@router.post(
    "",
    operation_id="cadastrarIngrediente",
    summary="Cadastrar ingrediente",
    status_code=status.HTTP_201_CREATED,
    response_model=Ingrediente,
    responses={
        201: resposta_criado("Ingrediente criado.", "/api/v1/ingredientes/5"),
        **respostas(400, 401, 403, 404, 422),
    },
)
def cadastrar_ingrediente(
    dto: CreateIngredienteDTO, response: Response, db: Annotated[Session, Depends(get_db)]
) -> Ingrediente:
    """O ingrediente nasce com estoque zero; entradas vêm por movimentação."""
    ingrediente = servico.cadastrar(db, dto)
    location(response, f"/api/v1/ingredientes/{ingrediente.id}")
    return Ingrediente.model_validate(ingrediente)


@router.get(
    "/{id}",
    operation_id="consultarIngrediente",
    summary="Consultar ingrediente por ID",
    response_model=Ingrediente,
    responses={200: {"description": "Ingrediente encontrado."}, **respostas(401, 403, 404)},
)
def consultar_ingrediente(id: IdPath, db: Annotated[Session, Depends(get_db)]) -> Ingrediente:
    return Ingrediente.model_validate(servico.obter(db, id))


@router.put(
    "/{id}",
    operation_id="atualizarIngrediente",
    summary="Atualizar ingrediente",
    response_model=Ingrediente,
    responses={
        200: {"description": "Ingrediente atualizado."},
        **respostas(400, 401, 403, 404, 422),
    },
)
def atualizar_ingrediente(
    id: IdPath, dto: UpdateIngredienteDTO, db: Annotated[Session, Depends(get_db)]
) -> Ingrediente:
    """O saldo não é editável por aqui: ele deriva dos lotes de entrada."""
    return Ingrediente.model_validate(servico.atualizar(db, id, dto))


@router.delete(
    "/{id}",
    operation_id="excluirIngrediente",
    summary="Excluir ingrediente",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Ingrediente excluído."},
        **respostas(401, 403, 404, 409),
    },
)
def excluir_ingrediente(id: IdPath, db: Annotated[Session, Depends(get_db)]) -> Response:
    """Ingrediente com composição ou histórico de movimentação responde 409."""
    servico.excluir(db, id)
    return resposta_sem_conteudo()
