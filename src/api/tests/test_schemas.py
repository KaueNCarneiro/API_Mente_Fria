"""Cobertura dos 54 schemas do contrato (Fase 6 — P6-17).

Cada schema de `components.schemas` é verificado individualmente (teste parametrizado):
existe como modelo Pydantic com o mesmo nome, tem exatamente os campos declarados, os
mesmos obrigatórios e `additionalProperties: false` quando o contrato assim define.

A verificação profunda de limites, enums, formatos e exemplos continua em
`verify_schemas.py`, executado aqui como um teste: são 5 976 conferências contra o
arquivo do contrato, e reescrevê-las à mão só multiplicaria a chance de erro.
"""

from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.api import schemas

RAIZ = Path(__file__).resolve().parents[3]


def _modelos_do_contrato(contrato: dict[str, Any]) -> list[str]:
    return sorted(contrato["components"]["schemas"])


def test_contrato_tem_54_schemas(contrato: dict[str, Any]) -> None:
    assert len(contrato["components"]["schemas"]) == 54


def test_todos_os_schemas_existem_em_schemas_py(contrato: dict[str, Any]) -> None:
    faltando = [nome for nome in _modelos_do_contrato(contrato) if not hasattr(schemas, nome)]
    assert faltando == []


@pytest.mark.parametrize(
    "nome",
    sorted(
        __import__("json")
        .loads((RAIZ / "Mente Fria API.openapi.json").read_text(encoding="utf-8"))["components"][
            "schemas"
        ]
    ),
)
def test_schema_espelha_o_contrato(nome: str, contrato: dict[str, Any]) -> None:
    """Campos, obrigatoriedade e objeto fechado de cada um dos 54 schemas."""
    definicao = contrato["components"]["schemas"][nome]
    modelo = getattr(schemas, nome)

    if definicao.get("type") == "string":  # CsvFile é texto, não objeto
        assert not isinstance(modelo, type) or not issubclass(modelo, BaseModel)
        return

    assert issubclass(modelo, BaseModel), nome

    propriedades = set(definicao.get("properties", {}))
    assert set(modelo.model_fields) == propriedades, nome

    obrigatorios_contrato = set(definicao.get("required", []))
    obrigatorios_modelo = {
        campo for campo, info in modelo.model_fields.items() if info.is_required()
    }
    # `tokenType` tem default no servidor mas é obrigatório na serialização (decisão P2).
    assert obrigatorios_contrato - obrigatorios_modelo <= {"tokenType"}, nome
    assert obrigatorios_modelo <= obrigatorios_contrato, nome

    if definicao.get("additionalProperties") is False:
        assert modelo.model_config.get("extra") == "forbid", nome


@pytest.mark.parametrize(
    "nome",
    sorted(
        __import__("json")
        .loads((RAIZ / "Mente Fria API.openapi.json").read_text(encoding="utf-8"))["components"][
            "schemas"
        ]
    ),
)
def test_exemplo_do_contrato_valida_no_modelo(nome: str, contrato: dict[str, Any]) -> None:
    """Quando o contrato traz `example`, ele precisa ser aceito pelo modelo."""
    definicao = contrato["components"]["schemas"][nome]
    exemplo = definicao.get("example")
    modelo = getattr(schemas, nome)
    if exemplo is None or not isinstance(exemplo, dict) or not isinstance(modelo, type):
        pytest.skip(f"{nome} não declara exemplo de objeto")
    if not issubclass(modelo, BaseModel):
        pytest.skip(f"{nome} não é objeto")
    modelo.model_validate(exemplo)


# --- objeto fechado, aliases e limites -------------------------------------------------------


@pytest.mark.parametrize(
    "nome",
    ["CreateAdminDTO", "LoginDTO", "CreateClienteDTO", "CreateProdutoDTO", "CreateReposicaoDTO"],
)
def test_campo_desconhecido_e_recusado(nome: str) -> None:
    modelo = getattr(schemas, nome)
    with pytest.raises(ValidationError):
        modelo.model_validate({"campoInexistente": 1})


