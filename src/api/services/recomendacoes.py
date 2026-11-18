"""Services de recomendação de produção e de reposição (Fase 5 — P5-09, P5-10, P5-11).

Ambas são calculadas **sob demanda** e **não persistem histórico** (SPEC §6.6): nada é
gravado no banco, apenas lido. A indisponibilidade do solver vira `503` com `ApiError`.

- **Produção** maximiza o lucro estimado (preço de venda menos custo dos ingredientes),
  em quantidades inteiras, respeitando o **estoque válido** — lote vencido não entra.
- **Reposição** projeta o consumo do período informado a partir do histórico de saídas,
  calcula o que falta e escolhe o que comprar dentro do orçamento.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..exceptions import DependenciaIndisponivelError
from ..integrations.optimizer import (
    ItemProducao,
    ItemReposicao,
    RestricaoIngrediente,
    SolverIndisponivelError,
    resolver_producao,
    resolver_reposicao,
)
from ..models import (
    ComposicaoProdutoModel,
    IngredienteModel,
    MovimentacaoEstoqueModel,
    ProdutoModel,
    agora,
    hoje,
)
from ..schemas import (
    CreateReposicaoDTO,
    ProducaoRecomendacao,
    ProducaoRecomendacaoItem,
    ReposicaoRecomendacao,
    ReposicaoRecomendacaoItem,
)
from .estoque import TIPO_SAIDA, inicio_do_dia

CENTAVOS = Decimal("0.01")
MILESIMOS = Decimal("0.001")

CRITERIO_LUCRO = "LUCRO_ESTIMADO"


def _reais(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _quantidade(valor: Decimal) -> Decimal:
    return valor.quantize(MILESIMOS, rounding=ROUND_HALF_UP)


def _saldos_validos(db: Session) -> dict[int, Decimal]:
    """Saldo válido (não vencido) por ingrediente, em uma única consulta."""
    m = MovimentacaoEstoqueModel
    data_ref = hoje()
    stmt = (
        select(m.ingredienteId, func.coalesce(func.sum(m.quantidadeRestante), 0))
        .where(
            m.tipo == "ENTRADA",
            m.quantidadeRestante > 0,
            (m.dataValidade.is_(None)) | (m.dataValidade >= data_ref),
        )
        .group_by(m.ingredienteId)
    )
    return {int(ing): Decimal(str(saldo)) for ing, saldo in db.execute(stmt).all()}


def recomendar_producao(db: Session) -> ProducaoRecomendacao:
    """Quantidades ótimas de produção para o estoque válido atual.

    Só entram produtos **ativos** e com composição. O lucro unitário é
    `precoVenda − Σ (quantidadeUtilizada × custoUnitario)`; produtos com lucro unitário
    não positivo são descartados, pois produzi-los nunca melhora o objetivo.
    """
    produtos = list(
        db.scalars(
            select(ProdutoModel)
            .where(ProdutoModel.ativo.is_(True))
            .options(
                selectinload(ProdutoModel.composicao).joinedload(ComposicaoProdutoModel.ingrediente)
            )
            .order_by(ProdutoModel.id)
        ).unique()
    )
    saldos = _saldos_validos(db)

    itens: list[ItemProducao] = []
    lucro_por_produto: dict[int, Decimal] = {}
    nomes: dict[int, str] = {}

    for produto in produtos:
        if not produto.composicao:
            continue
        custo = sum(
            (linha.quantidadeUtilizada * linha.ingrediente.custoUnitario
             for linha in produto.composicao),
            Decimal(0),
        )
        lucro = _reais(produto.precoVenda - custo)
        if lucro <= 0:
            continue
        itens.append(
            ItemProducao(
                produto_id=produto.id,
                nome=produto.nome,
                lucro_unitario=lucro,
                consumo={
                    linha.ingredienteId: linha.quantidadeUtilizada for linha in produto.composicao
                },
            )
        )
        lucro_por_produto[produto.id] = lucro
        nomes[produto.id] = produto.nome

    # A restrição precisa existir para **todo** ingrediente consumido pelos candidatos,
    # inclusive os de saldo zero: sem a linha correspondente, o produto ficaria sem limite
    # e o solver devolveria o teto de unidades. `_saldos_validos` só lista quem tem saldo.
    ingredientes_usados = {
        ingrediente_id for item in itens for ingrediente_id in item.consumo
    }
    restricoes = [
        RestricaoIngrediente(
            ingrediente_id=ingrediente_id, disponivel=saldos.get(ingrediente_id, Decimal(0))
        )
        for ingrediente_id in sorted(ingredientes_usados | set(saldos))
    ]

    try:
        solucao = resolver_producao(itens, restricoes)
    except SolverIndisponivelError as exc:
        raise DependenciaIndisponivelError(
            "Serviço de otimização temporariamente indisponível."
        ) from exc

    linhas = [
        ProducaoRecomendacaoItem(
            produtoId=produto_id,
            nomeProduto=nomes[produto_id],
            quantidadeRecomendada=quantidade,
            lucroEstimadoUnitario=lucro_por_produto[produto_id],
            lucroEstimadoTotal=_reais(lucro_por_produto[produto_id] * quantidade),
        )
        for produto_id, quantidade in sorted(solucao.items())
    ]

    return ProducaoRecomendacao(
        calculadoEm=agora(),
        criterioOtimizacao=CRITERIO_LUCRO,
        lucroTotalEstimado=_reais(sum((linha.lucroEstimadoTotal for linha in linhas), Decimal(0))),
        itens=linhas,
        observacao=(
            f"Cálculo sob demanda sobre {len(itens)} produto(s) ativo(s) com composição e "
            f"o estoque válido de {len(restricoes)} ingrediente(s) na data de hoje. "
            "Lotes vencidos não foram considerados; o resultado não é persistido."
        ),
    )


def recomendar_reposicao(db: Session, dto: CreateReposicaoDTO) -> ReposicaoRecomendacao:
    """Sugere compras para cobrir o consumo projetado do período, dentro do orçamento.

    Consumo projetado = média diária de saídas nos últimos `periodoDias` dias × o próprio
    `periodoDias`. A necessidade de cada ingrediente é
    `max(consumo projetado + quantidadeMinima − saldo válido, 0)`, de modo que o estoque
    termine o período acima do mínimo configurado. A escolha dentro do orçamento é um
    problema de mochila 0/1 resolvido pelo solver.
    """
    saldos = _saldos_validos(db)
    ingredientes = list(db.scalars(select(IngredienteModel).order_by(IngredienteModel.id)).all())

    desde = inicio_do_dia(hoje() - timedelta(days=dto.periodoDias))
    m = MovimentacaoEstoqueModel
    consumo_historico = {
        int(ingrediente_id): Decimal(str(total))
        for ingrediente_id, total in db.execute(
            select(m.ingredienteId, func.coalesce(func.sum(m.quantidade), 0))
            .where(m.tipo == TIPO_SAIDA, m.dataMovimentacao >= desde)
            .group_by(m.ingredienteId)
        ).all()
    }

    candidatos: list[ItemReposicao] = []
    dados: dict[int, tuple[IngredienteModel, Decimal, Decimal]] = {}

    for ingrediente in ingredientes:
        saldo = saldos.get(ingrediente.id, Decimal(0))
        # O histórico já cobre exatamente `periodoDias`; a projeção para o próximo
        # período de mesma duração é o próprio consumo observado.
        projecao = consumo_historico.get(ingrediente.id, Decimal(0))
        necessidade = projecao + ingrediente.quantidadeMinima - saldo
        if necessidade <= 0:
            continue
        necessidade = _quantidade(necessidade)
        custo = _reais(necessidade * ingrediente.custoUnitario)
        prioridade = _quantidade(max(ingrediente.quantidadeMinima - saldo, Decimal(0))) + necessidade
        candidatos.append(
            ItemReposicao(
                ingrediente_id=ingrediente.id,
                nome=ingrediente.nome,
                quantidade_necessaria=necessidade,
                custo_estimado=custo,
                prioridade=prioridade,
            )
        )
        dados[ingrediente.id] = (ingrediente, necessidade, custo)

    try:
        escolhidos = resolver_reposicao(candidatos, dto.orcamento)
    except SolverIndisponivelError as exc:
        raise DependenciaIndisponivelError(
            "Serviço de otimização temporariamente indisponível."
        ) from exc

    linhas = [
        ReposicaoRecomendacaoItem(
            ingredienteId=ingrediente_id,
            nomeIngrediente=dados[ingrediente_id][0].nome,
            quantidadeRecomendada=dados[ingrediente_id][1],
            unidadeMedida=dados[ingrediente_id][0].unidadeMedida,
            custoEstimado=dados[ingrediente_id][2],
        )
        for ingrediente_id in sorted(escolhidos)
    ]

    return ReposicaoRecomendacao(
        calculadoEm=agora(),
        periodoDias=dto.periodoDias,
        orcamento=dto.orcamento,
        custoTotalEstimado=_reais(sum((linha.custoEstimado for linha in linhas), Decimal(0))),
        itens=linhas,
    )
