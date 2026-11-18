
"""Verificação prática da Fase 5 (services, routers e integração) — Mente Fria API.

NÃO é a suíte definitiva da Fase 6 (pytest). Compara o OpenAPI **gerado pela aplicação**
com o contrato `Mente Fria API.openapi.json` operação por operação e exercita os fluxos
de negócio ponta a ponta em SQLite em memória. Uso, na raiz do repositório:

    python verify_api.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

# Ambiente de teste ANTES de importar a aplicação (nunca toca o banco de desenvolvimento).
for _k in [k for k in os.environ if k.startswith("MENTE_FRIA_")]:
    del os.environ[_k]
os.environ.update(
    MENTE_FRIA_ENV="test",
    MENTE_FRIA_JWT_SECRET_KEY="chave-apenas-para-verificacao",
    MENTE_FRIA_JWT_ACCESS_TOKEN_EXPIRE_SECONDS="60",
)

from fastapi.testclient import TestClient
from sqlalchemy import event

from src.api import database as db
from src.api.integrations import optimizer
from src.api.main import create_app, rotas_da_api
from src.api.models import hoje

OK = FAIL = 0
CONTRATO = Path("Mente Fria API.openapi.json")
METODOS = ("get", "post", "put", "patch", "delete")

SENHA = "SenhaForte#2026"


def check(nome: str, cond: bool, detalhe: str = "") -> None:
    global OK, FAIL
    if cond:
        OK += 1
    else:
        FAIL += 1
        print(f"  FALHOU: {nome} {detalhe}")


def operacoes(spec: dict) -> dict[str, dict]:
    """`operationId` -> {caminho, metodo, op} de um documento OpenAPI."""
    saida: dict[str, dict] = {}
    for caminho, item in spec["paths"].items():
        for metodo in METODOS:
            op = item.get(metodo)
            if op:
                saida[op["operationId"]] = {"caminho": caminho, "metodo": metodo, "op": op, "item": item}
    return saida


def parametros(spec: dict, dados: dict) -> set[tuple[str, str, bool]]:
    """Conjunto (nome, in, obrigatório) da operação, resolvendo `$ref`."""
    brutos = list(dados["item"].get("parameters", [])) + list(dados["op"].get("parameters", []))
    saida: set[tuple[str, str, bool]] = set()
    for par in brutos:
        if "$ref" in par:
            par = spec["components"]["parameters"][par["$ref"].split("/")[-1]]
        saida.add((par["name"], par["in"], bool(par.get("required", par["in"] == "path"))))
    return saida


def nome_do_schema(conteudo: dict | None) -> str | None:
    if not conteudo:
        return None
    esquema = conteudo.get("schema") or {}
    if "$ref" in esquema:
        return esquema["$ref"].split("/")[-1]
    return esquema.get("type")


def main() -> int:
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))
    app = create_app()
    gerado = app.openapi()

    esperadas = operacoes(contrato)
    obtidas = operacoes(gerado)

    # 1 — inventário de caminhos e operações (P5-66) --------------------------------------
    print("[1] caminhos, operações e operationIds")
    check("26 caminhos registrados", len(gerado["paths"]) == 26, str(len(gerado["paths"])))
    check("44 operações registradas", len(obtidas) == 44, str(len(obtidas)))
    check(
        "mesmos operationIds do contrato",
        set(obtidas) == set(esperadas),
        f"faltando={sorted(set(esperadas) - set(obtidas))} sobrando={sorted(set(obtidas) - set(esperadas))}",
    )
    check(
        "mesmos caminhos do contrato",
        set(gerado["paths"]) == set(contrato["paths"]),
        f"diferença={sorted(set(gerado['paths']) ^ set(contrato['paths']))}",
    )
    rotas_api = [r for r in rotas_da_api(app) if r.operation_id]
    assinaturas = [(r.operation_id, tuple(sorted(r.methods))) for r in rotas_api]
    check("44 rotas registradas na aplicação", len(assinaturas) == 44, str(len(assinaturas)))
    check("nenhuma rota duplicada", len(assinaturas) == len(set(assinaturas)), str(assinaturas))
    check(
        "nenhuma rota fora do contrato (sem /auth/me, /tasks, /projects)",
        not any(
            termo in caminho
            for caminho in gerado["paths"]
            for termo in ("/auth/me", "/tasks", "/projects")
        ),
    )

    # 2 — método, caminho, tag e parâmetros ----------------------------------------------
    print("[2] método, caminho, tags e parâmetros por operação")
    for oid, esperado in esperadas.items():
        obtido = obtidas.get(oid)
        if obtido is None:
            continue
        check(f"{oid}: método e caminho", (obtido["metodo"], obtido["caminho"]) == (esperado["metodo"], esperado["caminho"]),
              f"{obtido['metodo']} {obtido['caminho']}")
        check(f"{oid}: tags", obtido["op"].get("tags") == esperado["op"].get("tags"),
              f"{obtido['op'].get('tags')} != {esperado['op'].get('tags')}")
        p_esperado = parametros(contrato, esperado)
        p_obtido = parametros(gerado, obtido)
        check(f"{oid}: parâmetros (nome, in, obrigatório)", p_obtido == p_esperado,
              f"faltando={sorted(p_esperado - p_obtido)} sobrando={sorted(p_obtido - p_esperado)}")

    # 3 — corpos, status, media types e headers (P5-67) -----------------------------------
    print("[3] request bodies, status, media types e headers")
    for oid, esperado in esperadas.items():
        obtido = obtidas.get(oid)
        if obtido is None:
            continue
        corpo_esperado = nome_do_schema((esperado["op"].get("requestBody") or {}).get("content", {}).get("application/json"))
        corpo_obtido = nome_do_schema((obtido["op"].get("requestBody") or {}).get("content", {}).get("application/json"))
        check(f"{oid}: schema do corpo", corpo_obtido == corpo_esperado, f"{corpo_obtido} != {corpo_esperado}")

        status_esperado = set(esperado["op"]["responses"])
        status_obtido = set(obtido["op"]["responses"])
        check(f"{oid}: status declarados", status_obtido == status_esperado,
              f"faltando={sorted(status_esperado - status_obtido)} sobrando={sorted(status_obtido - status_esperado)}")

        for codigo, resp_esp in esperado["op"]["responses"].items():
            if "$ref" in resp_esp:
                resp_esp = contrato["components"]["responses"][resp_esp["$ref"].split("/")[-1]]
            resp_obt = obtido["op"]["responses"].get(codigo, {})
            mt_esp = set((resp_esp.get("content") or {}).keys())
            mt_obt = set((resp_obt.get("content") or {}).keys())
            check(f"{oid}/{codigo}: media types", mt_obt == mt_esp, f"{mt_obt} != {mt_esp}")
            if codigo == "204":
                check(f"{oid}/204: sem corpo no schema", not mt_obt, str(mt_obt))
            h_esp = set((resp_esp.get("headers") or {}).keys())
            h_obt = set((resp_obt.get("headers") or {}).keys())
            check(f"{oid}/{codigo}: headers", h_obt >= h_esp, f"{h_obt} não cobre {h_esp}")
            if codigo not in ("204",) and mt_esp == {"application/json"}:
                check(f"{oid}/{codigo}: schema da resposta",
                      nome_do_schema(resp_obt["content"]["application/json"]) == nome_do_schema(resp_esp["content"]["application/json"]),
                      f"{nome_do_schema(resp_obt['content']['application/json'])} != {nome_do_schema(resp_esp['content']['application/json'])}")

    # 4 — security (P5-68) ----------------------------------------------------------------
    print("[4] security por operação")
    for oid, esperado in esperadas.items():
        obtido = obtidas.get(oid)
        if obtido is None:
            continue
        publica = esperado["op"].get("security", contrato.get("security")) == []
        sec_obtida = obtido["op"].get("security")
        if publica:
            check(f"{oid}: pública (sem security)", not sec_obtida, str(sec_obtida))
        else:
            check(f"{oid}: exige bearer", bool(sec_obtida) and "HTTPBearer" in json.dumps(sec_obtida),
                  str(sec_obtida))

    # ------------------------------------------------------------------------------------
    # Fluxos funcionais
    # ------------------------------------------------------------------------------------
    engine = db.create_db_engine(db.get_settings())
    db.init_db(engine)
    db.get_engine.cache_clear()
    app.dependency_overrides.clear()

    def get_db_teste():
        sessao = db.SessionLocal(bind=engine)
        try:
            yield sessao
        finally:
            sessao.close()

    app.dependency_overrides[db.get_db] = get_db_teste
    cliente = TestClient(app, raise_server_exceptions=False)

    consultas: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)

    # 5 — saúde, bootstrap, login e RBAC --------------------------------------------------
    print("[5] saúde, autenticação e autorização")
    r = cliente.get("/api/v1/saude")
    check("GET /saude público responde 200", r.status_code == 200, str(r.status_code))
    check("saúde informa banco ok", r.json() == {"status": "ok", "banco": "ok"}, r.text)

    r = cliente.post("/api/v1/auth/administrador",
                     json={"nome": "Dona Maria", "email": "maria@exemplo.com", "senha": SENHA})
    check("bootstrap do administrador -> 201", r.status_code == 201, r.text[:200])
    check("201 traz header Location", r.headers.get("location") == "/api/v1/usuarios/1", str(r.headers.get("location")))
    check("resposta do bootstrap não expõe senha/hash", "senha" not in r.text and "argon2" not in r.text)
    check("perfil do bootstrap é ADMINISTRADOR", r.json()["perfil"] == "ADMINISTRADOR")

    r = cliente.post("/api/v1/auth/administrador",
                     json={"nome": "Outro", "email": "outro@exemplo.com", "senha": SENHA})
    check("segundo bootstrap -> 409", r.status_code == 409, str(r.status_code))
    check("409 no envelope ApiError", r.json().get("codigo") == "CONFLICT", r.text[:150])

    r = cliente.post("/api/v1/auth/login", json={"email": "maria@exemplo.com", "senha": SENHA})
    check("login -> 200 com AuthToken", r.status_code == 200 and r.json()["tokenType"] == "Bearer", r.text[:150])
    admin = {"Authorization": f"Bearer {r.json()['accessToken']}"}

    r = cliente.post("/api/v1/usuarios", headers=admin,
                     json={"nome": "João Silva", "email": "joao@exemplo.com", "senha": SENHA})
    check("cadastro de funcionário -> 201", r.status_code == 201, r.text[:200])
    check("perfil atribuído é FUNCIONARIO", r.json()["perfil"] == "FUNCIONARIO")
    funcionario_id = r.json()["id"]

    r = cliente.post("/api/v1/auth/login", json={"email": "joao@exemplo.com", "senha": SENHA})
    func = {"Authorization": f"Bearer {r.json()['accessToken']}"}

    check("rota protegida sem token -> 401", cliente.get("/api/v1/usuarios").status_code == 401)
    check("token inválido -> 401",
          cliente.get("/api/v1/usuarios", headers={"Authorization": "Bearer nao-e-token"}).status_code == 401)
    r = cliente.get("/api/v1/usuarios", headers=func)
    check("FUNCIONARIO em rota de ADMINISTRADOR -> 403", r.status_code == 403, str(r.status_code))
    check("403 no envelope ApiError", r.json().get("codigo") == "FORBIDDEN", r.text[:150])
    check("ADMINISTRADOR lista usuários", cliente.get("/api/v1/usuarios", headers=admin).status_code == 200)
    for headers, rotulo in ((admin, "ADMINISTRADOR"), (func, "FUNCIONARIO")):
        check(f"clientes liberado a {rotulo}", cliente.get("/api/v1/clientes", headers=headers).status_code == 200)
        check(f"pedidos (só autenticação) aceita {rotulo}", cliente.get("/api/v1/pedidos", headers=headers).status_code == 200)
        check(f"alertas (só autenticação) aceita {rotulo}", cliente.get("/api/v1/alertas/reposicao", headers=headers).status_code == 200)

    # 6 — CRUD, integridade e paginação ---------------------------------------------------
    print("[6] CRUD, integridade referencial e paginação")
    check("unidade criada", cliente.post("/api/v1/unidades-medida", headers=admin,
                                         json={"unidadeMedida": "g", "porcaoPadrao": 100}).status_code == 201)
    r = cliente.post("/api/v1/unidades-medida", headers=admin,
                     json={"unidadeMedida": "g", "porcaoPadrao": 50})
    check("unidade duplicada -> 409", r.status_code == 409, str(r.status_code))

    r = cliente.post("/api/v1/ingredientes", headers=admin, json={
        "nome": "Açaí", "unidadeMedida": "g", "custoUnitario": 0.05,
        "porcaoPadrao": 100, "quantidadeMinima": 500})
    check("ingrediente criado -> 201", r.status_code == 201, r.text[:200])
    acai = r.json()["id"]
    check("ingrediente nasce com estoque zero", Decimal(str(r.json()["quantidadeEstoque"])) == 0, r.text[:200])
    check("ingrediente novo precisa de reposição", r.json()["precisaReposicao"] is True)

    r = cliente.post("/api/v1/ingredientes", headers=admin, json={
        "nome": "Leite condensado", "unidadeMedida": "ml", "custoUnitario": 0.02,
        "porcaoPadrao": 50, "quantidadeMinima": 0})
    check("unidade inexistente no cadastro -> 404", r.status_code == 404, str(r.status_code))

    r = cliente.delete("/api/v1/unidades-medida/g", headers=admin)
    check("unidade em uso -> 409", r.status_code == 409, str(r.status_code))

    r = cliente.post("/api/v1/clientes", headers=func,
                     json={"nome": "Ana Souza", "contato": "11999990000", "endereco": "Rua A, 10"})
    check("cliente criado por FUNCIONARIO -> 201", r.status_code == 201, r.text[:200])
    cliente_id = r.json()["id"]

    for i in range(3):
        cliente.post("/api/v1/clientes", headers=admin,
                     json={"nome": f"Cliente {i}", "contato": f"1198888000{i}", "endereco": "Rua B"})
    r = cliente.get("/api/v1/clientes", headers=admin, params={"page": 0, "size": 2})
    corpo = r.json()
    check("paginação devolve data e paginacao", set(corpo) == {"data", "paginacao"}, str(sorted(corpo)))
    check("metadados da paginação", corpo["paginacao"] == {"page": 0, "size": 2, "totalElements": 4, "totalPages": 2}, str(corpo["paginacao"]))
    check("tamanho da página respeitado", len(corpo["data"]) == 2)
    r = cliente.get("/api/v1/clientes", headers=admin, params={"q": "Ana"})
    check("busca textual q filtra", r.json()["paginacao"]["totalElements"] == 1, r.text[:150])
    r = cliente.get("/api/v1/clientes", headers=admin, params={"sort": "nome,desc"})
    check("ordenação desc aplicada", r.json()["data"][0]["nome"] == "Cliente 2", r.text[:150])
    r = cliente.get("/api/v1/clientes", headers=admin, params={"sort": "senha,asc"})
    check("campo de ordenação não permitido -> 400", r.status_code == 400, str(r.status_code))
    r = cliente.get("/api/v1/clientes", headers=admin, params={"size": 500})
    check("size acima do máximo -> 400 (operação declara 400)", r.status_code == 400, str(r.status_code))

    # 7 — estoque, lotes, FEFO e validade -------------------------------------------------
    print("[7] estoque: lotes, saldo derivado, FEFO e validade")
    hoje_sp = hoje()
    def entrada(ingrediente, quantidade, validade=None, headers=admin):
        corpo = {"ingredienteId": ingrediente, "tipo": "ENTRADA", "quantidade": quantidade}
        if validade:
            corpo["dataValidade"] = validade.isoformat()
        return cliente.post("/api/v1/movimentacoes-estoque", headers=headers, json=corpo)

    r = entrada(acai, 1000, hoje_sp + timedelta(days=10))
    check("ENTRADA -> 201", r.status_code == 201, r.text[:200])
    lote_longe = r.json()["id"]
    check("ENTRADA inicia quantidadeRestante igual à quantidade",
          Decimal(str(r.json()["quantidadeRestante"])) == 1000, r.text[:200])
    check("usuarioId da movimentação vem do token", r.json()["usuarioId"] == 1, r.text[:200])

    r = entrada(acai, 300, hoje_sp + timedelta(days=2))
    lote_perto = r.json()["id"]
    r = entrada(acai, 200, hoje_sp - timedelta(days=1))
    lote_vencido = r.json()["id"]

    r = cliente.get(f"/api/v1/ingredientes/{acai}", headers=admin)
    check("quantidadeEstoque soma todos os lotes", Decimal(str(r.json()["quantidadeEstoque"])) == 1500, r.text[:200])

    r = cliente.post("/api/v1/movimentacoes-estoque", headers=admin,
                     json={"ingredienteId": acai, "tipo": "SAIDA", "quantidade": 400})
    check("SAIDA -> 201", r.status_code == 201, r.text[:200])
    check("SAIDA não cria lote (sem quantidadeRestante)", r.json()["quantidadeRestante"] is None, r.text[:200])

    r = cliente.get(f"/api/v1/ingredientes/{acai}/movimentacoes", headers=func, params={"tipo": "ENTRADA"})
    check("filtro por tipo no sub-recurso", r.json()["paginacao"]["totalElements"] == 3, r.text[:150])
    movimentacoes = {m["id"]: m for m in cliente.get("/api/v1/movimentacoes-estoque", headers=admin,
                                                     params={"ingredienteId": acai, "size": 100}).json()["data"]}
    check("FEFO consumiu primeiro o lote que vence antes",
          Decimal(str(movimentacoes[lote_perto]["quantidadeRestante"])) == 0, str(movimentacoes[lote_perto]))
    check("FEFO consumiu o restante do lote mais distante",
          Decimal(str(movimentacoes[lote_longe]["quantidadeRestante"])) == 900, str(movimentacoes[lote_longe]))
    check("lote vencido permanece intocado",
          Decimal(str(movimentacoes[lote_vencido]["quantidadeRestante"])) == 200, str(movimentacoes[lote_vencido]))

    r = cliente.post("/api/v1/movimentacoes-estoque", headers=admin,
                     json={"ingredienteId": acai, "tipo": "SAIDA", "quantidade": 5000})
    check("saída acima do estoque válido -> 409", r.status_code == 409, str(r.status_code))
    r = cliente.post("/api/v1/movimentacoes-estoque", headers=admin,
                     json={"ingredienteId": 9999, "tipo": "ENTRADA", "quantidade": 10})
    check("ingrediente inexistente -> 404", r.status_code == 404, str(r.status_code))

    r = cliente.get("/api/v1/alertas/validade", headers=func, params={"diasAntecedencia": 7})
    situacoes = {item["movimentacaoId"]: item["situacao"] for item in r.json()["itens"]}
    check("alerta de validade classifica VENCIDO", situacoes.get(lote_vencido) == "VENCIDO", str(situacoes))
    check("lote distante fora da janela de 7 dias", lote_longe not in situacoes, str(situacoes))
    check("lote esgotado pelo FEFO sai dos alertas", lote_perto not in situacoes, str(situacoes))
    r = cliente.get("/api/v1/alertas/validade", headers=func, params={"diasAntecedencia": 15})
    situacoes_15 = {item["movimentacaoId"]: item for item in r.json()["itens"]}
    check("alerta de validade classifica PROXIMO_VENCIMENTO",
          situacoes_15.get(lote_longe, {}).get("situacao") == "PROXIMO_VENCIMENTO", str(situacoes_15))
    check("diasAteVencimento positivo para lote válido",
          situacoes_15.get(lote_longe, {}).get("diasAteVencimento") == 10, str(situacoes_15))
    check("diasAteVencimento negativo para lote vencido",
          situacoes_15.get(lote_vencido, {}).get("diasAteVencimento") == -1, str(situacoes_15))
    r = cliente.get("/api/v1/alertas/validade", headers=func, params={"incluirVencidos": False})
    check("incluirVencidos=false remove vencidos",
          all(i["situacao"] != "VENCIDO" for i in r.json()["itens"]), r.text[:200])

    # 8 — produtos, composição e pedidos --------------------------------------------------
    print("[8] produtos, composição, pedidos e cancelamento")
    r = cliente.post("/api/v1/produtos", headers=admin, json={
        "nome": "Açaí 300ml", "precoVenda": 15.00, "ativo": True,
        "composicao": [{"ingredienteId": acai, "quantidadeUtilizada": 200}]})
    check("produto criado -> 201", r.status_code == 201, r.text[:200])
    produto_id = r.json()["id"]
    check("composição devolvida com nome e unidade do ingrediente",
          r.json()["composicao"][0]["nomeIngrediente"] == "Açaí"
          and r.json()["composicao"][0]["unidadeMedida"] == "g", r.text[:250])

    r = cliente.post("/api/v1/produtos", headers=admin, json={
        "nome": "Inválido", "precoVenda": 10.00, "ativo": True,
        "composicao": [{"ingredienteId": 9999, "quantidadeUtilizada": 1}]})
    check("composição com ingrediente inexistente -> 404", r.status_code == 404, str(r.status_code))
    r = cliente.post("/api/v1/produtos", headers=admin, json={
        "nome": "Duplicado", "precoVenda": 10.00, "ativo": True,
        "composicao": [{"ingredienteId": acai, "quantidadeUtilizada": 1},
                       {"ingredienteId": acai, "quantidadeUtilizada": 2}]})
    check("ingrediente repetido na composição -> 422", r.status_code == 422, str(r.status_code))

    r = cliente.delete(f"/api/v1/ingredientes/{acai}", headers=admin)
    check("ingrediente em composição -> 409", r.status_code == 409, str(r.status_code))

    saldo_antes = Decimal(str(cliente.get(f"/api/v1/ingredientes/{acai}", headers=admin).json()["quantidadeEstoque"]))
    r = cliente.post("/api/v1/pedidos", headers=func,
                     json={"clienteId": cliente_id, "itens": [{"produtoId": produto_id, "quantidade": 2}]})
    check("pedido registrado -> 201", r.status_code == 201, r.text[:250])
    pedido = r.json()
    pedido_id = pedido["id"]
    check("preço capturado no item", Decimal(str(pedido["itens"][0]["precoUnitarioRegistrado"])) == Decimal("15.00"), str(pedido["itens"]))
    check("subtotal e total em Decimal", Decimal(str(pedido["itens"][0]["subtotal"])) == Decimal("30.00")
          and Decimal(str(pedido["valorTotal"])) == Decimal("30.00"), str(pedido))
    check("usuarioId do pedido vem do token", pedido["usuarioId"] == funcionario_id, str(pedido["usuarioId"]))
    check("pedido nasce ATIVO", pedido["status"] == "ATIVO")

    saldo_depois = Decimal(str(cliente.get(f"/api/v1/ingredientes/{acai}", headers=admin).json()["quantidadeEstoque"]))
    check("baixa de estoque aplicada (2 x 200 g)", saldo_antes - saldo_depois == 400, f"{saldo_antes} -> {saldo_depois}")
    baixas = [m for m in cliente.get("/api/v1/movimentacoes-estoque", headers=admin,
                                     params={"tipo": "SAIDA", "size": 100}).json()["data"]
              if m["motivo"] == "PEDIDO"]
    check("baixa automática registrada com motivo PEDIDO", len(baixas) == 1, str(baixas))

    r = cliente.put(f"/api/v1/produtos/{produto_id}", headers=admin,
                    json={"nome": "Açaí 300ml", "precoVenda": 25.00, "ativo": True})
    check("preço do produto atualizado", r.status_code == 200 and Decimal(str(r.json()["precoVenda"])) == 25, r.text[:150])
    r = cliente.get(f"/api/v1/pedidos/{pedido_id}", headers=admin)
    check("preço histórico do pedido não mudou",
          Decimal(str(r.json()["itens"][0]["precoUnitarioRegistrado"])) == Decimal("15.00"), r.text[:250])

    r = cliente.delete(f"/api/v1/clientes/{cliente_id}", headers=admin)
    check("cliente com pedido -> 409", r.status_code == 409, str(r.status_code))

    # Transação atômica: pedido que estoura o estoque não deixa rastro.
    pedidos_antes = cliente.get("/api/v1/pedidos", headers=admin).json()["paginacao"]["totalElements"]
    saldo_antes = Decimal(str(cliente.get(f"/api/v1/ingredientes/{acai}", headers=admin).json()["quantidadeEstoque"]))
    r = cliente.post("/api/v1/pedidos", headers=func,
                     json={"itens": [{"produtoId": produto_id, "quantidade": 9999}]})
    check("pedido sem estoque -> 409", r.status_code == 409, str(r.status_code))
    pedidos_depois = cliente.get("/api/v1/pedidos", headers=admin).json()["paginacao"]["totalElements"]
    saldo_apos_falha = Decimal(str(cliente.get(f"/api/v1/ingredientes/{acai}", headers=admin).json()["quantidadeEstoque"]))
    check("rollback integral: nenhum pedido criado", pedidos_depois == pedidos_antes, f"{pedidos_antes} -> {pedidos_depois}")
    check("rollback integral: estoque intacto", saldo_apos_falha == saldo_antes, f"{saldo_antes} -> {saldo_apos_falha}")

    r = cliente.post("/api/v1/pedidos", headers=func, json={"itens": [{"produtoId": 9999, "quantidade": 1}]})
    check("produto inexistente no pedido -> 404", r.status_code == 404, str(r.status_code))

    saldo_antes_cancelamento = Decimal(str(cliente.get(f"/api/v1/ingredientes/{acai}", headers=admin).json()["quantidadeEstoque"]))
    r = cliente.post(f"/api/v1/pedidos/{pedido_id}/cancelamento", headers=admin,
                     json={"observacao": "Cliente desistiu."})
    check("cancelamento -> 200", r.status_code == 200, r.text[:200])
    check("status CANCELADO com data e usuário",
          r.json()["status"] == "CANCELADO" and r.json()["dataCancelamento"]
          and r.json()["usuarioCancelamentoId"] == 1, r.text[:250])
    saldo_apos_cancelamento = Decimal(str(cliente.get(f"/api/v1/ingredientes/{acai}", headers=admin).json()["quantidadeEstoque"]))
    check("cancelamento NÃO devolve estoque", saldo_apos_cancelamento == saldo_antes_cancelamento,
          f"{saldo_antes_cancelamento} -> {saldo_apos_cancelamento}")
    r = cliente.post(f"/api/v1/pedidos/{pedido_id}/cancelamento", headers=admin, json={})
    check("cancelar pedido já cancelado -> 409", r.status_code == 409, str(r.status_code))
    check("pedido cancelado continua consultável",
          cliente.get(f"/api/v1/pedidos/{pedido_id}", headers=admin).status_code == 200)

    r = cliente.delete(f"/api/v1/produtos/{produto_id}", headers=admin)
    check("desativar produto -> 204 sem corpo", r.status_code == 204 and r.content == b"", repr(r.content))
    check("produto desativado continua existindo",
          cliente.get(f"/api/v1/produtos/{produto_id}", headers=admin).json()["ativo"] is False)
    r = cliente.post("/api/v1/pedidos", headers=func, json={"itens": [{"produtoId": produto_id, "quantidade": 1}]})
    check("pedido com produto desativado -> 409 (decisão da Fase 5)", r.status_code == 409, str(r.status_code))
    cliente.put(f"/api/v1/produtos/{produto_id}", headers=admin,
                json={"nome": "Açaí 300ml", "precoVenda": 15.00, "ativo": True})

    # 9 — recomendações, marketing e 503 --------------------------------------------------
    print("[9] recomendações, marketing e indisponibilidade do solver")
    r = cliente.post("/api/v1/recomendacoes/producao", headers=admin)
    check("recomendação de produção -> 200", r.status_code == 200, r.text[:250])
    producao = r.json()
    check("critério é LUCRO_ESTIMADO", producao["criterioOtimizacao"] == "LUCRO_ESTIMADO")
    check("quantidades recomendadas são inteiras",
          all(isinstance(i["quantidadeRecomendada"], int) for i in producao["itens"]), str(producao["itens"]))
    saldo_valido_atual = Decimal(str(cliente.get(f"/api/v1/ingredientes/{acai}", headers=admin).json()["quantidadeEstoque"])) - 200
    if producao["itens"]:
        consumo = Decimal(producao["itens"][0]["quantidadeRecomendada"]) * 200
        check("produção respeita o estoque válido (lote vencido fora)", consumo <= saldo_valido_atual,
              f"consumo={consumo} saldo_valido={saldo_valido_atual}")
    check("FUNCIONARIO não acessa recomendações -> 403",
          cliente.post("/api/v1/recomendacoes/producao", headers=func).status_code == 403)

    r = cliente.post("/api/v1/recomendacoes/reposicao", headers=admin, json={"periodoDias": 30, "orcamento": 100})
    check("recomendação de reposição -> 200", r.status_code == 200, r.text[:250])
    reposicao = r.json()
    check("custo total respeita o orçamento", Decimal(str(reposicao["custoTotalEstimado"])) <= Decimal(100), r.text[:250])
    check("período ecoado na resposta", reposicao["periodoDias"] == 30)

    r = cliente.post("/api/v1/sugestoes-marketing", headers=admin)
    check("sugestões de marketing -> 200", r.status_code == 200, r.text[:200])
    check("sugestões vêm como lista de textos",
          isinstance(r.json()["sugestoes"], list) and all(isinstance(s, str) for s in r.json()["sugestoes"]), r.text[:200])

    original = optimizer._pulp
    def _indisponivel():
        raise optimizer.SolverIndisponivelError("Solver de otimização indisponível.")
    optimizer._pulp = _indisponivel
    try:
        r = cliente.post("/api/v1/recomendacoes/producao", headers=admin)
        check("solver indisponível -> 503", r.status_code == 503, str(r.status_code))
        check("503 no envelope ApiError", r.json().get("codigo") == "SERVICE_UNAVAILABLE", r.text[:200])
        check("503 não expõe detalhe interno", "pulp" not in r.text.lower() and "Traceback" not in r.text)
        r = cliente.post("/api/v1/recomendacoes/reposicao", headers=admin, json={"periodoDias": 7, "orcamento": 50})
        check("reposição com solver indisponível -> 503", r.status_code == 503, str(r.status_code))
    finally:
        optimizer._pulp = original

    # 10 — dashboard e CSV ----------------------------------------------------------------
    print("[10] dashboard, pedidos cancelados e exportação CSV")
    inicio = (hoje_sp - timedelta(days=1)).isoformat()
    fim = (hoje_sp + timedelta(days=1)).isoformat()
    r = cliente.post("/api/v1/pedidos", headers=func, json={"itens": [{"produtoId": produto_id, "quantidade": 1}]})
    check("novo pedido ativo registrado", r.status_code == 201, r.text[:200])

    r = cliente.get("/api/v1/dashboard", headers=admin, params={"dataInicio": inicio, "dataFim": fim})
    check("dashboard -> 200", r.status_code == 200, r.text[:200])
    painel = r.json()
    check("dashboard ignora pedidos cancelados", painel["quantidadePedidos"] == 1, str(painel))
    check("faturamento considera só o pedido ativo", Decimal(str(painel["faturamentoTotal"])) == Decimal("15.00"), str(painel))
    check("ticket médio calculado", Decimal(str(painel["ticketMedio"])) == Decimal("15.00"), str(painel))
    check("ranking de produtos presente", painel["produtosMaisVendidos"][0]["quantidadeVendida"] == 1, str(painel["produtosMaisVendidos"]))
    r = cliente.get("/api/v1/dashboard", headers=admin, params={"dataInicio": fim, "dataFim": inicio})
    check("dataFim anterior a dataInicio -> 400", r.status_code == 400, str(r.status_code))
    check("dashboard exige ADMINISTRADOR -> 403",
          cliente.get("/api/v1/dashboard", headers=func, params={"dataInicio": inicio, "dataFim": fim}).status_code == 403)

    r = cliente.get("/api/v1/dashboard/exportacao", headers=admin, params={"dataInicio": inicio, "dataFim": fim})
    check("exportação -> 200", r.status_code == 200, str(r.status_code))
    check("media type é text/csv", r.headers["content-type"].startswith("text/csv"), r.headers.get("content-type", ""))
    check("charset UTF-8 declarado", "utf-8" in r.headers["content-type"].lower(), r.headers.get("content-type", ""))
    check("header Content-Disposition presente", "attachment" in r.headers.get("content-disposition", ""), r.headers.get("content-disposition", ""))
    check("corpo é CSV, não JSON", r.text.startswith("secao,chave,valor") and not r.text.startswith("{"), r.text[:80])
    check("CSV decodifica em UTF-8", r.content.decode("utf-8") == r.text)
    check("CSV sem BOM", not r.content.startswith(b"\xef\xbb\xbf"))
    check("CSV traz os indicadores do período", "faturamentoTotal" in r.text and "quantidadePedidos" in r.text, r.text[:200])

    # 11 — carregamento sem N+1 -----------------------------------------------------------
    print("[11] ausência de N+1 nos carregamentos relevantes")
    for extra in range(3):
        cliente.post("/api/v1/pedidos", headers=func, json={"itens": [{"produtoId": produto_id, "quantidade": 1}]})
    consultas.clear()
    r = cliente.get("/api/v1/pedidos", headers=admin, params={"size": 100})
    selects_pedidos = [c for c in consultas if c.lstrip().upper().startswith("SELECT")]
    check("listagem de pedidos responde 200", r.status_code == 200)
    check("itens de pedido carregados em lote (sem N+1)", len(selects_pedidos) <= 6,
          f"{len(selects_pedidos)} SELECTs para {r.json()['paginacao']['totalElements']} pedidos")
    consultas.clear()
    r = cliente.get("/api/v1/produtos", headers=admin, params={"size": 100})
    selects_produtos = [c for c in consultas if c.lstrip().upper().startswith("SELECT")]
    check("composição carregada em lote (sem N+1)", len(selects_produtos) <= 6,
          f"{len(selects_produtos)} SELECTs")

    print()
    print(f"{OK} verificações OK, {FAIL} falhas")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
