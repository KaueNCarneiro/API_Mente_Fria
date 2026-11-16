# ruff: noqa: C408, SIM102  -- script auxiliar de verificação
"""Verificação Pydantic x OpenAPI (Fase 2) — Mente Fria API.

Compara `src/api/schemas.py` com uma transcrição compacta de `components.schemas`
do `Mente Fria API.openapi.json` (somente estrutura/restrições; descrições e
exemplos NÃO são comparados automaticamente). Uso, na raiz do repositório:

    python verify_schemas.py
    python verify_schemas.py --openapi "Mente Fria API.openapi.json"   # comparação direta

Sem `--openapi`, a conferência usa a transcrição `SPEC` abaixo (feita à mão a partir do
contrato). Com `--openapi`, cada schema do arquivo é comparado com a transcrição E com os
modelos Pydantic (tipos, limites, enums, nullability, required, additionalProperties,
descrições e exemplos), eliminando a dependência da transcrição.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError

from src.api import schemas as S


# ----------------------------- transcrição do contrato -----------------------------
def s(minL=None, maxL=None, fmt=None, enum=None, pat=None, null=False, default=None):
    d: dict[str, Any] = {"t": "string"}
    for k, v in dict(minL=minL, maxL=maxL, fmt=fmt, enum=enum, pat=pat, default=default).items():
        if v is not None:
            d[k] = v
    d["null"] = null
    return d

def n(mn=None, mx=None, mult=None, null=False, default=None):
    d: dict[str, Any] = {"t": "number", "null": null}
    for k, v in dict(min=mn, max=mx, mult=mult, default=default).items():
        if v is not None:
            d[k] = v
    return d

def i(mn=None, mx=None, fmt=None, null=False):
    d: dict[str, Any] = {"t": "integer", "null": null}
    for k, v in dict(min=mn, max=mx, fmt=fmt).items():
        if v is not None:
            d[k] = v
    return d

def b(default=None):
    d: dict[str, Any] = {"t": "boolean", "null": False}
    if default is not None:
        d["default"] = default
    return d

def arr(items, minItems=None):
    d: dict[str, Any] = {"t": "array", "items": items, "null": False}
    if minItems is not None:
        d["minItems"] = minItems
    return d

def ref(name, null=False):
    return {"t": "ref", "ref": name, "null": null}

ID = i(1, None, "int32")
EMAIL = s(maxL=150, fmt="email")
DT = s(fmt="date-time")
DATE = s(fmt="date")
PERFIL = s(enum=["ADMINISTRADOR", "FUNCIONARIO"])
TIPO = s(enum=["ENTRADA", "SAIDA"])
STATUS = s(enum=["ATIVO", "CANCELADO"])
PAT = r"^[a-zA-Z][a-zA-Z0-9_-]{0,19}$"
M3 = ("0.001", "9999999.999", "0.001")  # quantidades >0 com máximo
R2 = "0.01"

def q3pos(mx=True):  return n("0.001", "9999999.999" if mx else None, "0.001")
def q3nn(mx=True):   return n("0", "9999999.999" if mx else None, "0.001")
def r_nn(mx=False):  return n("0", "99999999.99" if mx else None, "0.01")
def r_pos(mx=False): return n("0.01", "99999999.99" if mx else None, "0.01")

def page_of(item): return {"req": ["data", "paginacao"],
                           "props": {"data": arr(ref(item)), "paginacao": ref("PageMetadata")}}

SPEC: dict[str, dict] = {
 "ApiErrorDetail": {"req": ["campo", "mensagem"], "props": {
    "campo": s(maxL=100), "mensagem": s(maxL=500), "valorRejeitado": s(maxL=500, null=True)}},
 "ApiError": {"req": ["codigo", "mensagem", "detalhes", "timestamp", "caminho"], "props": {
    "codigo": s(maxL=80), "mensagem": s(maxL=500), "detalhes": arr(ref("ApiErrorDetail")),
    "timestamp": DT, "caminho": s(maxL=300), "correlationId": s(maxL=100, null=True)}},
 "PageMetadata": {"req": ["page", "size", "totalElements", "totalPages"], "props": {
    "page": i(0), "size": i(1, 100), "totalElements": i(0), "totalPages": i(0)}},
 "CreateAdminDTO": {"req": ["nome", "email", "senha"], "props": {
    "nome": s(2, 150), "email": EMAIL, "senha": s(8, 128)}},
 "CreateFuncionarioDTO": {"req": ["nome", "email", "senha"], "props": {
    "nome": s(2, 150), "email": EMAIL, "senha": s(8, 128)}},
 "UpdateUsuarioDTO": {"req": [], "props": {"nome": s(2, 150), "email": EMAIL, "ativo": b()}},
 "Usuario": {"req": ["id", "nome", "email", "perfil", "ativo"], "props": {
    "id": ID, "nome": s(maxL=150), "email": EMAIL, "perfil": PERFIL, "ativo": b()}},
 "LoginDTO": {"req": ["email", "senha"], "props": {"email": EMAIL, "senha": s(8, 128)}},
 "AuthToken": {"req": ["accessToken", "tokenType", "expiresInSeconds", "usuario"], "props": {
    "accessToken": s(), "tokenType": s(enum=["Bearer"], default="Bearer"),
    "expiresInSeconds": i(1), "usuario": ref("Usuario")}},
 "CreateClienteDTO": {"req": ["nome", "contato", "endereco"], "props": {
    "nome": s(2, 150), "contato": s(3, 50), "endereco": s(3, 255)}},
 "UpdateClienteDTO": {"req": ["nome", "contato", "endereco"], "props": {
    "nome": s(2, 150), "contato": s(3, 50), "endereco": s(3, 255)}},
 "Cliente": {"req": ["id", "nome", "contato", "endereco"], "props": {
    "id": ID, "nome": s(maxL=150), "contato": s(maxL=50), "endereco": s(maxL=255)}},
 "UnidadeMedida": {"req": ["unidadeMedida", "porcaoPadrao"], "props": {
    "unidadeMedida": s(1, 20, pat=PAT), "porcaoPadrao": q3pos()}},
 "CreateUnidadeMedidaDTO": {"req": ["unidadeMedida", "porcaoPadrao"], "props": {
    "unidadeMedida": s(1, 20, pat=PAT), "porcaoPadrao": q3pos()}},
 "UpdateUnidadeMedidaDTO": {"req": ["porcaoPadrao"], "props": {"porcaoPadrao": q3pos()}},
 "CreateIngredienteDTO": {"req": ["nome", "unidadeMedida", "custoUnitario", "porcaoPadrao"], "props": {
    "nome": s(2, 100), "unidadeMedida": s(1, 20), "custoUnitario": r_nn(True),
    "porcaoPadrao": q3pos(), "quantidadeMinima": n("0", "9999999.999", "0.001", default=0)}},
 "UpdateIngredienteDTO": {"req": ["nome", "unidadeMedida", "custoUnitario", "porcaoPadrao",
                                  "quantidadeMinima"], "props": {
    "nome": s(2, 100), "unidadeMedida": s(1, 20), "custoUnitario": r_nn(True),
    "porcaoPadrao": q3pos(), "quantidadeMinima": q3nn()}},
 "Ingrediente": {"req": ["id", "nome", "unidadeMedida", "custoUnitario", "porcaoPadrao",
                         "quantidadeEstoque", "quantidadeMinima", "precisaReposicao"], "props": {
    "id": ID, "nome": s(maxL=100), "unidadeMedida": s(maxL=20), "custoUnitario": r_nn(True),
    "porcaoPadrao": q3pos(False), "quantidadeEstoque": q3nn(False),
    "quantidadeMinima": q3nn(False), "precisaReposicao": b()}},
 "ComposicaoProdutoItemDTO": {"req": ["ingredienteId", "quantidadeUtilizada"], "props": {
    "ingredienteId": ID, "quantidadeUtilizada": q3pos()}},
 "ComposicaoProdutoItem": {"req": ["ingredienteId", "nomeIngrediente", "unidadeMedida",
                                   "quantidadeUtilizada"], "props": {
    "ingredienteId": ID, "nomeIngrediente": s(maxL=100), "unidadeMedida": s(maxL=20),
    "quantidadeUtilizada": q3pos(False)}},
 "CreateProdutoDTO": {"req": ["nome", "precoVenda", "composicao"], "props": {
    "nome": s(2, 100), "precoVenda": r_pos(True), "ativo": b(True),
    "composicao": arr(ref("ComposicaoProdutoItemDTO"), 1)}},
 "UpdateProdutoDTO": {"req": ["nome", "precoVenda", "ativo"], "props": {
    "nome": s(2, 100), "precoVenda": r_pos(True), "ativo": b()}},
 "Produto": {"req": ["id", "nome", "precoVenda", "ativo", "composicao"], "props": {
    "id": ID, "nome": s(maxL=100), "precoVenda": r_pos(False), "ativo": b(),
    "composicao": arr(ref("ComposicaoProdutoItem"), 1)}},
 "CreateMovimentacaoEstoqueDTO": {"req": ["ingredienteId", "tipo", "quantidade"], "props": {
    "ingredienteId": ID, "tipo": TIPO, "quantidade": q3pos(),
    "observacao": s(maxL=255, null=True), "dataValidade": s(fmt="date", null=True),
    "motivo": s(enum=["CONVENCIONAL", "DESCARTE_VENCIDO"], null=True)}},
 "MovimentacaoEstoque": {"req": ["id", "ingredienteId", "usuarioId", "tipo", "quantidade",
                                 "dataMovimentacao"], "props": {
    "id": ID, "ingredienteId": ID, "usuarioId": ID, "tipo": TIPO, "quantidade": q3pos(False),
    "dataMovimentacao": DT, "observacao": s(maxL=255, null=True),
    "dataValidade": s(fmt="date", null=True),
    "quantidadeRestante": n("0", None, "0.001", null=True),
    "motivo": s(enum=["PEDIDO", "CONVENCIONAL", "DESCARTE_VENCIDO"], null=True)}},
 "PedidoItemDTO": {"req": ["produtoId", "quantidade"], "props": {
    "produtoId": ID, "quantidade": i(1, 10000, "int32")}},
 "CreatePedidoDTO": {"req": ["itens"], "props": {
    "clienteId": i(1, None, "int32", null=True), "itens": arr(ref("PedidoItemDTO"), 1)}},
 "PedidoItem": {"req": ["produtoId", "nomeProduto", "quantidade", "precoUnitarioRegistrado",
                        "subtotal"], "props": {
    "produtoId": ID, "nomeProduto": s(maxL=100), "quantidade": i(1, None, "int32"),
    "precoUnitarioRegistrado": r_pos(False), "subtotal": r_nn(False)}},
 "Pedido": {"req": ["id", "usuarioId", "dataPedido", "valorTotal", "status", "itens"], "props": {
    "id": ID, "clienteId": i(1, None, "int32", null=True), "usuarioId": ID, "dataPedido": DT,
    "valorTotal": r_nn(False), "status": STATUS,
    "dataCancelamento": s(fmt="date-time", null=True),
    "usuarioCancelamentoId": i(1, None, "int32", null=True),
    "itens": arr(ref("PedidoItem"), 1)}},
 "CancelamentoPedidoDTO": {"req": [], "props": {"observacao": s(maxL=255, null=True)}},
 "ProducaoRecomendacaoItem": {"req": ["produtoId", "nomeProduto", "quantidadeRecomendada",
                                      "lucroEstimadoUnitario", "lucroEstimadoTotal"], "props": {
    "produtoId": ID, "nomeProduto": s(maxL=100), "quantidadeRecomendada": i(0, None, "int32"),
    "lucroEstimadoUnitario": r_nn(False), "lucroEstimadoTotal": r_nn(False)}},
 "ProducaoRecomendacao": {"req": ["calculadoEm", "criterioOtimizacao", "lucroTotalEstimado",
                                  "itens"], "props": {
    "calculadoEm": DT, "criterioOtimizacao": s(enum=["LUCRO_ESTIMADO"]),
    "lucroTotalEstimado": r_nn(False), "itens": arr(ref("ProducaoRecomendacaoItem"), 0),
    "observacao": s(maxL=500)}},
 "CreateReposicaoDTO": {"req": ["periodoDias", "orcamento"], "props": {
    "periodoDias": i(1, 365, "int32"), "orcamento": r_nn(True)}},
 "ReposicaoRecomendacaoItem": {"req": ["ingredienteId", "nomeIngrediente",
                                       "quantidadeRecomendada", "unidadeMedida",
                                       "custoEstimado"], "props": {
    "ingredienteId": ID, "nomeIngrediente": s(maxL=100), "quantidadeRecomendada": q3nn(False),
    "unidadeMedida": s(maxL=20), "custoEstimado": r_nn(False)}},
 "ReposicaoRecomendacao": {"req": ["calculadoEm", "periodoDias", "orcamento",
                                   "custoTotalEstimado", "itens"], "props": {
    "calculadoEm": DT, "periodoDias": i(1, 365), "orcamento": r_nn(False),
    "custoTotalEstimado": r_nn(False), "itens": arr(ref("ReposicaoRecomendacaoItem"), 0)}},
 "AlertaReposicao": {"req": ["ingredienteId", "nomeIngrediente", "quantidadeEstoqueValido",
                             "quantidadeMinima", "unidadeMedida", "deficit"], "props": {
    "ingredienteId": ID, "nomeIngrediente": s(maxL=100),
    "quantidadeEstoqueValido": q3nn(False), "quantidadeMinima": q3nn(False),
    "unidadeMedida": s(maxL=20), "deficit": q3nn(False)}},
 "AlertaValidade": {"req": ["movimentacaoId", "ingredienteId", "nomeIngrediente", "dataValidade",
                            "quantidadeRestante", "diasAteVencimento", "situacao"], "props": {
    "movimentacaoId": ID, "ingredienteId": ID, "nomeIngrediente": s(maxL=100),
    "dataValidade": DATE, "quantidadeRestante": q3nn(False), "diasAteVencimento": i(),
    "situacao": s(enum=["PROXIMO_VENCIMENTO", "VENCIDO"])}},
 "SugestaoMarketing": {"req": ["geradoEm", "sugestoes"], "props": {
    "geradoEm": DT, "sugestoes": arr(s(maxL=1000), 0), "observacao": s(maxL=500, null=True)}},
 "Dashboard": {"req": ["periodoInicio", "periodoFim", "quantidadePedidos", "faturamentoTotal",
                       "ticketMedio", "produtosMaisVendidos", "ingredientesEmReposicao",
                       "linhasProximasVencimento"], "props": {
    "periodoInicio": DATE, "periodoFim": DATE, "quantidadePedidos": i(0),
    "faturamentoTotal": r_nn(False), "ticketMedio": r_nn(False),
    "produtosMaisVendidos": arr(ref("ProdutoMaisVendido"), 0),
    "ingredientesEmReposicao": i(0), "linhasProximasVencimento": i(0)}},
 "ProdutoMaisVendido": {"req": ["produtoId", "nomeProduto", "quantidadeVendida"], "props": {
    "produtoId": ID, "nomeProduto": s(maxL=100), "quantidadeVendida": i(0)}},
 "HealthStatus": {"req": ["status", "banco"], "props": {
    "status": s(enum=["ok", "degradado"]), "banco": s(enum=["ok", "indisponivel"])}},
 "PaginatedUsuarios": page_of("Usuario"),
 "PaginatedClientes": page_of("Cliente"),
 "PaginatedUnidadesMedida": page_of("UnidadeMedida"),
 "PaginatedIngredientes": page_of("Ingrediente"),
 "PaginatedProdutos": page_of("Produto"),
 "PaginatedMovimentacoesEstoque": page_of("MovimentacaoEstoque"),
 "PaginatedPedidos": page_of("Pedido"),
 "ComposicaoProduto": {"req": ["produtoId", "itens"], "props": {
    "produtoId": ID, "itens": arr(ref("ComposicaoProdutoItem"), 1)}},
 "SubstituirComposicaoDTO": {"req": ["itens"], "props": {
    "itens": arr(ref("ComposicaoProdutoItemDTO"), 1)}},
 "VazioDTO": {"req": [], "props": {}},
 "ListaAlertasReposicao": {"req": ["itens"], "props": {"itens": arr(ref("AlertaReposicao"))}},
 "ListaAlertasValidade": {"req": ["itens"], "props": {"itens": arr(ref("AlertaValidade"))}},
}
CSV = "CsvFile"  # string/binary, tratado à parte
EXPECTED_54 = set(SPEC) | {CSV}

# ----------------------------------- geração -----------------------------------
def valid_value(p: dict) -> Any:
    t = p["t"]
    if t == "ref":
        return valid_obj(p["ref"])
    if t == "array":
        mi = p.get("minItems", 0) or 0
        return [valid_value(p["items"]) for _ in range(max(mi, 1))]
    if t == "boolean":
        return True
    if t == "integer":
        return p.get("min", 1) if p.get("min", 1) >= 1 else 1 if p.get("min") is None else p["min"]
    if t == "number":
        return Decimal(p["min"]) if p.get("min") is not None else Decimal(1)
    # string
    if p.get("enum"):
        return p["enum"][0]
    f = p.get("fmt")
    if f == "email":
        return "a@exemplo.com"
    if f == "date":
        return "2026-01-01"
    if f == "date-time":
        return "2026-01-01T00:00:00-03:00"
    if p.get("pat"):
        return "kg"
    return "x" * max(p.get("minL") or 1, 1)

def valid_obj(name: str, only_required: bool = False) -> dict:
    sp = SPEC[name]
    keys = sp["req"] if only_required else list(sp["props"])
    return {k: valid_value(sp["props"][k]) for k in keys}

def dumps(obj: Any) -> str:
    return json.dumps(obj, default=lambda d: float(d) if isinstance(d, Decimal) else str(d))

failures: list[str] = []
checks = 0

def ok(cond: bool, msg: str) -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(msg)

def accepts(model: type[BaseModel], data: dict) -> bool:
    try:
        model.model_validate_json(dumps(data))
        return True
    except ValidationError:
        return False

# ----------------------------------- 1. inventário -----------------------------------
ok(set(S.__all__) == EXPECTED_54, f"__all__ difere dos 54 schemas: {set(S.__all__) ^ EXPECTED_54}")
ok(len(EXPECTED_54) == 54, f"esperado 54, transcrição tem {len(EXPECTED_54)}")
for name in EXPECTED_54:
    ok(hasattr(S, name), f"schema ausente: {name}")
ok(len(set(S.__all__)) == len(S.__all__), "nomes duplicados em __all__")
defined = {k for k, v in vars(S).items() if isinstance(v, type) and issubclass(v, BaseModel)
           and v is not BaseModel and not k.startswith("_")}
ok(defined == set(SPEC), f"classes extras/ausentes: {defined ^ set(SPEC)}")

# ----------------------------------- 2. estrutura -----------------------------------
for name, sp in SPEC.items():
    M: type[BaseModel] = getattr(S, name)
    js = M.model_json_schema(mode="serialization")
    ok(set(js.get("properties", {})) == set(sp["props"]), f"{name}: propriedades {set(js.get('properties', {})) ^ set(sp['props'])}")
    ok(set(M.model_fields) == set(sp["props"]), f"{name}: model_fields")
    ok(set(js.get("required", [])) == set(sp["req"]), f"{name}: required {set(js.get('required', [])) ^ set(sp['req'])}")
    ok(js.get("additionalProperties") is False, f"{name}: additionalProperties != false")
    ok(M.model_config.get("extra") == "forbid", f"{name}: extra != forbid")
    ok(M.model_config.get("from_attributes") is True, f"{name}: from_attributes")
    ok(not any("alias" in str(f.alias or "") for f in M.model_fields.values()) and
       all(f.alias is None for f in M.model_fields.values()), f"{name}: alias inesperado")
    ok(bool(M.__doc__ and M.__doc__.strip()), f"{name}: sem descrição")
    for pn, f in M.model_fields.items():
        ok(bool(f.description) or sp["props"][pn]["t"] == "ref" and False or bool(f.description),
           f"{name}.{pn}: sem description")
    # validação de requireds de entrada (AuthToken.tokenType tem default)
    if name != "AuthToken":
        ok(all(M.model_fields[k].is_required() for k in sp["req"]), f"{name}: required (validação)")
        ok(all(not M.model_fields[k].is_required() for k in sp["props"] if k not in sp["req"]),
           f"{name}: opcional marcado como required")
    # defaults
    for pn, p in sp["props"].items():
        if "default" in p:
            got = M.model_fields[pn].default
            ok(got == (Decimal(p["default"]) if p["t"] == "number" else p["default"]),
               f"{name}.{pn}: default {got!r} != {p['default']!r}")

# ----------------------------------- 3. comportamento -----------------------------------
def mutate(name: str, key: str, value: Any) -> dict:
    d = valid_obj(name)
    d[key] = value
    return d

for name, sp in SPEC.items():
    M = getattr(S, name)
    full = valid_obj(name)
    ok(accepts(M, full), f"{name}: baseline completo rejeitado")
    ok(accepts(M, valid_obj(name, True)), f"{name}: baseline só-required rejeitado")
    ok(not accepts(M, {**full, "campoInexistente": 1}), f"{name}: aceitou campo extra")
    for k in sp["req"]:
        d = dict(full); d.pop(k)
        if name == "AuthToken" and k == "tokenType":
            continue  # tem default (documentado)
        ok(not accepts(M, d), f"{name}: aceitou sem required '{k}'")
    for k in sp["props"]:
        if k not in sp["req"]:
            d = dict(full); d.pop(k)
            ok(accepts(M, d), f"{name}: rejeitou sem opcional '{k}'")
    for k, p in sp["props"].items():
        w = f"{name}.{k}"
        ok(accepts(M, mutate(name, k, None)) == bool(p.get("null")),
           f"{w}: null {'deveria ser aceito' if p.get('null') else 'deveria ser rejeitado'}")
        t = p["t"]
        if t == "integer":
            mn, mx = p.get("min"), p.get("max")
            if mn is not None:
                ok(accepts(M, mutate(name, k, mn)), f"{w}: mínimo {mn} rejeitado")
                ok(not accepts(M, mutate(name, k, mn - 1)), f"{w}: aceitou abaixo do mínimo")
            if mx is not None:
                ok(accepts(M, mutate(name, k, mx)), f"{w}: máximo {mx} rejeitado")
                ok(not accepts(M, mutate(name, k, mx + 1)), f"{w}: aceitou acima do máximo")
            if p.get("fmt") == "int32" and mx is None:
                ok(accepts(M, mutate(name, k, 2147483647)), f"{w}: int32 máx rejeitado")
                ok(not accepts(M, mutate(name, k, 2147483648)), f"{w}: aceitou > int32")
            ok(not accepts(M, mutate(name, k, "abc")), f"{w}: aceitou string não numérica")
            ok(not accepts(M, mutate(name, k, 1.5)), f"{w}: aceitou fração em inteiro")
        elif t == "number":
            mn = Decimal(p["min"]) if p.get("min") is not None else None
            mx = Decimal(p["max"]) if p.get("max") is not None else None
            mult = Decimal(p["mult"])
            if mn is not None:
                ok(accepts(M, mutate(name, k, mn)), f"{w}: mínimo {mn} rejeitado")
                ok(not accepts(M, mutate(name, k, mn - mult)), f"{w}: aceitou abaixo do mínimo")
            if mx is not None:
                ok(accepts(M, mutate(name, k, mx)), f"{w}: máximo {mx} rejeitado")
                ok(not accepts(M, mutate(name, k, mx + mult)), f"{w}: aceitou acima do máximo")
            ok(not accepts(M, mutate(name, k, (mn or Decimal(1)) + mult / 2)),
               f"{w}: aceitou não-múltiplo de {mult}")
            ok(not accepts(M, mutate(name, k, "abc")), f"{w}: aceitou string não numérica")
        elif t == "string":
            if p.get("enum"):
                for v in p["enum"]:
                    ok(accepts(M, mutate(name, k, v)), f"{w}: enum {v} rejeitado")
                ok(not accepts(M, mutate(name, k, "INVALIDO")), f"{w}: aceitou enum inválido")
            elif p.get("fmt") == "email":
                ok(not accepts(M, mutate(name, k, "sem-arroba")), f"{w}: aceitou e-mail inválido")
                mx = p["maxL"]
                def mail(total: int) -> str:  # e-mail sintaticamente válido com `total` caracteres
                    dom_tail = total - 64 - 1 - 63 - 1
                    return "a" * 64 + "@" + "b" * 63 + "." + "c" * dom_tail
                ok(accepts(M, mutate(name, k, mail(mx))) and len(mail(mx)) == mx, f"{w}: e-mail de {mx} caracteres rejeitado")
                ok(len(mail(mx + 1)) == mx + 1 and not accepts(M, mutate(name, k, mail(mx + 1))), f"{w}: aceitou e-mail > {mx}")
            elif p.get("fmt") == "date":
                ok(not accepts(M, mutate(name, k, "30/10/2026")), f"{w}: aceitou data inválida")
                ok(not accepts(M, mutate(name, k, "2026-02-30")), f"{w}: aceitou data inexistente")
            elif p.get("fmt") == "date-time":
                ok(not accepts(M, mutate(name, k, "ontem")), f"{w}: aceitou date-time inválido")
            else:
                mn, mx = p.get("minL"), p.get("maxL")
                if mn:
                    ok(accepts(M, mutate(name, k, "x" * mn if not p.get("pat") else "k" * mn)), f"{w}: minLength rejeitado")
                    if mn > 1 or not p.get("pat"):
                        ok(not accepts(M, mutate(name, k, "x" * (mn - 1))), f"{w}: aceitou < minLength")
                if mx:
                    ok(accepts(M, mutate(name, k, "k" * mx)), f"{w}: maxLength rejeitado")
                    ok(not accepts(M, mutate(name, k, "k" * (mx + 1))), f"{w}: aceitou > maxLength")
                if p.get("pat"):
                    ok(not accepts(M, mutate(name, k, "1kg")), f"{w}: aceitou fora do pattern")
                    ok(not accepts(M, mutate(name, k, "k g")), f"{w}: aceitou espaço no pattern")
                ok(not accepts(M, mutate(name, k, 123)), f"{w}: aceitou número em string")
        elif t == "boolean":
            ok(not accepts(M, mutate(name, k, "talvez")), f"{w}: aceitou booleano inválido")
        elif t == "array":
            mi = p.get("minItems")
            if mi:
                ok(not accepts(M, mutate(name, k, [])), f"{w}: aceitou lista vazia (minItems {mi})")
            else:
                ok(accepts(M, mutate(name, k, [])), f"{w}: rejeitou lista vazia")
            ok(not accepts(M, mutate(name, k, "x")), f"{w}: aceitou não-lista")
            if p["items"]["t"] == "string":
                ok(accepts(M, mutate(name, k, ["k" * 1000])), f"{w}: item 1000 rejeitado")
                ok(not accepts(M, mutate(name, k, ["k" * 1001])), f"{w}: item 1001 aceito")
        elif t == "ref":
            ok(not accepts(M, mutate(name, k, {"x": 1})), f"{w}: aceitou objeto aninhado inválido")

# ----------------------------------- 4. serialização / round-trip -----------------------------------
def find_decimals(M: type[BaseModel], dumped: Any, name: str) -> None:
    pass

for name, sp in SPEC.items():
    M = getattr(S, name)
    inst = M.model_validate_json(dumps(valid_obj(name)))
    out = inst.model_dump_json()
    parsed = json.loads(out)
    def walk(spec_name: str, data: dict, path: str) -> None:
        for k, p in SPEC[spec_name]["props"].items():
            v = data.get(k)
            if p["t"] == "number":
                ok(isinstance(v, (int, float)) and not isinstance(v, bool), f"{path}.{k}: número serializado como {type(v).__name__}")
            elif p["t"] == "ref" and isinstance(v, dict):
                walk(p["ref"], v, f"{path}.{k}")
            elif p["t"] == "array" and p["items"]["t"] == "ref":
                for el in v:
                    walk(p["items"]["ref"], el, f"{path}.{k}[]")
    walk(name, parsed, name)
    ok(M.model_validate_json(out) == inst, f"{name}: round-trip JSON difere")
    ok(set(parsed) == set(sp["props"]), f"{name}: chaves JSON serializadas {set(parsed) ^ set(sp['props'])}")

# exemplos de schema (copiados do contrato) devem validar no próprio modelo
for name in SPEC:
    M = getattr(S, name)
    ex = M.model_config.get("json_schema_extra", {}).get("example")
    ok(ex is not None, f"{name}: sem example")
    if ex is not None:
        ok(accepts(M, ex), f"{name}: example do schema não valida")

# ----------------------------------- 5. regras de segurança/contrato específicas -----------------------------------
ok(set(S.Usuario.model_fields) == {"id", "nome", "email", "perfil", "ativo"}, "Usuario expõe campos além do contrato")
for forbidden in ("senha", "senha_hash", "senhaHash", "hash"):
    for name, sp in SPEC.items():
        if name in {"CreateAdminDTO", "CreateFuncionarioDTO", "LoginDTO"} and forbidden == "senha":
            continue
        ok(forbidden not in sp["props"], f"{name} expõe '{forbidden}'")
for name in ("CreateAdminDTO", "CreateFuncionarioDTO", "LoginDTO"):
    inst = getattr(S, name).model_validate(valid_obj(name))
    ok("SenhaSecreta" not in repr(inst) and "xxxxxxxx" not in repr(inst), f"{name}: senha aparece no repr")
ok(S.AuthToken(accessToken="t", expiresInSeconds=1,
               usuario=S.Usuario(id=1, nome="ab", email="a@exemplo.com", perfil="FUNCIONARIO", ativo=True)).tokenType == "Bearer",
   "AuthToken: default tokenType")
ok("tokenType" in S.AuthToken.model_json_schema(mode="serialization")["required"], "AuthToken: tokenType não obrigatório na serialização")
ok(S.CreateIngredienteDTO.model_validate(valid_obj("CreateIngredienteDTO", True)).quantidadeMinima == Decimal(0), "default quantidadeMinima")
ok(S.CreateProdutoDTO.model_validate(valid_obj("CreateProdutoDTO", True)).ativo is True, "default ativo")
ok(S.CsvFile.__metadata__ and getattr(S.CsvFile, "__origin__", None) is str, "CsvFile: não é str anotada")  # type: ignore[attr-defined]
ok(S.VazioDTO.model_validate({}) is not None and not accepts(S.VazioDTO, {"x": 1}), "VazioDTO")
# from_attributes (ORM)
class Obj:
    id = 1; nome = "Maria"; email = "m@exemplo.com"; perfil = "FUNCIONARIO"; ativo = True; senha_hash = "$argon2..."
ok(S.Usuario.model_validate(Obj()).model_dump() == {"id": 1, "nome": "Maria", "email": "m@exemplo.com", "perfil": "FUNCIONARIO", "ativo": True},
   "from_attributes não devolveu apenas campos públicos")
# Decimal exato: sem erro de float
ok(S.UnidadeMedida.model_validate_json('{"unidadeMedida":"kg","porcaoPadrao":0.04}').porcaoPadrao == Decimal("0.04"), "0.04 não preservado como Decimal exato")

# OpenAPI do FastAPI com todos os modelos
from fastapi import FastAPI

app = FastAPI()
for name in SPEC:
    pass
js_all = {name: getattr(S, name).model_json_schema() for name in SPEC}
ok(len(js_all) == 53, "geração de JSON Schema falhou")


# ----------------------------------- 6. comparação direta com o OpenAPI -----------------------------------
ALLOWED_PROP_KEYS = {"type", "format", "description", "example", "minimum", "maximum", "multipleOf",
                     "minLength", "maxLength", "pattern", "enum", "default", "nullable", "items",
                     "minItems", "$ref"}


def _num(x: Any) -> Decimal:
    return Decimal(str(x))


def norm_prop(op: dict, w: str) -> dict:
    """Normaliza uma propriedade OpenAPI para o formato de SPEC."""
    extra = set(op) - ALLOWED_PROP_KEYS
    ok(not extra, f"{w}: chaves OpenAPI não cobertas pelo verificador: {extra}")
    if "$ref" in op:
        return {"t": "ref", "ref": op["$ref"].rsplit("/", 1)[-1], "null": bool(op.get("nullable"))}
    t = op["type"]
    d: dict[str, Any] = {"t": t, "null": bool(op.get("nullable", False))}
    if t == "array":
        d["items"] = norm_prop(op["items"], w + "[]")
        if "minItems" in op:
            d["minItems"] = op["minItems"]
    elif t == "string":
        for src, dst in (("minLength", "minL"), ("maxLength", "maxL"), ("format", "fmt"),
                         ("enum", "enum"), ("pattern", "pat"), ("default", "default")):
            if src in op:
                d[dst] = op[src]
    elif t == "number":
        for src, dst in (("minimum", "min"), ("maximum", "max"), ("multipleOf", "mult")):
            if src in op:
                d[dst] = _num(op[src])
        if "default" in op:
            d["default"] = _num(op["default"])
    elif t == "integer":
        for src, dst in (("minimum", "min"), ("maximum", "max"), ("format", "fmt")):
            if src in op:
                d[dst] = op[src]
    elif t == "boolean":
        if "default" in op:
            d["default"] = op["default"]
    return d


def norm_spec(p: dict) -> dict:
    d = dict(p)
    for k in ("min", "max", "mult"):
        if k in d and p["t"] == "number":
            d[k] = _num(d[k])
    if p["t"] == "number" and "default" in d:
        d["default"] = _num(d["default"])
    if p["t"] == "array":
        d["items"] = norm_spec(p["items"])
    return d


def _canon(x: Any) -> Any:
    return json.loads(dumps(x))


def compare_openapi(doc: dict) -> None:
    comp = doc["components"]["schemas"]
    ok(len(comp) == 54, f"OpenAPI possui {len(comp)} schemas (esperado 54)")
    ok(set(comp) == EXPECTED_54, f"nomes divergentes (OpenAPI x SPEC): {set(comp) ^ EXPECTED_54}")
    csv = comp.get(CSV, {})
    ok(csv.get("type") == "string" and csv.get("format") == "binary", "CsvFile: esperado string/binary")
    csv_field = next((m for m in getattr(S.CsvFile, "__metadata__", ())), None)
    ok(csv_field is not None and csv_field.description == csv.get("description"), "CsvFile: descrição difere")
    ok(csv_field is not None and (csv_field.json_schema_extra or {}).get("format") == "binary", "CsvFile: format binary")
    for name, osch in comp.items():
        if name == CSV:
            continue
        sp = SPEC.get(name)
        ok(sp is not None, f"{name}: ausente em SPEC")
        if sp is None:
            continue
        M = getattr(S, name)
        ok(osch.get("type") == "object", f"{name}: type != object")
        ok(osch.get("additionalProperties") is False, f"{name}: additionalProperties != false (OpenAPI)")
        ok(set(osch.get("required", [])) == set(sp["req"]), f"{name}: required OpenAPI x SPEC")
        ok(set(osch.get("properties", {})) == set(sp["props"]), f"{name}: propriedades OpenAPI x SPEC")
        ok(osch.get("description", "").strip() == (M.__doc__ or "").strip(), f"{name}: descrição do schema difere")
        ok(_canon(osch.get("example")) == _canon(M.model_config.get("json_schema_extra", {}).get("example")),
           f"{name}: example do schema difere")
        for pn, op in osch.get("properties", {}).items():
            w = f"{name}.{pn}"
            got = norm_prop(op, w)
            exp = norm_spec(sp["props"].get(pn, {}))
            ok(got == exp, f"{w}: OpenAPI {got} != transcrição {exp}")
            f = M.model_fields.get(pn)
            if f is None:
                continue
            ok((op.get("description") or None) == (f.description or None), f"{w}: descrição difere")
            if "example" in op:
                ex = f.examples[0] if f.examples else None
                ok(_canon(op["example"]) == _canon(ex), f"{w}: example {op['example']!r} != {ex!r}")
            else:
                ok(not f.examples, f"{w}: example no modelo mas não no OpenAPI")


def build_synthetic_openapi() -> dict:
    """Gera um 'OpenAPI' a partir de SPEC + modelos, só para autoteste do comparador."""
    def to_op(p: dict, desc: str | None, ex: Any) -> dict:
        if p["t"] == "ref":
            o: dict[str, Any] = {"$ref": f"#/components/schemas/{p['ref']}"}
        elif p["t"] == "array":
            o = {"type": "array", "items": to_op(p["items"], None, None)}
            if "minItems" in p:
                o["minItems"] = p["minItems"]
        else:
            o = {"type": p["t"]}
            for src, dst in (("minL", "minLength"), ("maxL", "maxLength"), ("fmt", "format"),
                             ("enum", "enum"), ("pat", "pattern"), ("default", "default"),
                             ("min", "minimum"), ("max", "maximum"), ("mult", "multipleOf")):
                if src in p:
                    v = p[src]
                    o[dst] = float(v) if isinstance(v, str) and src in ("min", "max", "mult") else v
        if p.get("null"):
            o["nullable"] = True
        if desc:
            o["description"] = desc
        if ex is not None:
            o["example"] = ex
        return o
    comp: dict[str, Any] = {}
    for name, sp in SPEC.items():
        M = getattr(S, name)
        props = {}
        for pn, p in sp["props"].items():
            f = M.model_fields[pn]
            props[pn] = to_op(p, f.description, f.examples[0] if f.examples else None)
        comp[name] = {"type": "object", "description": (M.__doc__ or "").strip(), "properties": props,
                      "additionalProperties": False, "required": list(sp["req"]),
                      "example": M.model_config.get("json_schema_extra", {}).get("example")}
    csvf = next(iter(S.CsvFile.__metadata__))
    comp[CSV] = {"type": "string", "format": "binary", "description": csvf.description}
    return {"components": {"schemas": comp}}


# autoteste do comparador (sempre executa)
_before = len(failures)
compare_openapi(json.loads(dumps(build_synthetic_openapi())))
ok(len(failures) == _before, f"autoteste do comparador falhou: {failures[_before:_before + 5]}")
# o comparador deve DETECTAR divergências (mutação proposital)
_bad = json.loads(dumps(build_synthetic_openapi()))
_bad["components"]["schemas"]["Cliente"]["properties"]["nome"]["maxLength"] = 151
_n = len(failures)
compare_openapi(_bad)
_detected = len(failures) > _n
del failures[_n:]
ok(_detected, "comparador não detectou divergência proposital")

if "--openapi" in sys.argv:
    _path = sys.argv[sys.argv.index("--openapi") + 1]
    with open(_path, encoding="utf-8") as _fh:
        _doc = json.load(_fh)
    compare_openapi(_doc)
    print(f"comparação direta com {_path}: executada")

print(f"schemas no contrato (transcritos): {len(EXPECTED_54)} | verificações executadas: {checks}")
if failures:
    print(f"FALHAS: {len(failures)}")
    for f in failures[:80]:
        print(" -", f)
    sys.exit(1)
print("OK — todas as verificações passaram")
