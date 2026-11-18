"""Service de estoque: lotes, saldo derivado, validade, FEFO e auditoria
(Fase 5 — P5-03, P5-04, P5-12, P5-13, P5-17).

Modelo de estoque (SPEC §6.3):

- **ENTRADA** cria um lote consumível: `quantidadeRestante` inicial igual a `quantidade`,
  com `dataValidade` opcional. Lote sem validade nunca vence.
- **SAIDA** consome lotes **não vencidos** em ordem FEFO (*first expire, first out*) e
  abate `quantidadeRestante` de cada um. A saída em si não é lote: não tem saldo nem
  validade (garantido por `CHECK` no modelo).
- O saldo **deriva** dos lotes (`IngredienteModel.quantidadeEstoque` e `saldoValido` são
  expressões SQL, não colunas): nada aqui escreve saldo diretamente.
- Toda movimentação registra o `usuarioId` autenticado — a trilha de auditoria.

Fuso: "vencido" é `dataValidade < hoje` no horário de São Paulo (`models.hoje`); um lote
que vence **hoje** ainda é válido.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..exceptions import ConflitoError, NaoEncontradoError
from ..models import SAO_PAULO, IngredienteModel, MovimentacaoEstoqueModel, hoje
from ..schemas import CreateMovimentacaoEstoqueDTO
from .comum import Pagina, aplicar_ordenacao, paginar, validar_intervalo

TIPO_ENTRADA = "ENTRADA"
TIPO_SAIDA = "SAIDA"

MOTIVO_PEDIDO = "PEDIDO"
MOTIVO_CONVENCIONAL = "CONVENCIONAL"
MOTIVO_DESCARTE_VENCIDO = "DESCARTE_VENCIDO"

ORDENACAO_PERMITIDA = {
    "id": MovimentacaoEstoqueModel.id,
    "ingredienteId": MovimentacaoEstoqueModel.ingredienteId,
    "tipo": MovimentacaoEstoqueModel.tipo,
    "quantidade": MovimentacaoEstoqueModel.quantidade,
    "dataMovimentacao": MovimentacaoEstoqueModel.dataMovimentacao,
    "dataValidade": MovimentacaoEstoqueModel.dataValidade,
}


@dataclass(frozen=True, slots=True)
class Necessidade:
    """Quantidade exigida de um ingrediente em uma operação de consumo."""

    ingrediente_id: int
    quantidade: Decimal


def lotes_disponiveis(
    db: Session, ingrediente_id: int, *, data_referencia: date | None = None
) -> list[MovimentacaoEstoqueModel]:
    """Lotes consumíveis do ingrediente em ordem **FEFO**.

    Só entram ENTRADAs com saldo restante e **não vencidas**. A ordenação coloca primeiro
    o que vence antes; lotes sem validade vão para o fim (não vencem, então são
    consumidos por último) e, no empate, vale o lote mais antigo.
    """
    data_ref = data_referencia or hoje()
    m = MovimentacaoEstoqueModel
    stmt = (
        select(m)
        .where(
            m.ingredienteId == ingrediente_id,
            m.tipo == TIPO_ENTRADA,
            m.quantidadeRestante > 0,
            (m.dataValidade.is_(None)) | (m.dataValidade >= data_ref),
        )
        .order_by(m.dataValidade.is_(None), m.dataValidade.asc(), m.id.asc())
    )
    return list(db.scalars(stmt).all())


def saldo_valido(db: Session, ingrediente_id: int, *, data_referencia: date | None = None) -> Decimal:
    """Soma da `quantidadeRestante` dos lotes não vencidos."""
    return sum(
        (lote.quantidadeRestante or Decimal(0)
         for lote in lotes_disponiveis(db, ingrediente_id, data_referencia=data_referencia)),
        Decimal(0),
    )


def consumir_fefo(
    db: Session,
    *,
    ingrediente_id: int,
    quantidade: Decimal,
    usuario_id: int,
    motivo: str,
    observacao: str | None = None,
    data_referencia: date | None = None,
    registrar_saida: bool = True,
) -> MovimentacaoEstoqueModel | None:
    """Abate `quantidade` dos lotes válidos em FEFO e registra a SAIDA correspondente.

    Não faz `commit`: quem chama decide a transação — é isso que permite ao pedido gravar
    itens e baixas atomicamente (P5-06). Estoque válido insuficiente resulta em `409`, e
    **lote vencido nunca é consumido**, ainda que haja saldo vencido sobrando.
    """
    if quantidade <= 0:
        raise ConflitoError("A quantidade a consumir deve ser positiva.")

    ingrediente = db.get(IngredienteModel, ingrediente_id)
    if ingrediente is None:
        raise NaoEncontradoError(f"Ingrediente {ingrediente_id} não encontrado.")

    lotes = lotes_disponiveis(db, ingrediente_id, data_referencia=data_referencia)
    disponivel = sum((lote.quantidadeRestante or Decimal(0) for lote in lotes), Decimal(0))
    if disponivel < quantidade:
        raise ConflitoError(
            f"Estoque válido insuficiente para o ingrediente {ingrediente.nome}: "
            f"disponível {disponivel}, necessário {quantidade}."
        )

    restante = quantidade
    for lote in lotes:
        if restante <= 0:
            break
        no_lote = lote.quantidadeRestante or Decimal(0)
        usado = min(no_lote, restante)
        lote.quantidadeRestante = no_lote - usado
        restante -= usado

    if not registrar_saida:
        return None

    saida = MovimentacaoEstoqueModel(
        ingredienteId=ingrediente_id,
        usuarioId=usuario_id,
        tipo=TIPO_SAIDA,
        quantidade=quantidade,
        observacao=observacao,
        dataValidade=None,
        quantidadeRestante=None,
        motivo=motivo,
    )
    db.add(saida)
    return saida


def registrar_movimentacao(
    db: Session, dto: CreateMovimentacaoEstoqueDTO, *, usuario_id: int
) -> MovimentacaoEstoqueModel:
    """Registra ENTRADA (novo lote) ou SAIDA (consumo FEFO). `usuarioId` vem do token.

    Observação registrada no PLAN.md: o contrato aceita `motivo` `CONVENCIONAL` ou
    `DESCARTE_VENCIDO` na SAIDA, mas o SPEC §6.3 determina que **nenhuma** saída consome
    lote vencido. O motivo é gravado como dado de auditoria e não altera a seleção de
    lotes; a consequência (estoque vencido não tem como sair pelo contrato atual) está
    registrada como divergência para revisão.
    """
    ingrediente = db.get(IngredienteModel, dto.ingredienteId)
    if ingrediente is None:
        raise NaoEncontradoError("Ingrediente não encontrado.")

    if dto.tipo == TIPO_ENTRADA:
        movimentacao = MovimentacaoEstoqueModel(
            ingredienteId=dto.ingredienteId,
            usuarioId=usuario_id,
            tipo=TIPO_ENTRADA,
            quantidade=dto.quantidade,
            observacao=dto.observacao,
            dataValidade=dto.dataValidade,
            quantidadeRestante=dto.quantidade,
            motivo=dto.motivo,
        )
        db.add(movimentacao)
        db.commit()
        db.refresh(movimentacao)
        return movimentacao

    saida = consumir_fefo(
        db,
        ingrediente_id=dto.ingredienteId,
        quantidade=dto.quantidade,
        usuario_id=usuario_id,
        motivo=dto.motivo or MOTIVO_CONVENCIONAL,
        observacao=dto.observacao,
    )
    if saida is None:  # inalcançável: registrar_saida é True por padrão
        raise ConflitoError("Não foi possível registrar a saída de estoque.")
    db.commit()
    db.refresh(saida)
    return saida


def _filtrar(
    stmt: Select[tuple[MovimentacaoEstoqueModel]],
    *,
    ingrediente_id: int | None,
    tipo: str | None,
    data_inicio: date | None,
    data_fim: date | None,
) -> Select[tuple[MovimentacaoEstoqueModel]]:
    m = MovimentacaoEstoqueModel
    if ingrediente_id is not None:
        stmt = stmt.where(m.ingredienteId == ingrediente_id)
    if tipo is not None:
        stmt = stmt.where(m.tipo == tipo)
    # `dataMovimentacao` é timestamp; o filtro é por dia, inclusivo nas duas pontas.
    if data_inicio is not None:
        stmt = stmt.where(m.dataMovimentacao >= inicio_do_dia(data_inicio))
    if data_fim is not None:
        stmt = stmt.where(m.dataMovimentacao < inicio_do_dia_seguinte(data_fim))
    return stmt


def inicio_do_dia(dia: date) -> datetime:
    """Meia-noite do dia no fuso de São Paulo (o contrato trabalha nesse horário)."""
    return datetime.combine(dia, time.min, tzinfo=SAO_PAULO)


def inicio_do_dia_seguinte(dia: date) -> datetime:
    return inicio_do_dia(dia + timedelta(days=1))


def listar_movimentacoes(
    db: Session,
    *,
    page: int,
    size: int,
    sort: str | None = None,
    ingrediente_id: int | None = None,
    tipo: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> Pagina[MovimentacaoEstoqueModel]:
    """Livro de movimentações (`listarMovimentacoesEstoque`), somente leitura."""
    validar_intervalo(data_inicio, data_fim)
    stmt = _filtrar(
        select(MovimentacaoEstoqueModel),
        ingrediente_id=ingrediente_id,
        tipo=tipo,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    stmt = aplicar_ordenacao(
        stmt, sort, ORDENACAO_PERMITIDA, padrao=MovimentacaoEstoqueModel.id
    )
    return paginar(db, stmt, page=page, size=size)


def listar_movimentacoes_do_ingrediente(
    db: Session,
    ingrediente_id: int,
    *,
    page: int,
    size: int,
    tipo: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> Pagina[MovimentacaoEstoqueModel]:
    """Histórico de um ingrediente. Ingrediente inexistente resulta em `404`.

    Esta operação não declara o parâmetro `sort` no contrato: a ordem é fixa por `id`.
    """
    if db.get(IngredienteModel, ingrediente_id) is None:
        raise NaoEncontradoError("Ingrediente não encontrado.")
    validar_intervalo(data_inicio, data_fim)
    stmt = _filtrar(
        select(MovimentacaoEstoqueModel),
        ingrediente_id=ingrediente_id,
        tipo=tipo,
        data_inicio=data_inicio,
        data_fim=data_fim,
    ).order_by(MovimentacaoEstoqueModel.id.asc())
    return paginar(db, stmt, page=page, size=size)
