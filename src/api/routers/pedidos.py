"""Router de pedidos (Fase 5 — P5-53 a P5-56).

As quatro operações exigem Bearer sem restrição de perfil nas descrições do contrato.
`usuarioId` do pedido e do cancelamento vem sempre do token.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    CancelamentoPedidoDTO,
    CreatePedidoDTO,
    PageMetadata,
    PaginatedPedidos,
    Pedido,
)
from ..security import UsuarioAutenticado
from ..services import pedidos as servico
from .comum import (
    IdPath,
    PageQuery,
    SizeQuery,
    SortQuery,
    location,
    resposta_criado,
    respostas,
)

router = APIRouter(prefix="/pedidos", tags=["Pedidos"])

# O contrato declara o corpo do cancelamento como **não obrigatório**, com schema
# `CancelamentoPedidoDTO`. Um default anulável (`DTO | None = None`) geraria
# `anyOf[DTO, null]` no OpenAPI, divergindo do contrato; uma instância vazia como padrão
# mantém o `$ref` puro e o corpo opcional. Nada a muta, então compartilhá-la é seguro.
CANCELAMENTO_SEM_OBSERVACAO = CancelamentoPedidoDTO()

# `status` é o nome do parâmetro no contrato; o alias evita colidir com o módulo
# `status` do FastAPI, importado aqui para os códigos HTTP.
StatusFiltro = Annotated[
    Literal["ATIVO", "CANCELADO"] | None,
    Query(alias="status", description="Filtra pedidos pelo status."),
]
ClienteFiltro = Annotated[int | None, Query(ge=1, description="Filtra pedidos de um cliente.")]
DataInicioFiltro = Annotated[date | None, Query(description="Data inicial inclusiva.")]
DataFimFiltro = Annotated[date | None, Query(description="Data final inclusiva.")]


@router.get(
    "",
    operation_id="listarPedidos",
    summary="Listar pedidos",
    response_model=PaginatedPedidos,
    responses={200: {"description": "Página de pedidos."}, **respostas(400, 401, 403)},
)
def listar_pedidos(
    usuario: UsuarioAutenticado,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 0,
    size: SizeQuery = 20,
    sort: SortQuery = None,
    status_pedido: StatusFiltro = None,
    clienteId: ClienteFiltro = None,
    dataInicio: DataInicioFiltro = None,
    dataFim: DataFimFiltro = None,
) -> PaginatedPedidos:
    """Pedidos cancelados permanecem consultáveis aqui."""
    pagina = servico.listar(
        db,
        page=page,
        size=size,
        sort=sort,
        status=status_pedido,
        cliente_id=clienteId,
        data_inicio=dataInicio,
        data_fim=dataFim,
    )
    return PaginatedPedidos(
        data=[Pedido.model_validate(p) for p in pagina.itens],
        paginacao=PageMetadata.model_validate(pagina.paginacao),
    )


@router.post(
    "",
    operation_id="registrarPedido",
    summary="Registrar pedido",
    status_code=status.HTTP_201_CREATED,
    response_model=Pedido,
    responses={
        201: resposta_criado("Pedido registrado.", "/api/v1/pedidos/44"),
        **respostas(400, 401, 403, 404, 409, 422),
    },
)
def registrar_pedido(
    dto: CreatePedidoDTO,
    response: Response,
    usuario: UsuarioAutenticado,
    db: Annotated[Session, Depends(get_db)],
) -> Pedido:
    """Captura preços vigentes, calcula o total e baixa o estoque na mesma transação."""
    pedido = servico.registrar(db, dto, usuario_id=usuario.id)
    location(response, f"/api/v1/pedidos/{pedido.id}")
    return Pedido.model_validate(pedido)


@router.get(
    "/{id}",
    operation_id="consultarPedido",
    summary="Consultar pedido por ID",
    response_model=Pedido,
    responses={200: {"description": "Pedido encontrado."}, **respostas(401, 403, 404)},
)
def consultar_pedido(
    id: IdPath, usuario: UsuarioAutenticado, db: Annotated[Session, Depends(get_db)]
) -> Pedido:
    return Pedido.model_validate(servico.obter(db, id))


@router.post(
    "/{id}/cancelamento",
    operation_id="cancelarPedido",
    summary="Cancelar pedido",
    response_model=Pedido,
    responses={
        200: {"description": "Pedido cancelado."},
        **respostas(401, 403, 404, 409, 422),
    },
)
def cancelar_pedido(
    id: IdPath,
    usuario: UsuarioAutenticado,
    db: Annotated[Session, Depends(get_db)],
    dto: CancelamentoPedidoDTO = CANCELAMENTO_SEM_OBSERVACAO,
) -> Pedido:
    """Registra status, data e usuário responsável. **Não** devolve estoque."""
    return Pedido.model_validate(servico.cancelar(db, id, dto, usuario_id=usuario.id))
