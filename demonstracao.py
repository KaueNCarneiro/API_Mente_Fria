"""Roteiro de demonstração da Mente Fria API.

Popula um cenário realista **pelos endpoints do contrato** e narra cada passo: bootstrap
do administrador, cadastro de funcionário, catálogo, entradas de estoque com validades
diferentes, pedido com baixa em FEFO, cancelamento, alertas, recomendação por
Programação Linear Inteira, dashboard e exportação CSV.

Não é seed: nada é inserido no banco por fora da API, e a política de seed do projeto
continua vazia (PLAN.md, decisão 5). É um cliente HTTP como qualquer outro — o mesmo que
uma coleção do Postman faria, só que reproduzível e versionado.

Uso, com a API no ar e um banco **vazio**:

    python demonstracao.py

Contra outro endereço (exige confirmação explícita, para não popular um ambiente por
engano):

    python demonstracao.py --url https://exemplo.com --confirmar

Depende apenas da biblioteca padrão.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from typing import Any

URL_PADRAO = "http://127.0.0.1:8000"
HOSTS_LOCAIS = ("127.0.0.1", "localhost", "[::1]", "0.0.0.0")

ADMIN = {"nome": "Marina Souza", "email": "marina@mentefria.com", "senha": "SenhaForte#2026"}
FUNCIONARIO = {"nome": "Caio Lima", "email": "caio@mentefria.com", "senha": "SenhaForte#2026"}

HOJE = date.today()

# O console do Windows abre em cp1252, que não tem "─", "→" nem "✓". Tenta mudar a saída
# para UTF-8; se não der, cai para equivalentes ASCII em vez de estourar no meio da
# demonstração.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    _UNICODE = True
except (AttributeError, OSError, ValueError):  # pragma: no cover - depende do terminal
    _UNICODE = False

TRACO = "─" if _UNICODE else "-"
SETA = "→" if _UNICODE else "->"
CERTO = "✓" if _UNICODE else "ok"
ATENCAO = "!" if _UNICODE else "!!"

# Cores só quando o terminal é um TTY (num arquivo de log, só atrapalhariam).
_COR = sys.stdout.isatty()
VERDE = "\033[32m" if _COR else ""
AMARELO = "\033[33m" if _COR else ""
CINZA = "\033[90m" if _COR else ""
NEGRITO = "\033[1m" if _COR else ""
FIM = "\033[0m" if _COR else ""

_passo = 0


class DemonstracaoError(RuntimeError):
    """Interrompe o roteiro com uma mensagem útil, sem traceback na tela."""


def titulo(texto: str) -> None:
    print(f"\n{NEGRITO}{texto}{FIM}")
    print(CINZA + TRACO * len(texto) + FIM)


def nota(texto: str) -> None:
    print(f"  {CINZA}{texto}{FIM}")


def chamar(
    metodo: str,
    caminho: str,
    *,
    base: str,
    token: str | None = None,
    corpo: dict[str, Any] | None = None,
    esperado: int | tuple[int, ...] = (200, 201, 204),
    resumo: str = "",
) -> Any:
    """Faz a requisição, narra o que aconteceu e devolve o corpo decodificado."""
    global _passo
    _passo += 1

    url = base.rstrip("/") + caminho
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    requisicao = urllib.request.Request(url, data=dados, method=metodo)
    requisicao.add_header("Accept", "application/json")
    if dados is not None:
        requisicao.add_header("Content-Type", "application/json")
    if token:
        requisicao.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(requisicao, timeout=30) as resposta:
            status = resposta.status
            bruto = resposta.read()
            tipo = resposta.headers.get("Content-Type", "")
            cabecalhos = dict(resposta.headers)
    except urllib.error.HTTPError as erro:
        status = erro.code
        bruto = erro.read()
        tipo = erro.headers.get("Content-Type", "")
        cabecalhos = dict(erro.headers)
    except urllib.error.URLError as erro:
        raise DemonstracaoError(
            f"Não foi possível falar com a API em {base}. Ela está no ar?\n"
            f"  Suba com: uvicorn --factory src.api.main:create_app\n"
            f"  Detalhe: {erro.reason}"
        ) from None

    esperados = (esperado,) if isinstance(esperado, int) else esperado
    marca = f"{VERDE}{CERTO}{FIM}" if status in esperados else f"{AMARELO}{ATENCAO}{FIM}"
    print(f"  {marca} {_passo:>2}. {metodo:<6} {caminho:<46} {SETA} {status} {resumo}")

    if status not in esperados:
        corpo_erro = bruto.decode("utf-8", errors="replace")[:600]
        raise DemonstracaoError(
            f"A API respondeu {status} onde o roteiro esperava {esperados}.\n"
            f"  Resposta: {corpo_erro}"
        )

    if status == 204 or not bruto:
        return None
    if "application/json" in tipo:
        return json.loads(bruto)
    return {"_texto": bruto.decode("utf-8"), "_cabecalhos": cabecalhos}


def dinheiro(valor: Any) -> str:
    return f"R$ {float(valor):.2f}".replace(".", ",")


def executar(base: str) -> int:
    print(f"{NEGRITO}Demonstração da Mente Fria API{FIM}  {CINZA}({base}){FIM}")

    # 1 — saúde -------------------------------------------------------------------------
    titulo("1. A API está no ar?")
    saude = chamar("GET", "/api/v1/saude", base=base, esperado=200, resumo="(público)")
    nota(f"status={saude['status']} banco={saude['banco']}")

    # 2 — bootstrap e login ---------------------------------------------------------------
    titulo("2. Primeiro administrador e autenticação")
    nota("O banco nasce vazio: não há usuário algum até o bootstrap.")
    try:
        admin = chamar(
            "POST",
            "/api/v1/auth/administrador",
            base=base,
            corpo=ADMIN,
            esperado=201,
            resumo="(público, uma única vez)",
        )
    except DemonstracaoError as erro:
        # Tropeço mais provável numa apresentação: rodar o roteiro duas vezes.
        if "409" in str(erro):
            raise DemonstracaoError(
                "já existe um administrador neste banco — o roteiro precisa de um banco vazio.\n"
                "  Pare a API, apague mente_fria.db e suba de novo:\n"
                "    rm mente_fria.db   (Windows: del mente_fria.db)\n"
                "    uvicorn --factory src.api.main:create_app"
            ) from None
        raise
    nota(f"criado id={admin['id']} perfil={admin['perfil']} — a resposta não traz senha nem hash")

    chamar(
        "POST",
        "/api/v1/auth/administrador",
        base=base,
        corpo={"nome": "Outro", "email": "outro@mentefria.com", "senha": "SenhaForte#2026"},
        esperado=409,
        resumo=f"segunda tentativa {SETA} conflito",
    )

    autenticacao = chamar(
        "POST",
        "/api/v1/auth/login",
        base=base,
        corpo={"email": ADMIN["email"], "senha": ADMIN["senha"]},
        esperado=200,
    )
    token_admin = autenticacao["accessToken"]
    nota(f"token emitido, expira em {autenticacao['expiresInSeconds']}s")

    funcionario = chamar(
        "POST",
        "/api/v1/usuarios",
        base=base,
        token=token_admin,
        corpo=FUNCIONARIO,
        esperado=201,
        resumo="perfil definido pelo servidor",
    )
    nota(f"perfil atribuído: {funcionario['perfil']} — o cliente não escolhe")
    token_funcionario = chamar(
        "POST",
        "/api/v1/auth/login",
        base=base,
        corpo={"email": FUNCIONARIO["email"], "senha": FUNCIONARIO["senha"]},
        esperado=200,
    )["accessToken"]

    # 3 — autorização ----------------------------------------------------------------------
    titulo("3. Autorização conforme o contrato")
    chamar("GET", "/api/v1/usuarios", base=base, esperado=401, resumo="sem token")
    chamar(
        "GET",
        "/api/v1/usuarios",
        base=base,
        token=token_funcionario,
        esperado=403,
        resumo="FUNCIONARIO em rota de ADMINISTRADOR",
    )
    chamar(
        "GET",
        "/api/v1/clientes",
        base=base,
        token=token_funcionario,
        esperado=200,
        resumo="clientes: liberado aos dois perfis",
    )

    # 4 — catálogo ---------------------------------------------------------------------------
    titulo("4. Catálogo: unidades e ingredientes")
    for unidade, porcao in (("g", 100), ("ml", 50)):
        chamar(
            "POST",
            "/api/v1/unidades-medida",
            base=base,
            token=token_admin,
            corpo={"unidadeMedida": unidade, "porcaoPadrao": porcao},
            esperado=201,
        )

    acai = chamar(
        "POST",
        "/api/v1/ingredientes",
        base=base,
        token=token_admin,
        corpo={
            "nome": "Açaí",
            "unidadeMedida": "g",
            "custoUnitario": 0.05,
            "porcaoPadrao": 100,
            "quantidadeMinima": 500,
        },
        esperado=201,
    )
    nota(
        f"estoque inicial = {acai['quantidadeEstoque']} e precisaReposicao = "
        f"{acai['precisaReposicao']} — o ingrediente nasce zerado"
    )
    leite = chamar(
        "POST",
        "/api/v1/ingredientes",
        base=base,
        token=token_admin,
        corpo={
            "nome": "Leite condensado",
            "unidadeMedida": "ml",
            "custoUnitario": 0.02,
            "porcaoPadrao": 50,
            "quantidadeMinima": 200,
        },
        esperado=201,
    )
    # Fica de propósito sem entrada de estoque: é ele que alimenta os alertas de
    # reposição e a recomendação de compra, mais adiante.
    chamar(
        "POST",
        "/api/v1/ingredientes",
        base=base,
        token=token_admin,
        corpo={
            "nome": "Granola",
            "unidadeMedida": "g",
            "custoUnitario": 0.03,
            "porcaoPadrao": 100,
            "quantidadeMinima": 1000,
        },
        esperado=201,
        resumo="sem estoque, de propósito",
    )

    # 5 — estoque ------------------------------------------------------------------------------
    titulo("5. Entradas de estoque com validades diferentes")
    lote_longe = chamar(
        "POST",
        "/api/v1/movimentacoes-estoque",
        base=base,
        token=token_admin,
        corpo={
            "ingredienteId": acai["id"],
            "tipo": "ENTRADA",
            "quantidade": 2000,
            "dataValidade": (HOJE + timedelta(days=60)).isoformat(),
            "observacao": "Lote novo",
        },
        esperado=201,
    )
    lote_perto = chamar(
        "POST",
        "/api/v1/movimentacoes-estoque",
        base=base,
        token=token_admin,
        corpo={
            "ingredienteId": acai["id"],
            "tipo": "ENTRADA",
            "quantidade": 800,
            "dataValidade": (HOJE + timedelta(days=3)).isoformat(),
            "observacao": "Lote que vence antes",
        },
        esperado=201,
    )
    lote_vencido = chamar(
        "POST",
        "/api/v1/movimentacoes-estoque",
        base=base,
        token=token_admin,
        corpo={
            "ingredienteId": acai["id"],
            "tipo": "ENTRADA",
            "quantidade": 300,
            "dataValidade": (HOJE - timedelta(days=2)).isoformat(),
            "observacao": "Lote já vencido",
        },
        esperado=201,
    )
    chamar(
        "POST",
        "/api/v1/movimentacoes-estoque",
        base=base,
        token=token_admin,
        corpo={"ingredienteId": leite["id"], "tipo": "ENTRADA", "quantidade": 1000},
        esperado=201,
        resumo="lote sem validade",
    )
    nota("três lotes de açaí: vence em 60 dias, em 3 dias e um já vencido")

    # 6 — produto ---------------------------------------------------------------------------------
    titulo("6. Produto e composição")
    produto = chamar(
        "POST",
        "/api/v1/produtos",
        base=base,
        token=token_admin,
        corpo={
            "nome": "Açaí 300ml",
            "precoVenda": 18.00,
            "ativo": True,
            "composicao": [
                {"ingredienteId": acai["id"], "quantidadeUtilizada": 250},
                {"ingredienteId": leite["id"], "quantidadeUtilizada": 30},
            ],
        },
        esperado=201,
    )
    nota(
        "composição: "
        + ", ".join(
            f"{item['quantidadeUtilizada']} {item['unidadeMedida']} de {item['nomeIngrediente']}"
            for item in produto["composicao"]
        )
    )

    # 7 — pedido e FEFO ------------------------------------------------------------------------------
    titulo("7. Pedido: preço capturado e baixa em FEFO")
    cliente = chamar(
        "POST",
        "/api/v1/clientes",
        base=base,
        token=token_funcionario,
        corpo={"nome": "Ana Ribeiro", "contato": "11999990000", "endereco": "Rua das Flores, 120"},
        esperado=201,
    )
    antes = chamar(
        "GET", f"/api/v1/ingredientes/{acai['id']}", base=base, token=token_admin, esperado=200
    )
    pedido = chamar(
        "POST",
        "/api/v1/pedidos",
        base=base,
        token=token_funcionario,
        corpo={"clienteId": cliente["id"], "itens": [{"produtoId": produto["id"], "quantidade": 2}]},
        esperado=201,
    )
    depois = chamar(
        "GET", f"/api/v1/ingredientes/{acai['id']}", base=base, token=token_admin, esperado=200
    )
    item = pedido["itens"][0]
    nota(
        f"preço registrado {dinheiro(item['precoUnitarioRegistrado'])} × {item['quantidade']} = "
        f"{dinheiro(item['subtotal'])} | total {dinheiro(pedido['valorTotal'])}"
    )
    nota(
        f"estoque de açaí: {antes['quantidadeEstoque']} {SETA} {depois['quantidadeEstoque']} "
        f"(2 × 250 g baixados)"
    )

    movimentacoes = chamar(
        "GET",
        f"/api/v1/movimentacoes-estoque?ingredienteId={acai['id']}&size=100",
        base=base,
        token=token_admin,
        esperado=200,
        resumo="conferindo os lotes",
    )
    lotes = {m["id"]: m for m in movimentacoes["data"] if m["tipo"] == "ENTRADA"}
    nota(
        f"FEFO — lote de 3 dias: {lotes[lote_perto['id']]['quantidadeRestante']} restante | "
        f"lote de 60 dias: {lotes[lote_longe['id']]['quantidadeRestante']} | "
        f"lote vencido: {lotes[lote_vencido['id']]['quantidadeRestante']} (intocado)"
    )

    # 8 — preço histórico ------------------------------------------------------------------------------
    titulo("8. Alterar o produto não reescreve o passado")
    chamar(
        "PUT",
        f"/api/v1/produtos/{produto['id']}",
        base=base,
        token=token_admin,
        corpo={"nome": "Açaí 300ml", "precoVenda": 24.00, "ativo": True},
        esperado=200,
        resumo="preço sobe para 24,00",
    )
    conferido = chamar(
        "GET", f"/api/v1/pedidos/{pedido['id']}", base=base, token=token_admin, esperado=200
    )
    nota(
        f"o pedido continua com {dinheiro(conferido['itens'][0]['precoUnitarioRegistrado'])} "
        f"e total {dinheiro(conferido['valorTotal'])}"
    )

    # 9 — cancelamento ------------------------------------------------------------------------------
    titulo("9. Cancelamento não devolve estoque")
    segundo = chamar(
        "POST",
        "/api/v1/pedidos",
        base=base,
        token=token_funcionario,
        corpo={"itens": [{"produtoId": produto["id"], "quantidade": 1}]},
        esperado=201,
        resumo="pedido sem cliente",
    )
    saldo_antes = chamar(
        "GET", f"/api/v1/ingredientes/{acai['id']}", base=base, token=token_admin, esperado=200
    )["quantidadeEstoque"]
    cancelado = chamar(
        "POST",
        f"/api/v1/pedidos/{segundo['id']}/cancelamento",
        base=base,
        token=token_admin,
        corpo={"observacao": "Cliente desistiu na hora."},
        esperado=200,
    )
    saldo_depois = chamar(
        "GET", f"/api/v1/ingredientes/{acai['id']}", base=base, token=token_admin, esperado=200
    )["quantidadeEstoque"]
    nota(
        f"status={cancelado['status']} por usuário {cancelado['usuarioCancelamentoId']} | "
        f"estoque {saldo_antes} {SETA} {saldo_depois} (inalterado, como manda o contrato)"
    )
    chamar(
        "POST",
        f"/api/v1/pedidos/{segundo['id']}/cancelamento",
        base=base,
        token=token_admin,
        corpo={},
        esperado=409,
        resumo=f"cancelar de novo {SETA} conflito",
    )

    # 10 — alertas ------------------------------------------------------------------------------
    titulo("10. Alertas de validade e reposição")
    validade = chamar(
        "GET", "/api/v1/alertas/validade?diasAntecedencia=7", base=base, token=token_funcionario, esperado=200
    )
    if not validade["itens"]:
        nota("nenhum lote na janela de vencimento")
    for alerta in validade["itens"]:
        nota(
            f"{alerta['situacao']:<19} {alerta['nomeIngrediente']} — "
            f"{alerta['quantidadeRestante']} unid., vence {alerta['dataValidade']} "
            f"({alerta['diasAteVencimento']} dias)"
        )
    reposicao = chamar(
        "GET", "/api/v1/alertas/reposicao", base=base, token=token_funcionario, esperado=200
    )
    if not reposicao["itens"]:
        nota("nenhum ingrediente abaixo do mínimo no momento")
    for alerta in reposicao["itens"]:
        nota(
            f"repor {alerta['nomeIngrediente']}: saldo válido {alerta['quantidadeEstoqueValido']} "
            f"< mínimo {alerta['quantidadeMinima']} (déficit {alerta['deficit']})"
        )

    # 11 — descarte do vencido ------------------------------------------------------------------------------
    titulo("11. Descarte do lote vencido")
    nota("É a única saída que alcança lote vencido; as demais só consomem lote válido.")
    chamar(
        "POST",
        "/api/v1/movimentacoes-estoque",
        base=base,
        token=token_admin,
        corpo={
            "ingredienteId": acai["id"],
            "tipo": "SAIDA",
            "quantidade": 300,
            "motivo": "DESCARTE_VENCIDO",
            "observacao": "Descarte do lote vencido.",
        },
        esperado=201,
    )
    restante = chamar(
        "GET",
        f"/api/v1/movimentacoes-estoque?ingredienteId={acai['id']}&size=100",
        base=base,
        token=token_admin,
        esperado=200,
    )
    vencido = next(m for m in restante["data"] if m["id"] == lote_vencido["id"])
    nota(f"lote vencido zerado: quantidadeRestante = {vencido['quantidadeRestante']}")

    # 12 — recomendação ------------------------------------------------------------------------------
    titulo("12. Recomendação de produção (Programação Linear Inteira)")
    producao = chamar(
        "POST", "/api/v1/recomendacoes/producao", base=base, token=token_admin, esperado=200
    )
    nota(f"critério: {producao['criterioOtimizacao']}")
    if not producao["itens"]:
        nota("nenhuma produção recomendada com o estoque válido atual")
    for linha in producao["itens"]:
        nota(
            f"produzir {linha['quantidadeRecomendada']}× {linha['nomeProduto']} — lucro unitário "
            f"{dinheiro(linha['lucroEstimadoUnitario'])}, total {dinheiro(linha['lucroEstimadoTotal'])}"
        )
    nota(f"lucro total estimado: {dinheiro(producao['lucroTotalEstimado'])}")

    compras = chamar(
        "POST",
        "/api/v1/recomendacoes/reposicao",
        base=base,
        token=token_admin,
        corpo={"periodoDias": 30, "orcamento": 100.00},
        esperado=200,
    )
    if not compras["itens"]:
        nota("nada a comprar: o estoque cobre o período dentro do orçamento")
    for linha in compras["itens"]:
        nota(
            f"comprar {linha['quantidadeRecomendada']} {linha['unidadeMedida']} de "
            f"{linha['nomeIngrediente']} — {dinheiro(linha['custoEstimado'])}"
        )
    nota(f"custo total dentro do orçamento de R$ 100,00: {dinheiro(compras['custoTotalEstimado'])}")

    # 13 — dashboard e CSV ------------------------------------------------------------------------------
    titulo("13. Dashboard e exportação CSV")
    periodo = f"dataInicio={(HOJE - timedelta(days=1)).isoformat()}&dataFim={(HOJE + timedelta(days=1)).isoformat()}"
    painel = chamar(
        "GET", f"/api/v1/dashboard?{periodo}", base=base, token=token_admin, esperado=200
    )
    nota(
        f"pedidos ativos: {painel['quantidadePedidos']} | faturamento "
        f"{dinheiro(painel['faturamentoTotal'])} | ticket médio {dinheiro(painel['ticketMedio'])}"
    )
    nota("o pedido cancelado não entra nestes números")
    for posicao in painel["produtosMaisVendidos"]:
        nota(f"mais vendido: {posicao['nomeProduto']} ({posicao['quantidadeVendida']} unid.)")

    csv = chamar(
        "GET", f"/api/v1/dashboard/exportacao?{periodo}", base=base, token=token_admin, esperado=200
    )
    linhas = csv["_texto"].strip().splitlines()
    tipo_csv = next(
        (v for k, v in csv["_cabecalhos"].items() if k.lower() == "content-type"), "?"
    )
    nota(f"CSV com {len(linhas)} linhas, Content-Type: {tipo_csv}")
    for linha in linhas[:4]:
        nota(f"  {linha}")

    # 14 — erros ------------------------------------------------------------------------------
    titulo("14. Erros no envelope do contrato")
    for metodo, caminho, corpo, status, descricao in (
        ("GET", "/api/v1/produtos/9999", None, 404, "produto inexistente"),
        ("GET", "/api/v1/usuarios?size=500", None, 400, "parâmetro fora do limite"),
        (
            "POST",
            "/api/v1/clientes",
            {"nome": "A", "contato": "1", "endereco": "x"},
            422,
            "campos inválidos",
        ),
    ):
        erro = chamar(
            metodo,
            caminho,
            base=base,
            token=token_admin,
            corpo=corpo,
            esperado=status,
            resumo=descricao,
        )
        detalhes = ", ".join(d["campo"] for d in erro["detalhes"]) or "—"
        nota(f"codigo={erro['codigo']} campos={detalhes}")

    print(f"\n{VERDE}{NEGRITO}Roteiro concluído.{FIM} {_passo} chamadas, todas com o status esperado.")
    print(f"{CINZA}Abra {base}/docs para explorar o restante do contrato.{FIM}")
    return 0


def main() -> int:
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument("--url", default=URL_PADRAO, help=f"endereço da API (padrão: {URL_PADRAO})")
    analisador.add_argument(
        "--confirmar",
        action="store_true",
        help="exigido para rodar contra um endereço que não seja local",
    )
    argumentos = analisador.parse_args()

    local = any(host in argumentos.url for host in HOSTS_LOCAIS)
    if not local and not argumentos.confirmar:
        print(
            f"{AMARELO}Recusado:{FIM} {argumentos.url} não é um endereço local e o roteiro "
            "escreve dados (usuários, estoque, pedidos).\n"
            "Se é mesmo onde você quer demonstrar, repita com --confirmar.",
            file=sys.stderr,
        )
        return 2

    try:
        return executar(argumentos.url)
    except DemonstracaoError as erro:
        print(f"\n{AMARELO}Roteiro interrompido.{FIM} {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
