"""Modelos ORM SQLAlchemy 2.0 (Fase 3 — P3-01 a P3-17).

Decisões de modelagem (registradas no PLAN.md):

- Nomes físicos de tabelas conforme SPEC.md §4.1; colunas em ``snake_case``.
- Os atributos Python dos campos expostos pelo contrato usam o MESMO nome JSON
  (camelCase), pois os schemas Pydantic (``from_attributes=True``, sem aliases —
  P2-56) leem os atributos diretamente. Atributos internos (ex.: ``senha_hash``) ficam
  em ``snake_case`` e nunca constam de schema algum.
- Dinheiro: ``Numeric(10, 2)`` (máx. contratual 99.999.999,99); quantidades:
  ``Numeric(10, 3)`` (máx. contratual 9.999.999,999); totais de pedido/subtotais:
  ``Numeric(15, 2)`` (contrato sem máximo). Sempre ``Decimal`` no Python, nunca ``float``.
- Datas/horas: ``date`` para validade; ``datetime`` com fuso (``TimestampTZ``): grava
  UTC e devolve ``America/Sao_Paulo`` (o contrato define o horário de São Paulo).
- Integridade/histórico: toda FK de dado histórico usa ``ON DELETE RESTRICT`` e as
  coleções usam ``passive_deletes="all"`` — o ORM nunca anula nem apaga filhos; o banco
  recusa a exclusão. Única cascata destrutiva: a composição do produto (não é histórico;
  pedidos guardam nome/preço próprios), necessária à substituição integral.
- O saldo do ingrediente NÃO é coluna: ``quantidadeEstoque`` e ``saldoValido`` são
  expressões derivadas (``column_property``) das entradas (lotes) em
  ``movimentacoes_estoque``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
    bindparam,
    func,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    column_property,
    mapped_column,
    relationship,
)
from sqlalchemy.types import TypeDecorator

__all__ = [
    "Base",
    "ClienteModel",
    "ComposicaoProdutoModel",
    "IngredienteModel",
    "MovimentacaoEstoqueModel",
    "PedidoItemModel",
    "PedidoModel",
    "ProdutoModel",
    "TimestampTZ",
    "UnidadeMedidaModel",
    "UsuarioModel",
    "agora",
    "hoje",
]

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def agora() -> datetime:
    """Instante atual com fuso de São Paulo (padrão dos timestamps do contrato)."""
    return datetime.now(UTC).astimezone(SAO_PAULO)


def hoje() -> date:
    """Data atual em São Paulo (referência para validade de lotes)."""
    return agora().date()


class TimestampTZ(TypeDecorator[datetime]):
    """``datetime`` com fuso: armazena UTC (naive) e devolve horário de São Paulo.

    O SQLite não guarda fuso; sem este tipo, valores com offset voltariam sem
    ``tzinfo``. Valores sem fuso são recusados (evita ambiguidade silenciosa).
    """

    impl = DateTime(timezone=False)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime sem fuso horário não é aceito; use um valor com fuso")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC).astimezone(SAO_PAULO)


# Nomes determinísticos de constraints (úteis a futuras migrações).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa única (P3-01)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _dinheiro() -> Numeric[Decimal]:
    return Numeric(10, 2)


def _quantidade() -> Numeric[Decimal]:
    return Numeric(10, 3)


def _total() -> Numeric[Decimal]:
    return Numeric(15, 2)


# ---------------------------------------------------------------------------
# 1. Usuários
# ---------------------------------------------------------------------------


class UsuarioModel(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        UniqueConstraint("email"),
        CheckConstraint("perfil IN ('ADMINISTRADOR', 'FUNCIONARIO')", name="perfil"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(150))
    # Somente o hash (nunca a senha); atributo interno, fora de qualquer schema.
    senha_hash: Mapped[str] = mapped_column(String(255))
    perfil: Mapped[str] = mapped_column(String(13))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    pedidos: Mapped[list[PedidoModel]] = relationship(
        back_populates="usuario",
        foreign_keys="PedidoModel.usuarioId",
        passive_deletes="all",
    )
    movimentacoes: Mapped[list[MovimentacaoEstoqueModel]] = relationship(
        back_populates="usuario", passive_deletes="all"
    )

    def __repr__(self) -> str:  # sem hash/senha
        return f"UsuarioModel(id={self.id!r}, email={self.email!r}, perfil={self.perfil!r})"


# ---------------------------------------------------------------------------
# 2. Clientes
# ---------------------------------------------------------------------------


class ClienteModel(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(150))
    contato: Mapped[str] = mapped_column(String(50))
    endereco: Mapped[str] = mapped_column(String(255))

    pedidos: Mapped[list[PedidoModel]] = relationship(
        back_populates="cliente", passive_deletes="all"
    )


# ---------------------------------------------------------------------------
# 3. Unidades de medida
# ---------------------------------------------------------------------------


class UnidadeMedidaModel(Base):
    __tablename__ = "unidades_medida"
    __table_args__ = (CheckConstraint("porcao_padrao >= 0.001", name="porcao_padrao"),)

    unidadeMedida: Mapped[str] = mapped_column("unidade_medida", String(20), primary_key=True)
    porcaoPadrao: Mapped[Decimal] = mapped_column("porcao_padrao", _quantidade())

    ingredientes: Mapped[list[IngredienteModel]] = relationship(
        back_populates="unidade", passive_deletes="all"
    )


# ---------------------------------------------------------------------------
# 4. Ingredientes
# ---------------------------------------------------------------------------


class IngredienteModel(Base):
    __tablename__ = "ingredientes"
    __table_args__ = (
        CheckConstraint("custo_unitario >= 0", name="custo_unitario"),
        CheckConstraint("porcao_padrao >= 0.001", name="porcao_padrao"),
        CheckConstraint("quantidade_minima >= 0", name="quantidade_minima"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(100))
    unidadeMedida: Mapped[str] = mapped_column(
        "unidade_medida",
        String(20),
        ForeignKey("unidades_medida.unidade_medida", ondelete="RESTRICT"),
        index=True,
    )
    custoUnitario: Mapped[Decimal] = mapped_column("custo_unitario", _dinheiro())
    porcaoPadrao: Mapped[Decimal] = mapped_column("porcao_padrao", _quantidade())
    # Opcional no DTO de cadastro; sem valor informado, o limite de alerta é zero.
    quantidadeMinima: Mapped[Decimal] = mapped_column(
        "quantidade_minima", _quantidade(), default=Decimal(0), server_default="0"
    )

    unidade: Mapped[UnidadeMedidaModel] = relationship(back_populates="ingredientes")
    movimentacoes: Mapped[list[MovimentacaoEstoqueModel]] = relationship(
        back_populates="ingrediente", passive_deletes="all"
    )
    composicoes: Mapped[list[ComposicaoProdutoModel]] = relationship(
        back_populates="ingrediente", passive_deletes="all"
    )

    # Derivados de movimentacoes_estoque, atribuídos após MovimentacaoEstoqueModel
    # (NÃO anotar aqui: uma anotação Mapped[...] viraria coluna física):
    #   quantidadeEstoque -> soma de quantidadeRestante das ENTRADAS (contrato);
    #   saldoValido       -> idem, excluindo lotes vencidos (validade < hoje em SP).

    @property
    def precisaReposicao(self) -> bool:
        """Saldo válido abaixo do limite mínimo (contrato: ``precisaReposicao``)."""
        return self.saldoValido < self.quantidadeMinima  # type: ignore[attr-defined,no-any-return]


# ---------------------------------------------------------------------------
# 5. Movimentações de estoque / lotes
# ---------------------------------------------------------------------------


class MovimentacaoEstoqueModel(Base):
    __tablename__ = "movimentacoes_estoque"
    __table_args__ = (
        CheckConstraint("tipo IN ('ENTRADA', 'SAIDA')", name="tipo"),
        CheckConstraint(
            "motivo IS NULL OR motivo IN ('PEDIDO', 'CONVENCIONAL', 'DESCARTE_VENCIDO')",
            name="motivo",
        ),
        CheckConstraint("quantidade >= 0.001", name="quantidade"),
        # ENTRADA = lote consumível; SAIDA não tem saldo nem validade (contrato).
        CheckConstraint(
            "(tipo = 'ENTRADA' AND quantidade_restante IS NOT NULL"
            " AND quantidade_restante >= 0 AND quantidade_restante <= quantidade)"
            " OR (tipo = 'SAIDA' AND quantidade_restante IS NULL AND data_validade IS NULL)",
            name="lote_coerente",
        ),
        # Consulta FEFO / saldo: lotes do ingrediente por validade.
        Index("ix_movimentacoes_lotes", "ingrediente_id", "tipo", "data_validade"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ingredienteId: Mapped[int] = mapped_column(
        "ingrediente_id", Integer, ForeignKey("ingredientes.id", ondelete="RESTRICT")
    )
    usuarioId: Mapped[int] = mapped_column(
        "usuario_id", Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    tipo: Mapped[str] = mapped_column(String(7))
    quantidade: Mapped[Decimal] = mapped_column(_quantidade())
    dataMovimentacao: Mapped[datetime] = mapped_column(
        "data_movimentacao", TimestampTZ(), default=agora, index=True
    )
    observacao: Mapped[str | None] = mapped_column(String(255))
    dataValidade: Mapped[date | None] = mapped_column("data_validade", Date)
    quantidadeRestante: Mapped[Decimal | None] = mapped_column("quantidade_restante", _quantidade())
    motivo: Mapped[str | None] = mapped_column(String(20))

    ingrediente: Mapped[IngredienteModel] = relationship(back_populates="movimentacoes")
    usuario: Mapped[UsuarioModel] = relationship(back_populates="movimentacoes")


def _saldo_entradas(*, somente_validas: bool) -> Any:
    """Subconsulta correlacionada: soma da ``quantidadeRestante`` das entradas."""
    m = MovimentacaoEstoqueModel
    condicoes = [m.ingredienteId == IngredienteModel.id, m.tipo == "ENTRADA"]
    if somente_validas:
        # `hoje` é avaliado a cada execução (data de São Paulo), não na importação.
        data_ref = bindparam("data_ref_saldo_valido", callable_=hoje, type_=Date)
        condicoes.append((m.dataValidade.is_(None)) | (m.dataValidade >= data_ref))
    return (
        select(func.coalesce(func.sum(m.quantidadeRestante), 0))
        .where(*condicoes)
        .correlate_except(m)
        .scalar_subquery()
    )


# Saldos DERIVADOS (somente leitura): nenhuma coluna editável de saldo (P3-05/P3-16).
# Valores refletem o banco; após escritas, a sessão precisa expirar/refazer a leitura
# (``commit`` já expira; ou ``session.refresh``).
IngredienteModel.quantidadeEstoque = column_property(  # type: ignore[attr-defined]
    _saldo_entradas(somente_validas=False)
)
IngredienteModel.saldoValido = column_property(  # type: ignore[attr-defined]
    _saldo_entradas(somente_validas=True)
)


# ---------------------------------------------------------------------------
# 6. Produtos
# ---------------------------------------------------------------------------


class ProdutoModel(Base):
    __tablename__ = "produtos"
    __table_args__ = (CheckConstraint("preco_venda >= 0.01", name="preco_venda"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(100))
    precoVenda: Mapped[Decimal] = mapped_column("preco_venda", _dinheiro())
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    # Composição: pertence ao produto e é substituída integralmente (delete-orphan).
    # Não é histórico comercial (pedidos guardam nome/preço próprios).
    composicao: Mapped[list[ComposicaoProdutoModel]] = relationship(
        back_populates="produto",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ComposicaoProdutoModel.ingredienteId",
    )
    itensPedido: Mapped[list[PedidoItemModel]] = relationship(
        back_populates="produto", passive_deletes="all"
    )


# ---------------------------------------------------------------------------
# 7. Composição do produto (N:N produto–ingrediente)
# ---------------------------------------------------------------------------


class ComposicaoProdutoModel(Base):
    __tablename__ = "composicoes_produto"
    __table_args__ = (CheckConstraint("quantidade_utilizada >= 0.001", name="quantidade_utilizada"),)

    # Chave composta: impede o mesmo ingrediente duas vezes na composição do produto.
    produtoId: Mapped[int] = mapped_column(
        "produto_id", Integer, ForeignKey("produtos.id", ondelete="CASCADE"), primary_key=True
    )
    ingredienteId: Mapped[int] = mapped_column(
        "ingrediente_id",
        Integer,
        ForeignKey("ingredientes.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
    quantidadeUtilizada: Mapped[Decimal] = mapped_column("quantidade_utilizada", _quantidade())

    produto: Mapped[ProdutoModel] = relationship(back_populates="composicao")
    ingrediente: Mapped[IngredienteModel] = relationship(back_populates="composicoes")

    # Campos de leitura de ``ComposicaoProdutoItem`` (derivados do ingrediente).
    @property
    def nomeIngrediente(self) -> str:
        return self.ingrediente.nome

    @property
    def unidadeMedida(self) -> str:
        return self.ingrediente.unidadeMedida


# ---------------------------------------------------------------------------
# 8. Pedidos
# ---------------------------------------------------------------------------


class PedidoModel(Base):
    __tablename__ = "pedidos"
    __table_args__ = (
        CheckConstraint("status IN ('ATIVO', 'CANCELADO')", name="status"),
        CheckConstraint("valor_total >= 0", name="valor_total"),
        # Dados de cancelamento só existem em pedidos CANCELADO (contrato).
        CheckConstraint(
            "(status = 'ATIVO' AND data_cancelamento IS NULL"
            " AND usuario_cancelamento_id IS NULL AND observacao_cancelamento IS NULL)"
            " OR (status = 'CANCELADO' AND data_cancelamento IS NOT NULL"
            " AND usuario_cancelamento_id IS NOT NULL)",
            name="cancelamento_coerente",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Opcional: venda sem cliente cadastrado. RESTRICT (nunca SET NULL): preserva histórico.
    clienteId: Mapped[int | None] = mapped_column(
        "cliente_id", Integer, ForeignKey("clientes.id", ondelete="RESTRICT"), index=True
    )
    usuarioId: Mapped[int] = mapped_column(
        "usuario_id", Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    dataPedido: Mapped[datetime] = mapped_column(
        "data_pedido", TimestampTZ(), default=agora, index=True
    )
    valorTotal: Mapped[Decimal] = mapped_column("valor_total", _total())
    status: Mapped[str] = mapped_column(String(9), default="ATIVO", server_default="ATIVO")
    dataCancelamento: Mapped[datetime | None] = mapped_column("data_cancelamento", TimestampTZ())
    usuarioCancelamentoId: Mapped[int | None] = mapped_column(
        "usuario_cancelamento_id", Integer, ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    # Justificativa de ``CancelamentoPedidoDTO.observacao`` (não exposta em ``Pedido``).
    observacaoCancelamento: Mapped[str | None] = mapped_column("observacao_cancelamento", String(255))

    cliente: Mapped[ClienteModel | None] = relationship(back_populates="pedidos")
    usuario: Mapped[UsuarioModel] = relationship(
        back_populates="pedidos", foreign_keys=[usuarioId]
    )
    usuarioCancelamento: Mapped[UsuarioModel | None] = relationship(
        foreign_keys=[usuarioCancelamentoId]
    )
    # Itens fazem parte do pedido, mas nunca são apagados em cascata (histórico).
    itens: Mapped[list[PedidoItemModel]] = relationship(
        back_populates="pedido",
        passive_deletes="all",
        order_by="PedidoItemModel.id",
    )


# ---------------------------------------------------------------------------
# 9. Itens de pedido
# ---------------------------------------------------------------------------


class PedidoItemModel(Base):
    __tablename__ = "itens_pedido"
    __table_args__ = (
        CheckConstraint("quantidade >= 1 AND quantidade <= 10000", name="quantidade"),
        CheckConstraint("preco_unitario_registrado >= 0.01", name="preco_unitario_registrado"),
        CheckConstraint("subtotal >= 0", name="subtotal"),
    )

    # Chave substituta interna (não exposta): o contrato não proíbe o mesmo produto
    # em mais de uma linha do pedido, então não se impõe unicidade (pedido, produto).
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedidoId: Mapped[int] = mapped_column(
        "pedido_id", Integer, ForeignKey("pedidos.id", ondelete="RESTRICT"), index=True
    )
    produtoId: Mapped[int] = mapped_column(
        "produto_id", Integer, ForeignKey("produtos.id", ondelete="RESTRICT"), index=True
    )
    # Snapshot comercial: permanece correto mesmo se o produto for alterado depois.
    nomeProduto: Mapped[str] = mapped_column("nome_produto", String(100))
    quantidade: Mapped[int] = mapped_column(Integer)
    precoUnitarioRegistrado: Mapped[Decimal] = mapped_column(
        "preco_unitario_registrado", _dinheiro()
    )
    subtotal: Mapped[Decimal] = mapped_column(_total())

    pedido: Mapped[PedidoModel] = relationship(back_populates="itens")
    produto: Mapped[ProdutoModel] = relationship(back_populates="itensPedido")