def test_nomes_json_do_contrato_sao_preservados() -> None:
    """Nada de `snake_case` vazando para o JSON."""
    token = schemas.AuthToken(
        accessToken="t",
        tokenType="Bearer",
        expiresInSeconds=3600,
        usuario=schemas.Usuario(
            id=1, nome="Ana", email="ana@mentefria.com", perfil="FUNCIONARIO", ativo=True
        ),
    )
    assert set(token.model_dump()) == {"accessToken", "tokenType", "expiresInSeconds", "usuario"}


@pytest.mark.parametrize(
    ("modelo", "campo", "valor"),
    [
        (schemas.PageMetadata, "page", -1),
        (schemas.PageMetadata, "size", 101),
        (schemas.CreateReposicaoDTO, "periodoDias", 366),
        (schemas.PedidoItemDTO, "quantidade", 10_001),
        (schemas.ComposicaoProdutoItemDTO, "quantidadeUtilizada", Decimal(0)),
    ],
)
def test_limites_numericos(modelo: type[BaseModel], campo: str, valor: Any) -> None:
    base: dict[str, Any] = {
        schemas.PageMetadata: {"page": 0, "size": 20, "totalElements": 0, "totalPages": 0},
        schemas.CreateReposicaoDTO: {"periodoDias": 7, "orcamento": Decimal(10)},
        schemas.PedidoItemDTO: {"produtoId": 1, "quantidade": 1},
        schemas.ComposicaoProdutoItemDTO: {"ingredienteId": 1, "quantidadeUtilizada": Decimal(1)},
    }[modelo]
    with pytest.raises(ValidationError):
        modelo.model_validate({**base, campo: valor})


@pytest.mark.parametrize(
    ("modelo", "campo", "invalido", "base"),
    [
        (
            schemas.CreateMovimentacaoEstoqueDTO,
            "tipo",
            "TRANSFERENCIA",
            {"ingredienteId": 1, "tipo": "ENTRADA", "quantidade": Decimal(1)},
        ),
        (
            schemas.CreateMovimentacaoEstoqueDTO,
            "motivo",
            "PERDA",
            {"ingredienteId": 1, "tipo": "SAIDA", "quantidade": Decimal(1)},
        ),
        (schemas.HealthStatus, "status", "quebrado", {"status": "ok", "banco": "ok"}),
        (schemas.HealthStatus, "banco", "talvez", {"status": "ok", "banco": "ok"}),
    ],
)
def test_enums_do_contrato(
    modelo: type[BaseModel], campo: str, invalido: str, base: dict[str, Any]
) -> None:
    modelo.model_validate(base)
    with pytest.raises(ValidationError):
        modelo.model_validate({**base, campo: invalido})


def test_api_error_exige_os_campos_do_contrato() -> None:
    with pytest.raises(ValidationError):
        schemas.ApiError.model_validate({"codigo": "X", "mensagem": "Y"})


def test_usuario_nunca_aceita_senha() -> None:
    with pytest.raises(ValidationError):
        schemas.Usuario.model_validate(
            {
                "id": 1,
                "nome": "Ana",
                "email": "ana@mentefria.com",
                "perfil": "FUNCIONARIO",
                "ativo": True,
                "senha": "x",
            }
        )


# --- verificação profunda contra o arquivo do contrato ------------------------------------------


@pytest.mark.slow
def test_verificador_de_schemas_contra_o_contrato() -> None:
    """Executa `verify_schemas.py --openapi`: limites, enums, formatos e exemplos."""
    # PYTHONIOENCODING: sem isso a saída do subprocesso sai na codepage do console do
    # Windows e os acentos chegam corrompidos aqui.
    ambiente = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    resultado = subprocess.run(
        [
            sys.executable,
            str(RAIZ / "verify_schemas.py"),
            "--openapi",
            str(RAIZ / "Mente Fria API.openapi.json"),
        ],
        check=False,
        cwd=RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ambiente,
        timeout=600,
    )
    assert resultado.returncode == 0, resultado.stdout[-3000:] + resultado.stderr[-2000:]
    assert "todas as verificações passaram" in resultado.stdout
    assert "5976" in resultado.stdout.replace(" ", "")
