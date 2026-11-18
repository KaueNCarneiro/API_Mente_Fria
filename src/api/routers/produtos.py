"""Router de produtos e composição (Fase 5 — P5-46 a P5-52). Restrito a `ADMINISTRADOR`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..exceptions import resposta_sem_conteudo
from ..schemas import (
    ComposicaoProduto,
    ComposicaoProdutoItem,
    CreateProdutoDTO,
    PageMetadata,
    PaginatedProdutos,
    Produto,
    SubstituirComposicaoDTO,
    UpdateProdutoDTO,
)
from ..security import somente_administrador
from ..services import produtos as servico
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
    prefix="/produtos",
    tags=["Produtos"],
    dependencies=[Depends(somente_administrador)],
)

AtivoFiltro = Annotated[bool | None, Query(description="Filtra produtos por disponibilidade.")]


def _composicao(produto: object) -> ComposicaoProduto:
    return ComposicaoProduto(
        produtoId=produto.id,  # type: ignore[attr-defined]
        itens=[
            ComposicaoProdutoItem.model_validate(linha)
            for linha in produto.composicao  # type: ignore[attr-defined]
        ],
    )


@router.get(
    "",
    operation_id="listarProdutos",
    summary="Listar produtos",
    response_model=PaginatedProdutos,
    responses={200: {"description": "Página de produtos."}, **respostas(400, 401, 403)},
)
def listar_produtos(
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 0,
    size: SizeQuery = 20,
    sort: SortQuery = None,
    q: BuscaQuery = None,
    ativo: AtivoFiltro = None,
) -> PaginatedProdutos:
    pagina = servico.listar(db, page=page, size=size, sort=sort, q=q, ativo=ativo)
    return PaginatedProdutos(
        data=[Produto.model_validate(p) for p in pagina.itens],
        paginacao=PageMetadata.model_validate(pagina.paginacao),
    )


@router.post(
    "",
    operation_id="cadastrarProduto",
    summary="Cadastrar produto",
    status_code=status.HTTP_201_CREATED,
    response_model=Produto,
    responses={
        201: resposta_criado("Produto criado.", "/api/v1/produtos/9"),
        **respostas(400, 401, 403, 404, 422),
    },
)
def cadastrar_produto(
    dto: CreateProdutoDTO, response: Response, db: Annotated[Session, Depends(get_db)]
) -> Produto:
    """Cria produto e composição juntos; ingrediente inexistente responde 404."""
    produto = servico.cadastrar(db, dto)
    location(response, f"/api/v1/produtos/{produto.id}")
    return Produto.model_validate(produto)


@router.get(
    "/{id}",
    operation_id="consultarProduto",
    summary="Consultar produto por ID",
    response_model=Produto,
    responses={200: {"description": "Produto encontrado."}, **respostas(401, 403, 404)},
)
def consultar_produto(id: IdPath, db: Annotated[Session, Depends(get_db)]) -> Produto:
    return Produto.model_validate(servico.obter(db, id))


@router.put(
    "/{id}",
    operation_id="atualizarProduto",
    summary="Atualizar produto",
    response_model=Produto,
    responses={
        200: {"description": "Produto atualizado."},
        **respostas(400, 401, 403, 404, 422),
    },
)
def atualizar_produto(
    id: IdPath, dto: UpdateProdutoDTO, db: Annotated[Session, Depends(get_db)]
) -> Produto:
    """Dados comerciais apenas: preços já registrados em pedidos não mudam."""
    return Produto.model_validate(servico.atualizar(db, id, dto))


@router.delete(
    "/{id}",
    operation_id="desativarProduto",
    summary="Desativar produto",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Produto desativado."},
        **respostas(401, 403, 404, 409),
    },
)
def desativar_produto(id: IdPath, db: Annotated[Session, Depends(get_db)]) -> Response:
    """Desativação lógica: o produto não é apagado fisicamente."""
    servico.desativar(db, id)
    return resposta_sem_conteudo()


@router.get(
    "/{id}/composicao",
    operation_id="consultarComposicaoProduto",
    summary="Consultar composição do produto",
    response_model=ComposicaoProduto,
    responses={200: {"description": "Composição do produto."}, **respostas(401, 403, 404)},
)
def consultar_composicao_produto(
    id: IdPath, db: Annotated[Session, Depends(get_db)]
) -> ComposicaoProduto:
    return _composicao(servico.obter_composicao(db, id))


@router.put(
    "/{id}/composicao",
    operation_id="substituirComposicaoProduto",
    summary="Substituir composição do produto",
    response_model=Produto,
    responses={
        200: {"description": "Composição substituída."},
        **respostas(400, 401, 403, 404, 422),
    },
)
def substituir_composicao_produto(
    id: IdPath, dto: SubstituirComposicaoDTO, db: Annotated[Session, Depends(get_db)]
) -> Produto:
    """Substituição integral: a composição anterior é descartada."""
    return Produto.model_validate(servico.substituir_composicao(db, id, dto))
