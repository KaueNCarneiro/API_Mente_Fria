"""Testes de `GET /api/v1/saude` (Fase 6 — P6-04)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from src.api.services import saude as servico


def test_saude_e_publica_e_responde_ok(client: TestClient) -> None:
    resposta = client.get("/api/v1/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "banco": "ok"}


def test_saude_nao_exige_token(client: TestClient) -> None:
    """A operação é pública no contrato: cabeçalho ausente não pode virar 401."""
    assert client.get("/api/v1/saude").status_code == 200


def test_saude_ignora_token_invalido(client: TestClient) -> None:
    resposta = client.get("/api/v1/saude", headers={"Authorization": "Bearer invalido"})
    assert resposta.status_code == 200


def test_banco_indisponivel_e_reportado_como_degradado(db, monkeypatch) -> None:
    """Falha do banco não derruba a aplicação: `status=degradado`, `banco=indisponivel`."""

    def _falhar(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, Exception("banco fora do ar"))

    monkeypatch.setattr(db, "execute", _falhar)
    estado = servico.verificar(db)
    assert estado.status == "degradado"
    assert estado.banco == "indisponivel"


def test_saude_nao_expoe_detalhe_de_infraestrutura(client: TestClient) -> None:
    corpo = client.get("/api/v1/saude").text
    assert "sqlite" not in corpo.lower()
    assert "Traceback" not in corpo
