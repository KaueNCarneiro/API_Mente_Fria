"""Services de alertas de reposição e de validade (Fase 5 — P5-12, P5-13).

- **Reposição** (UC15): ingredientes cujo **saldo válido** está abaixo da quantidade
  mínima. `somenteCriticos=true` restringe, conforme o contrato, aos que estão com saldo
  válido **igual a zero**.
- **Validade** (UC16): considera somente linhas de **ENTRADA** com `dataValidade`
  informada e saldo restante. `diasAntecedencia` define o que é "próximo do vencimento";
  `incluirVencidos` (padrão `true`) inclui o que já passou da validade.

`diasAteVencimento` é negativo para lote vencido, como descreve o contrato.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import IngredienteModel, MovimentacaoEstoqueModel, hoje
from ..schemas import (
    AlertaReposicao,
    AlertaValidade,
    ListaAlertasReposicao,
    ListaAlertasValidade,
)
from .estoque import TIPO_ENTRADA

SITUACAO_PROXIMO = "PROXIMO_VENCIMENTO"
SITUACAO_VENCIDO = "VENCIDO"

DIAS_ANTECEDENCIA_PADRAO = 7


def listar_reposicao(db: Session, *, somente_criticos: bool = False) -> ListaAlertasReposicao:
    """Ingredientes abaixo do mínimo, com o déficit calculado."""
    stmt = select(IngredienteModel).where(
        IngredienteModel.saldoValido < IngredienteModel.quantidadeMinima
    )
    if somente_criticos:
        stmt = stmt.where(IngredienteModel.saldoValido == 0)
    stmt = stmt.order_by(IngredienteModel.id)

    itens = [
        AlertaReposicao(
            ingredienteId=ingrediente.id,
            nomeIngrediente=ingrediente.nome,
            quantidadeEstoqueValido=ingrediente.saldoValido,
            quantidadeMinima=ingrediente.quantidadeMinima,
            unidadeMedida=ingrediente.unidadeMedida,
            deficit=max(ingrediente.quantidadeMinima - ingrediente.saldoValido, Decimal(0)),
        )
        for ingrediente in db.scalars(stmt).all()
    ]
    return ListaAlertasReposicao(itens=itens)


def listar_validade(
    db: Session,
    *,
    dias_antecedencia: int = DIAS_ANTECEDENCIA_PADRAO,
    incluir_vencidos: bool = True,
) -> ListaAlertasValidade:
    """Lotes próximos do vencimento e, opcionalmente, já vencidos."""
    hoje_sp = hoje()
    limite = hoje_sp + timedelta(days=dias_antecedencia)
    m = MovimentacaoEstoqueModel

    stmt = (
        select(m)
        .where(
            m.tipo == TIPO_ENTRADA,
            m.dataValidade.is_not(None),
            m.quantidadeRestante > 0,
            m.dataValidade <= limite,
        )
        .options(joinedload(m.ingrediente))
        .order_by(m.dataValidade.asc(), m.id.asc())
    )
    if not incluir_vencidos:
        stmt = stmt.where(m.dataValidade >= hoje_sp)

    itens = []
    for lote in db.scalars(stmt).unique().all():
        validade = lote.dataValidade
        if validade is None:  # filtrado na consulta; guarda de tipo
            continue
        dias = (validade - hoje_sp).days
        itens.append(
            AlertaValidade(
                movimentacaoId=lote.id,
                ingredienteId=lote.ingredienteId,
                nomeIngrediente=lote.ingrediente.nome,
                dataValidade=validade,
                quantidadeRestante=lote.quantidadeRestante or Decimal(0),
                diasAteVencimento=dias,
                situacao=SITUACAO_VENCIDO if dias < 0 else SITUACAO_PROXIMO,
            )
        )
    return ListaAlertasValidade(itens=itens)
