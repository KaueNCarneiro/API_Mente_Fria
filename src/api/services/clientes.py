"""Service de clientes (Fase 5 — P5-02).

Cobre `listarClientes`, `cadastrarCliente`, `consultarCliente`, `atualizarCliente` e
`excluirCliente`. Regra do SPEC §6.2: cliente referenciado por pedido **não** pode ser
excluído — responde `409` e o histórico é preservado.
"""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..exceptions import ConflitoError, NaoEncontradoError
from ..models import ClienteModel, PedidoModel
from ..schemas import CreateClienteDTO, UpdateClienteDTO
from .comum import Pagina, aplicar_ordenacao, paginar, termo_de_busca

ORDENACAO_PERMITIDA = {
    "id": ClienteModel.id,
    "nome": ClienteModel.nome,
    "contato": ClienteModel.contato,
    "endereco": ClienteModel.endereco,
}


def listar(
    db: Session, *, page: int, size: int, sort: str | None = None, q: str | None = None
) -> Pagina[ClienteModel]:
    """Lista clientes; `q` busca por nome, contato ou endereço (descrição da operação)."""
    stmt = select(ClienteModel)
    termo = termo_de_busca(q)
    if termo is not None:
        stmt = stmt.where(
            ClienteModel.nome.ilike(termo, escape="\\")
            | ClienteModel.contato.ilike(termo, escape="\\")
            | ClienteModel.endereco.ilike(termo, escape="\\")
        )
    stmt = aplicar_ordenacao(stmt, sort, ORDENACAO_PERMITIDA, padrao=ClienteModel.id)
    return paginar(db, stmt, page=page, size=size)


def obter(db: Session, cliente_id: int) -> ClienteModel:
    cliente = db.get(ClienteModel, cliente_id)
    if cliente is None:
        raise NaoEncontradoError("Cliente não encontrado.")
    return cliente


def cadastrar(db: Session, dto: CreateClienteDTO) -> ClienteModel:
    cliente = ClienteModel(
        nome=dto.nome.strip(), contato=dto.contato.strip(), endereco=dto.endereco.strip()
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


def atualizar(db: Session, cliente_id: int, dto: UpdateClienteDTO) -> ClienteModel:
    """Substituição integral dos dados cadastrais (`PUT`)."""
    cliente = obter(db, cliente_id)
    cliente.nome = dto.nome.strip()
    cliente.contato = dto.contato.strip()
    cliente.endereco = dto.endereco.strip()
    db.commit()
    db.refresh(cliente)
    return cliente


def excluir(db: Session, cliente_id: int) -> None:
    """Exclui o cliente; `409` se houver pedido associado (histórico preservado)."""
    cliente = obter(db, cliente_id)
    tem_pedido = db.scalar(select(exists().where(PedidoModel.clienteId == cliente_id)))
    if tem_pedido:
        raise ConflitoError("Cliente possui pedidos associados e não pode ser excluído.")
    db.delete(cliente)
    db.commit()
