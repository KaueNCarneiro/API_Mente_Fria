"""Service de pedidos: registro transacional e cancelamento
(Fase 5 — P5-05, P5-06, P5-07, P5-17).

Regras do SPEC §6.5:

- `usuarioId` vem do token, nunca do corpo.
- O backend captura os **preços vigentes** no momento do pedido e grava nome e preço no
  item (`PedidoItemModel`), de modo que alterar o produto depois não reescreve o
  histórico.
- Pedido, itens e baixas de estoque são gravados **na mesma transação**: qualquer falha
  derruba tudo (`rollback` integral), sem pedido sem baixa nem baixa parcial.
- Cancelar registra status, data e usuário responsável e **não devolve estoque**.

Cálculo monetário: `subtotal = precoUnitarioRegistrado * quantidade` e
`valorTotal = Σ subtotais`, sempre em `Decimal` quantizado em 2 casas (nunca `float`).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from ..exceptions import ConflitoError, NaoEncontradoError, ValidacaoError
from ..models import ClienteModel, PedidoItemModel, PedidoModel, ProdutoModel, agora
from ..schemas import ApiErrorDetail, CancelamentoPedidoDTO, CreatePedidoDTO
from .comum import Pagina, aplicar_ordenacao, paginar, validar_intervalo
from .estoque import (
    MOTIVO_PEDIDO,
    consumir_fefo,
    inicio_do_dia,
    inicio_do_dia_seguinte,
)

STATUS_ATIVO = "ATIVO"
STATUS_CANCELADO = "CANCELADO"

CENTAVOS = Decimal("0.01")

ORDENACAO_PERMITIDA = {
    "id": PedidoModel.id,
    "dataPedido": PedidoModel.dataPedido,
    "valorTotal": PedidoModel.valorTotal,
    "status": PedidoModel.status,
    "clienteId": PedidoModel.clienteId,
}


def _dinheiro(valor: Decimal) -> Decimal:
    """Arredonda para centavos (meio para cima), como se espera de valor monetário."""
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _com_itens(stmt: Select[tuple[PedidoModel]]) -> Select[tuple[PedidoModel]]:
    """Carrega os itens em lote: a resposta `Pedido` sempre os inclui (P5-19)."""
    return stmt.options(selectinload(PedidoModel.itens))


def listar(
    db: Session,
    *,
    page: int,
    size: int,
    sort: str | None = None,
    status: str | None = None,
    cliente_id: int | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> Pagina[PedidoModel]:
    """Lista pedidos com os filtros declarados. Cancelados continuam consultáveis."""
    validar_intervalo(data_inicio, data_fim)
    stmt = _com_itens(select(PedidoModel))
    if status is not None:
        stmt = stmt.where(PedidoModel.status == status)
    if cliente_id is not None:
        stmt = stmt.where(PedidoModel.clienteId == cliente_id)
    if data_inicio is not None:
        stmt = stmt.where(PedidoModel.dataPedido >= inicio_do_dia(data_inicio))
    if data_fim is not None:
        stmt = stmt.where(PedidoModel.dataPedido < inicio_do_dia_seguinte(data_fim))
    stmt = aplicar_ordenacao(stmt, sort, ORDENACAO_PERMITIDA, padrao=PedidoModel.id)
    return paginar(db, stmt, page=page, size=size)


def obter(db: Session, pedido_id: int) -> PedidoModel:
    pedido = db.scalar(_com_itens(select(PedidoModel).where(PedidoModel.id == pedido_id)))
    if pedido is None:
        raise NaoEncontradoError("Pedido não encontrado.")
    return pedido


def registrar(db: Session, dto: CreatePedidoDTO, *, usuario_id: int) -> PedidoModel:
    """Registra o pedido, os itens e as baixas de estoque em uma única transação.

    Sequência: valida cliente e produtos, captura preços, soma a necessidade de cada
    ingrediente somando **todos** os itens (um mesmo ingrediente pode aparecer em vários
    produtos), consome em FEFO e grava tudo com um único `commit`. Qualquer erro no meio
    resulta em `rollback` integral — o pedido não existe pela metade.
    """
    if not dto.itens:
        raise ValidacaoError(
            "O pedido deve conter ao menos um item.",
            detalhes=[ApiErrorDetail(campo="itens", mensagem="Informe ao menos um item.")],
        )

    if dto.clienteId is not None and db.get(ClienteModel, dto.clienteId) is None:
        raise NaoEncontradoError("Cliente não encontrado.")

    try:
        itens: list[PedidoItemModel] = []
        necessidade: dict[int, Decimal] = defaultdict(lambda: Decimal(0))
        total = Decimal(0)

        for item in dto.itens:
            produto = db.scalar(
                select(ProdutoModel)
                .where(ProdutoModel.id == item.produtoId)
                .options(selectinload(ProdutoModel.composicao))
            )
            if produto is None:
                raise NaoEncontradoError(f"Produto {item.produtoId} não encontrado.")
            if not produto.ativo:
                # Decisão da Fase 5 registrada no PLAN.md: produto desativado não é
                # vendável (é esse o sentido da desativação lógica). 409 é status
                # declarado nesta operação.
                raise ConflitoError(f"Produto {produto.nome} está desativado e não pode ser vendido.")

            preco = _dinheiro(produto.precoVenda)
            subtotal = _dinheiro(preco * item.quantidade)
            total += subtotal
            itens.append(
                PedidoItemModel(
                    produtoId=produto.id,
                    nomeProduto=produto.nome,
                    quantidade=item.quantidade,
                    precoUnitarioRegistrado=preco,
                    subtotal=subtotal,
                )
            )
            for linha in produto.composicao:
                necessidade[linha.ingredienteId] += linha.quantidadeUtilizada * item.quantidade

        pedido = PedidoModel(
            clienteId=dto.clienteId,
            usuarioId=usuario_id,
            valorTotal=_dinheiro(total),
            status=STATUS_ATIVO,
        )
        pedido.itens = itens
        db.add(pedido)
        db.flush()  # garante o id do pedido antes das baixas

        for ingrediente_id in sorted(necessidade):
            consumir_fefo(
                db,
                ingrediente_id=ingrediente_id,
                quantidade=necessidade[ingrediente_id],
                usuario_id=usuario_id,
                motivo=MOTIVO_PEDIDO,
                observacao=f"Baixa automática do pedido {pedido.id}.",
            )

        db.commit()
    except Exception:
        db.rollback()
        raise

    return obter(db, pedido.id)


def cancelar(
    db: Session, pedido_id: int, dto: CancelamentoPedidoDTO | None, *, usuario_id: int
) -> PedidoModel:
    """Cancela o pedido. **Não devolve estoque** (decisão de negócio do contrato).

    Pedido já cancelado resulta em `409`.
    """
    pedido = obter(db, pedido_id)
    if pedido.status == STATUS_CANCELADO:
        raise ConflitoError("Pedido já está cancelado.")

    pedido.status = STATUS_CANCELADO
    pedido.dataCancelamento = agora()
    pedido.usuarioCancelamentoId = usuario_id
    pedido.observacaoCancelamento = dto.observacao if dto is not None else None
    db.commit()
    return obter(db, pedido_id)


def tem_pedido_do_cliente(db: Session, cliente_id: int) -> bool:
    """Usado pela exclusão de cliente (`409` quando houver histórico)."""
    return bool(db.scalar(select(PedidoModel.id).where(PedidoModel.clienteId == cliente_id).limit(1)))


__all__ = [
    "ORDENACAO_PERMITIDA",
    "STATUS_ATIVO",
    "STATUS_CANCELADO",
    "cancelar",
    "listar",
    "obter",
    "registrar",
    "tem_pedido_do_cliente",
]
