"""Blocos compartilhados pelos routers (Fase 5 — P5-64, P5-67).

Reúne o que toda rota precisa declarar igual ao contrato:

- **`respostas(...)`** monta o dicionário `responses` da operação a partir dos
  `components.responses` do OpenAPI. Não é cosmético: o handler de erro da Fase 4 decide
  entre `400`, `404` e `422` lendo **exatamente** o que a rota declara, então declarar a
  menos (ou a mais) muda a resposta da API.
- **Parâmetros compartilhados** (`page`, `size`, `sort`, `q`) com os mesmos limites,
  padrões e descrições de `components.parameters`.
- **`location`** preenche o cabeçalho `Location` das operações que declaram `201`.

Os routers cuidam só de HTTP: validam entrada via schema, chamam o service e devolvem a
resposta. Regra de negócio nenhuma mora aqui.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Path, Query, Response

from ..schemas import ApiError

# Descrições idênticas às de `components.responses` do contrato.
DESCRICOES: dict[int, str] = {
    400: "Requisição malformada ou parâmetros incompatíveis.",
    401: "Autenticação ausente, inválida ou expirada.",
    403: "Usuário autenticado sem permissão para a operação.",
    404: "Recurso não encontrado.",
    409: "Conflito com o estado atual ou restrição de integridade referencial.",
    422: "Os dados foram compreendidos, mas violam uma regra de validação.",
    500: "Erro interno inesperado.",
    503: "Serviço de otimização ou dependência temporariamente indisponível.",
}


def respostas(*codigos: int) -> dict[int | str, dict[str, Any]]:
    """`responses` da operação: um `ApiError` por status de erro declarado no contrato."""
    return {
        codigo: {"model": ApiError, "description": DESCRICOES[codigo]} for codigo in codigos
    }


def resposta_criado(descricao: str, exemplo: str) -> dict[str, Any]:
    """Bloco do `201` com o cabeçalho `Location`, como o contrato declara."""
    return {
        "description": descricao,
        "headers": {
            "Location": {
                "description": "URI do recurso criado.",
                "schema": {"type": "string", "example": exemplo},
            }
        },
    }


def location(response: Response, caminho: str) -> None:
    """Preenche o cabeçalho `Location` da resposta `201`."""
    response.headers["Location"] = caminho


# ---------------------------------------------------------------------------
# Parâmetros compartilhados (components.parameters)
# ---------------------------------------------------------------------------

PageQuery = Annotated[
    int, Query(ge=0, description="Índice da página, começando em zero.", examples=[0])
]
SizeQuery = Annotated[
    int,
    Query(ge=1, le=100, description="Quantidade de itens por página (máximo 100).", examples=[20]),
]
SortQuery = Annotated[
    str | None,
    Query(
        description="Ordenação no formato campo,direção. Campos aceitos dependem do recurso.",
        examples=["nome,asc"],
    ),
]
BuscaQuery = Annotated[
    str | None,
    Query(
        max_length=100,
        description="Busca textual por nome ou campos de identificação do recurso.",
    ),
]
IdPath = Annotated[int, Path(ge=1, description="Identificador inteiro do recurso.")]
UnidadePath = Annotated[
    str, Path(min_length=1, max_length=20, description="Código da unidade de medida.")
]
