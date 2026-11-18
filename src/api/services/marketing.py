"""Service de sugestões de marketing (Fase 5 — P5-14).

As sugestões são **informativas**: nada é publicado automaticamente e nada é gravado
(SPEC §6.6 — "não há histórico persistido no modelo atual"). O texto é montado a partir
dos dados comerciais que já existem no banco; não há geração externa nem chamada a
serviço de terceiros.

O contrato declara `503` nesta operação; ele fica reservado a uma eventual dependência
externa de geração. Na implementação atual **não há** dependência externa, então o `503`
não é emitido — registrado no PLAN.md.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    IngredienteModel,
    MovimentacaoEstoqueModel,
    PedidoItemModel,
    PedidoModel,
    ProdutoModel,
    agora,
    hoje,
)
from ..schemas import SugestaoMarketing
from .estoque import TIPO_ENTRADA, inicio_do_dia

# Janela de vendas considerada e horizonte de vencimento usados nas sugestões.
DIAS_DE_VENDAS = 30
DIAS_PARA_VENCER = 7
LIMITE_DESTAQUES = 3


def gerar(db: Session) -> SugestaoMarketing:
    """Monta sugestões a partir de vendas recentes, validade e produtos parados."""
    hoje_sp = hoje()
    desde = inicio_do_dia(hoje_sp - timedelta(days=DIAS_DE_VENDAS))

    mais_vendidos = db.execute(
        select(PedidoItemModel.nomeProduto, func.sum(PedidoItemModel.quantidade).label("total"))
        .join(PedidoModel, PedidoModel.id == PedidoItemModel.pedidoId)
        .where(PedidoModel.status == "ATIVO", PedidoModel.dataPedido >= desde)
        .group_by(PedidoItemModel.nomeProduto)
        .order_by(func.sum(PedidoItemModel.quantidade).desc())
        .limit(LIMITE_DESTAQUES)
    ).all()

    m = MovimentacaoEstoqueModel
    a_vencer = db.execute(
        select(IngredienteModel.nome, func.min(m.dataValidade))
        .join(IngredienteModel, IngredienteModel.id == m.ingredienteId)
        .where(
            m.tipo == TIPO_ENTRADA,
            m.quantidadeRestante > 0,
            m.dataValidade.is_not(None),
            m.dataValidade >= hoje_sp,
            m.dataValidade <= hoje_sp + timedelta(days=DIAS_PARA_VENCER),
        )
        .group_by(IngredienteModel.nome)
        .order_by(func.min(m.dataValidade))
        .limit(LIMITE_DESTAQUES)
    ).all()

    vendidos = {nome for nome, _ in mais_vendidos}
    parados = list(
        db.scalars(
            select(ProdutoModel.nome)
            .where(ProdutoModel.ativo.is_(True), ProdutoModel.nome.not_in(vendidos or {""}))
            .order_by(ProdutoModel.nome)
            .limit(LIMITE_DESTAQUES)
        ).all()
    )

    sugestoes: list[str] = []

    for nome, total in mais_vendidos:
        sugestoes.append(
            f"Destaque o produto {nome}: {int(total)} unidade(s) vendida(s) nos últimos "
            f"{DIAS_DE_VENDAS} dias. Vale manter em evidência no balcão e nas redes."
        )

    for nome, validade in a_vencer:
        dias = (validade - hoje_sp).days
        sugestoes.append(
            f"Crie uma promoção com {nome}: há lote vencendo em {dias} dia(s) "
            f"({validade.isoformat()}). Girar esse estoque evita perda."
        )

    for nome in parados:
        sugestoes.append(
            f"O produto {nome} não registrou vendas nos últimos {DIAS_DE_VENDAS} dias. "
            "Uma degustação ou combo pode reaquecer a procura."
        )

    if not sugestoes:
        sugestoes.append(
            "Ainda não há vendas, lotes a vencer ou produtos cadastrados suficientes para "
            "gerar sugestões. Registre pedidos e entradas de estoque para obter recomendações."
        )

    faturamento = db.scalar(
        select(func.coalesce(func.sum(PedidoModel.valorTotal), Decimal(0))).where(
            PedidoModel.status == "ATIVO", PedidoModel.dataPedido >= desde
        )
    )

    return SugestaoMarketing(
        geradoEm=agora(),
        sugestoes=sugestoes,
        observacao=(
            f"Sugestões informativas geradas sob demanda a partir dos últimos "
            f"{DIAS_DE_VENDAS} dias de pedidos ativos (faturamento considerado: "
            f"R$ {faturamento or Decimal(0)}) e dos lotes com validade em até "
            f"{DIAS_PARA_VENCER} dias. Nada é publicado automaticamente nem armazenado."
        ),
    )
