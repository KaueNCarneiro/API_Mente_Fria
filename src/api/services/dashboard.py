"""Service do dashboard e da exportação CSV (Fase 5 — P5-15, P5-16).

Regras do SPEC §6.6: o período informado é respeitado nas duas pontas (inclusivo) e
**somente pedidos `ATIVO`** entram nos indicadores financeiros e no ranking — pedidos
cancelados continuam consultáveis, mas não contam aqui.

A exportação aplica exatamente as mesmas regras e devolve **CSV UTF-8**, não JSON.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import IngredienteModel, PedidoItemModel, PedidoModel
from ..schemas import Dashboard, ProdutoMaisVendido
from .alertas import DIAS_ANTECEDENCIA_PADRAO, listar_validade
from .comum import validar_intervalo
from .estoque import inicio_do_dia, inicio_do_dia_seguinte
from .pedidos import STATUS_ATIVO

CENTAVOS = Decimal("0.01")
LIMITE_RANKING = 5

# Cabeçalhos do CSV exportado (seção, chave, valor): formato tabular simples, legível em
# planilha, cobrindo os mesmos indicadores do JSON.
CABECALHO_CSV = ("secao", "chave", "valor")


def _reais(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def consultar(db: Session, *, data_inicio: date, data_fim: date) -> Dashboard:
    """Indicadores do período, considerando apenas pedidos ativos."""
    validar_intervalo(data_inicio, data_fim)
    inicio = inicio_do_dia(data_inicio)
    fim = inicio_do_dia_seguinte(data_fim)

    periodo = (
        PedidoModel.status == STATUS_ATIVO,
        PedidoModel.dataPedido >= inicio,
        PedidoModel.dataPedido < fim,
    )

    quantidade, faturamento = db.execute(
        select(
            func.count(PedidoModel.id),
            func.coalesce(func.sum(PedidoModel.valorTotal), 0),
        ).where(*periodo)
    ).one()
    quantidade = int(quantidade or 0)
    faturamento = _reais(Decimal(str(faturamento or 0)))
    ticket = _reais(faturamento / quantidade) if quantidade else Decimal("0.00")

    ranking = [
        ProdutoMaisVendido(
            produtoId=int(produto_id), nomeProduto=nome, quantidadeVendida=int(total)
        )
        for produto_id, nome, total in db.execute(
            select(
                PedidoItemModel.produtoId,
                PedidoItemModel.nomeProduto,
                func.sum(PedidoItemModel.quantidade).label("total"),
            )
            .join(PedidoModel, PedidoModel.id == PedidoItemModel.pedidoId)
            .where(*periodo)
            .group_by(PedidoItemModel.produtoId, PedidoItemModel.nomeProduto)
            .order_by(func.sum(PedidoItemModel.quantidade).desc(), PedidoItemModel.produtoId)
            .limit(LIMITE_RANKING)
        ).all()
    ]

    # Indicadores de estoque refletem o estado ATUAL (não têm recorte por período no
    # contrato): ingredientes abaixo do mínimo e lotes próximos do vencimento.
    em_reposicao = int(
        db.scalar(
            select(func.count())
            .select_from(IngredienteModel)
            .where(IngredienteModel.saldoValido < IngredienteModel.quantidadeMinima)
        )
        or 0
    )
    proximas_vencimento = len(
        listar_validade(
            db, dias_antecedencia=DIAS_ANTECEDENCIA_PADRAO, incluir_vencidos=False
        ).itens
    )

    return Dashboard(
        periodoInicio=data_inicio,
        periodoFim=data_fim,
        quantidadePedidos=quantidade,
        faturamentoTotal=faturamento,
        ticketMedio=ticket,
        produtosMaisVendidos=ranking,
        ingredientesEmReposicao=em_reposicao,
        linhasProximasVencimento=proximas_vencimento,
    )


def exportar_csv(db: Session, *, data_inicio: date, data_fim: date) -> str:
    """Mesmos dados do dashboard em CSV UTF-8 (texto, não JSON).

    Sem BOM: o contrato pede UTF-8, e o BOM mudaria os bytes do arquivo. O separador é a
    vírgula, e os números decimais usam ponto, como no JSON da API.
    """
    painel = consultar(db, data_inicio=data_inicio, data_fim=data_fim)

    buffer = io.StringIO(newline="")
    escritor = csv.writer(buffer, lineterminator="\n")
    escritor.writerow(CABECALHO_CSV)
    escritor.writerow(("periodo", "dataInicio", painel.periodoInicio.isoformat()))
    escritor.writerow(("periodo", "dataFim", painel.periodoFim.isoformat()))
    escritor.writerow(("indicadores", "quantidadePedidos", painel.quantidadePedidos))
    escritor.writerow(("indicadores", "faturamentoTotal", painel.faturamentoTotal))
    escritor.writerow(("indicadores", "ticketMedio", painel.ticketMedio))
    escritor.writerow(("indicadores", "ingredientesEmReposicao", painel.ingredientesEmReposicao))
    escritor.writerow(
        ("indicadores", "linhasProximasVencimento", painel.linhasProximasVencimento)
    )
    for posicao, produto in enumerate(painel.produtosMaisVendidos, start=1):
        escritor.writerow(
            (
                "produtosMaisVendidos",
                f"{posicao}. {produto.nomeProduto} (id {produto.produtoId})",
                produto.quantidadeVendida,
            )
        )
    return buffer.getvalue()


def nome_do_arquivo(data_inicio: date, data_fim: date) -> str:
    """Nome sugerido no cabeçalho `Content-Disposition` da exportação."""
    return f"mente-fria-dashboard-{data_inicio.isoformat()}-a-{data_fim.isoformat()}.csv"
