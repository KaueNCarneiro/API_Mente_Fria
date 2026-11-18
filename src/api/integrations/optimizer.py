"""Integração com o solver de Programação Linear Inteira (Fase 5 — P5-08, P5-11).

Solver aprovado na revisão humana de 2026-11-18 (PLAN.md, decisão 1): **PuLP**, Python
puro, com o CBC distribuído no próprio pacote — não exige solver instalado no sistema.

Este módulo é a **única** fronteira com a biblioteca de otimização: os services falam com
as funções daqui e nunca importam `pulp`. Assim, trocar de solver não toca em regra de
negócio, e a indisponibilidade do solver vira um erro próprio
(`SolverIndisponivelError`), que o service traduz para `503` + `ApiError`.

A importação do `pulp` é **preguiçosa**, dentro de cada função: assim, um ambiente sem a
dependência instalada falha com `503` na operação que a usa, em vez de derrubar a
aplicação inteira na importação.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "ItemProducao",
    "ItemReposicao",
    "RestricaoIngrediente",
    "SolverIndisponivelError",
    "resolver_producao",
    "resolver_reposicao",
]

# Teto por produto: o CBC precisa de variáveis limitadas, e o contrato limita a
# quantidade de um item de pedido a 10.000 unidades — o mesmo teto é adotado aqui.
LIMITE_UNIDADES = 10_000


class SolverIndisponivelError(RuntimeError):
    """O solver não pôde ser carregado ou não concluiu o cálculo.

    O service a converte em `503` com `ApiError`, como manda o contrato das operações de
    recomendação. Nunca vaza detalhe interno para o cliente.
    """


@dataclass(frozen=True, slots=True)
class ItemProducao:
    """Produto candidato à produção, com o lucro unitário já calculado."""

    produto_id: int
    nome: str
    lucro_unitario: Decimal
    # ingrediente_id -> quantidade consumida por unidade produzida
    consumo: dict[int, Decimal]


@dataclass(frozen=True, slots=True)
class RestricaoIngrediente:
    """Estoque válido disponível de um ingrediente."""

    ingrediente_id: int
    disponivel: Decimal


@dataclass(frozen=True, slots=True)
class ItemReposicao:
    """Ingrediente candidato à compra, com necessidade e custo estimados."""

    ingrediente_id: int
    nome: str
    quantidade_necessaria: Decimal
    custo_estimado: Decimal
    # Peso da urgência: quanto o saldo está abaixo do mínimo configurado.
    prioridade: Decimal


def _pulp() -> Any:
    """Importa o PuLP sob demanda; ausência da dependência vira `SolverIndisponivelError`."""
    try:
        import pulp
    except ImportError as exc:  # dependência ausente no ambiente
        logger.warning("solver de otimização indisponível: %s", type(exc).__name__)
        raise SolverIndisponivelError("Solver de otimização indisponível.") from exc
    return pulp


def _resolver(problema: Any, pulp: Any) -> None:
    """Executa o CBC em silêncio e exige solução ótima."""
    try:
        status = problema.solve(pulp.PULP_CBC_CMD(msg=False))
    except Exception as exc:  # falha de execução do binário do solver
        logger.warning("falha ao executar o solver: %s", type(exc).__name__)
        raise SolverIndisponivelError("Solver de otimização indisponível.") from exc
    if pulp.LpStatus[status] != "Optimal":
        logger.warning("solver não encontrou solução ótima: status=%s", pulp.LpStatus[status])
        raise SolverIndisponivelError("Não foi possível concluir a otimização.")


def resolver_producao(
    itens: list[ItemProducao], restricoes: list[RestricaoIngrediente]
) -> dict[int, int]:
    """Maximiza o lucro estimado escolhendo **quantidades inteiras** por produto.

    Modelo::

        max  Σ lucro_p · x_p
        s.a. Σ consumo_pi · x_p ≤ disponível_i   (para cada ingrediente i)
             x_p ∈ ℤ, 0 ≤ x_p ≤ LIMITE_UNIDADES

    Devolve ``{produto_id: quantidade}`` apenas com quantidades maiores que zero. Sem
    produtos candidatos, devolve vazio sem chamar o solver.
    """
    if not itens:
        return {}

    pulp = _pulp()
    problema = pulp.LpProblem("producao_mente_fria", pulp.LpMaximize)

    variaveis = {
        item.produto_id: pulp.LpVariable(
            f"x_{item.produto_id}", lowBound=0, upBound=LIMITE_UNIDADES, cat=pulp.LpInteger
        )
        for item in itens
    }

    problema += pulp.lpSum(
        float(item.lucro_unitario) * variaveis[item.produto_id] for item in itens
    )

    disponivel = {r.ingrediente_id: r.disponivel for r in restricoes}
    for ingrediente_id, quantidade in disponivel.items():
        consumidores = [
            float(item.consumo[ingrediente_id]) * variaveis[item.produto_id]
            for item in itens
            if item.consumo.get(ingrediente_id)
        ]
        if consumidores:
            problema += pulp.lpSum(consumidores) <= float(quantidade), f"estoque_{ingrediente_id}"

    _resolver(problema, pulp)

    resultado: dict[int, int] = {}
    for produto_id, variavel in variaveis.items():
        quantidade = round(variavel.value() or 0)
        if quantidade > 0:
            resultado[produto_id] = quantidade
    return resultado


def resolver_reposicao(itens: list[ItemReposicao], orcamento: Decimal) -> set[int]:
    """Escolhe quais ingredientes repor dentro do orçamento (mochila 0/1 inteira).

    Modelo::

        max  Σ prioridade_i · y_i
        s.a. Σ custo_i · y_i ≤ orçamento
             y_i ∈ {0, 1}

    Cada candidato representa cobrir **integralmente** a necessidade do ingrediente no
    período; devolve os ids escolhidos. Candidatos cujo custo já excede o orçamento são
    descartados antes do solver (não cabem sozinhos).
    """
    viaveis = [item for item in itens if item.custo_estimado <= orcamento]
    if not viaveis:
        return set()

    pulp = _pulp()
    problema = pulp.LpProblem("reposicao_mente_fria", pulp.LpMaximize)

    variaveis = {
        item.ingrediente_id: pulp.LpVariable(f"y_{item.ingrediente_id}", cat=pulp.LpBinary)
        for item in viaveis
    }

    problema += pulp.lpSum(
        float(item.prioridade) * variaveis[item.ingrediente_id] for item in viaveis
    )
    problema += (
        pulp.lpSum(float(item.custo_estimado) * variaveis[item.ingrediente_id] for item in viaveis)
        <= float(orcamento),
        "orcamento",
    )

    _resolver(problema, pulp)

    return {
        ingrediente_id
        for ingrediente_id, variavel in variaveis.items()
        if round(variavel.value() or 0) == 1
    }
