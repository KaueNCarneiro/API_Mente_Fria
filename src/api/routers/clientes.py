"""Router de clientes (Fase 5 — P5-28 a P5-32).

Operações liberadas a **ADMINISTRADOR e FUNCIONARIO** ("Atores autorizados" nas
descrições do contrato).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..exceptions import resposta_sem_conteudo
from ..schemas import (
    Cliente,
    CreateClienteDTO,
    PageMetadata,
    PaginatedClientes,
    UpdateClienteDTO,
)
from ..security import administrador_ou_funcionario
from ..services import clientes as servico
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
    prefix="/clientes",
    tags=["Clientes"],
    dependencies=[Depends(administrador_ou_funcionario)],
)


@router.get(
    "",
    operation_id="listarClientes",
    summary="Listar clientes",
    response_model=PaginatedClientes,
    responses={200: {"description": "Página de clientes."}, **respostas(400, 401, 403)},
)
def listar_clientes(
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 0,
    size: SizeQuery = 20,
    sort: SortQuery = None,
    q: BuscaQuery = None,
) -> PaginatedClientes:
    pagina = servico.listar(db, page=page, size=size, sort=sort, q=q)
    return PaginatedClientes(
        data=[Cliente.model_validate(c) for c in pagina.itens],
        paginacao=PageMetadata.model_validate(pagina.paginacao),
    )


@router.post(
    "",
    operation_id="cadastrarCliente",
    summary="Cadastrar cliente",
    status_code=status.HTTP_201_CREATED,
    response_model=Cliente,
    responses={
        201: resposta_criado("Cliente criado.", "/api/v1/clientes/7"),
        **respostas(400, 401, 403, 422),
    },
)
def cadastrar_cliente(
    dto: CreateClienteDTO, response: Response, db: Annotated[Session, Depends(get_db)]
) -> Cliente:
    cliente = servico.cadastrar(db, dto)
    location(response, f"/api/v1/clientes/{cliente.id}")
    return Cliente.model_validate(cliente)


@router.get(
    "/{id}",
    operation_id="consultarCliente",
    summary="Consultar cliente por ID",
    response_model=Cliente,
    responses={200: {"description": "Cliente encontrado."}, **respostas(401, 403, 404)},
)
def consultar_cliente(id: IdPath, db: Annotated[Session, Depends(get_db)]) -> Cliente:
    return Cliente.model_validate(servico.obter(db, id))


@router.put(
    "/{id}",
    operation_id="atualizarCliente",
    summary="Atualizar cliente",
    response_model=Cliente,
    responses={
        200: {"description": "Cliente atualizado."},
        **respostas(400, 401, 403, 404, 422),
    },
)
def atualizar_cliente(
    id: IdPath, dto: UpdateClienteDTO, db: Annotated[Session, Depends(get_db)]
) -> Cliente:
    return Cliente.model_validate(servico.atualizar(db, id, dto))


@router.delete(
    "/{id}",
    operation_id="excluirCliente",
    summary="Excluir cliente",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Cliente excluído."},
        **respostas(401, 403, 404, 409),
    },
)
def excluir_cliente(id: IdPath, db: Annotated[Session, Depends(get_db)]) -> Response:
    """Cliente referenciado por pedido não é excluído: responde 409."""
    servico.excluir(db, id)
    return resposta_sem_conteudo()
