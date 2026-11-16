"""Schemas Pydantic v2 derivados de ``components.schemas`` do OpenAPI (Fase 2).

Nomes de campos em camelCase preservam EXATAMENTE o contrato JSON.

Fonte da verdade: ``Mente Fria API.openapi.json`` (54 schemas). Este módulo NÃO
introduz campos, enums, validações ou regras de negócio fora do contrato.

Convenções:
- Nomes de schemas e de campos JSON preservados literalmente (sem aliases).
- ``additionalProperties: false`` -> ``extra="forbid"``; ``from_attributes=True``
  permite construir respostas a partir de objetos ORM (Fase 3 em diante).
- ``type: number`` -> ``Decimal`` (STYLEGUIDE §3.2) com ``ge/le/multiple_of`` do
  contrato; na serialização JSON o valor sai como número (não como string).
- Enums inline do contrato -> ``Literal`` (não cria schemas extras).
- Campo opcional NÃO ``nullable`` (ex.: ``UpdateUsuarioDTO``) aceita ausência, mas
  rejeita ``null``; campo ``nullable`` aceita ``None``.
- ``senha`` nunca é exibida em ``repr`` e nenhum schema de resposta contém
  senha ou hash de senha.
- ``CsvFile`` não é objeto JSON: é um alias de ``str`` (``format: binary``,
  ``text/csv``).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer

__all__ = [
    "AlertaReposicao",
    "AlertaValidade",
    "ApiError",
    "ApiErrorDetail",
    "AuthToken",
    "CancelamentoPedidoDTO",
    "Cliente",
    "ComposicaoProduto",
    "ComposicaoProdutoItem",
    "ComposicaoProdutoItemDTO",
    "CreateAdminDTO",
    "CreateClienteDTO",
    "CreateFuncionarioDTO",
    "CreateIngredienteDTO",
    "CreateMovimentacaoEstoqueDTO",
    "CreatePedidoDTO",
    "CreateProdutoDTO",
    "CreateReposicaoDTO",
    "CreateUnidadeMedidaDTO",
    "CsvFile",
    "Dashboard",
    "HealthStatus",
    "Ingrediente",
    "ListaAlertasReposicao",
    "ListaAlertasValidade",
    "LoginDTO",
    "MovimentacaoEstoque",
    "PageMetadata",
    "PaginatedClientes",
    "PaginatedIngredientes",
    "PaginatedMovimentacoesEstoque",
    "PaginatedPedidos",
    "PaginatedProdutos",
    "PaginatedUnidadesMedida",
    "PaginatedUsuarios",
    "Pedido",
    "PedidoItem",
    "PedidoItemDTO",
    "ProducaoRecomendacao",
    "ProducaoRecomendacaoItem",
    "Produto",
    "ProdutoMaisVendido",
    "ReposicaoRecomendacao",
    "ReposicaoRecomendacaoItem",
    "SubstituirComposicaoDTO",
    "SugestaoMarketing",
    "UnidadeMedida",
    "UpdateClienteDTO",
    "UpdateIngredienteDTO",
    "UpdateProdutoDTO",
    "UpdateUnidadeMedidaDTO",
    "UpdateUsuarioDTO",
    "Usuario",
    "VazioDTO",
]

# ---------------------------------------------------------------------------
# Tipos reutilizáveis (derivados dos limites do contrato)
# ---------------------------------------------------------------------------

# `format: int32`, `minimum: 1` — identificadores de recursos.
INT32_MAX = 2_147_483_647
Id = Annotated[int, Field(ge=1, le=INT32_MAX)]

# Perfis e enums inline do contrato (Literal: não geram schemas adicionais).
Perfil = Literal["ADMINISTRADOR", "FUNCIONARIO"]
TipoMovimentacao = Literal["ENTRADA", "SAIDA"]
MotivoSaidaManual = Literal["CONVENCIONAL", "DESCARTE_VENCIDO"]
MotivoMovimentacao = Literal["PEDIDO", "CONVENCIONAL", "DESCARTE_VENCIDO"]
StatusPedido = Literal["ATIVO", "CANCELADO"]

Email = Annotated[EmailStr, Field(max_length=150)]

# `type: number` -> Decimal serializado como número JSON.
_AS_JSON_NUMBER = PlainSerializer(float, return_type=float, when_used="json")


def _num(
    *,
    ge: str,
    multiple_of: str,
    le: str | None = None,
) -> object:
    """Decimal limitado (``minimum``/``maximum``/``multipleOf``) serializado como número."""
    constraints: dict[str, Decimal] = {"ge": Decimal(ge), "multiple_of": Decimal(multiple_of)}
    if le is not None:
        constraints["le"] = Decimal(le)
    return Annotated[Decimal, Field(**constraints), _AS_JSON_NUMBER]


# Quantidades (multipleOf 0.001)
Qtd3Pos = _num(ge="0.001", le="9999999.999", multiple_of="0.001")  # >0, com máximo
Qtd3PosSemMax = _num(ge="0.001", multiple_of="0.001")  # >0, sem máximo (respostas)
Qtd3NaoNeg = _num(ge="0", le="9999999.999", multiple_of="0.001")  # >=0, com máximo
Qtd3NaoNegSemMax = _num(ge="0", multiple_of="0.001")  # >=0, sem máximo (respostas)

# Valores monetários em reais (multipleOf 0.01)
ReaisNaoNegMax = _num(ge="0", le="99999999.99", multiple_of="0.01")
ReaisPosMax = _num(ge="0.01", le="99999999.99", multiple_of="0.01")
ReaisNaoNeg = _num(ge="0", multiple_of="0.01")
ReaisPos = _num(ge="0.01", multiple_of="0.01")


class _ContractModel(BaseModel):
    """Base: ``additionalProperties: false`` e leitura de atributos (ORM)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


def _example(value: dict[str, object]) -> ConfigDict:
    """Exemplo do schema (OpenAPI ``example``) exposto em ``json_schema_extra``."""
    return ConfigDict(json_schema_extra={"example": value})


# ---------------------------------------------------------------------------
# Erros e paginação compartilhados
# ---------------------------------------------------------------------------


class ApiErrorDetail(_ContractModel):
    """Detalhe de validação associado a um campo da requisição."""

    model_config = _example(
        {"campo": "precoVenda", "mensagem": "Deve ser maior que zero.", "valorRejeitado": "0.00"}
    )

    campo: str = Field(
        max_length=100,
        description="Nome do campo que apresentou problema.",
        examples=["precoVenda"],
    )
    mensagem: str = Field(
        max_length=500,
        description="Explicação objetiva da falha de validação.",
        examples=["Deve ser maior que zero."],
    )
    valorRejeitado: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Representação textual do valor inválido, quando seguro e útil para diagnóstico."
        ),
        examples=["0.00"],
    )


class ApiError(_ContractModel):
    """Formato uniforme para erros da API. Não deve expor stack trace, SQL, hash de senha ou dados internos."""

    model_config = _example(
        {
            "codigo": "VALIDATION_ERROR",
            "mensagem": "A requisição contém dados inválidos.",
            "detalhes": [
                {
                    "campo": "precoVenda",
                    "mensagem": "Deve ser maior que zero.",
                    "valorRejeitado": "0.00",
                }
            ],
            "timestamp": "2026-10-30T16:30:00-03:00",
            "caminho": "/api/v1/produtos",
            "correlationId": "7c8b4fb3-9da1-4baf-9f7d-3f2f0b7a0d2a",
        }
    )

    codigo: str = Field(
        max_length=80,
        description="Código estável e legível por máquina para classificar o erro.",
        examples=["VALIDATION_ERROR"],
    )
    mensagem: str = Field(
        max_length=500,
        description="Mensagem resumida e adequada ao consumidor da API.",
        examples=["A requisição contém dados inválidos."],
    )
    detalhes: list[ApiErrorDetail] = Field(
        description="Lista de erros de validação específicos; pode ser vazia.",
        examples=[
            [
                {
                    "campo": "precoVenda",
                    "mensagem": "Deve ser maior que zero.",
                    "valorRejeitado": "0.00",
                }
            ]
        ],
    )
    timestamp: datetime = Field(
        description="Instante em que o erro foi produzido, em ISO 8601.",
        examples=["2026-10-30T16:30:00-03:00"],
    )
    caminho: str = Field(
        max_length=300,
        description="Caminho da requisição que originou o erro.",
        examples=["/api/v1/produtos"],
    )
    correlationId: str | None = Field(
        default=None,
        max_length=100,
        description="Identificador de correlação para rastreamento nos logs.",
        examples=["7c8b4fb3-9da1-4baf-9f7d-3f2f0b7a0d2a"],
    )


class PageMetadata(_ContractModel):
    """Metadados da paginação. page é baseado em zero."""

    model_config = _example({"page": 0, "size": 20, "totalElements": 42, "totalPages": 3})

    page: int = Field(
        ge=0, description="Índice da página retornada, começando em zero.", examples=[0]
    )
    size: int = Field(
        ge=1, le=100, description="Quantidade máxima de itens por página.", examples=[20]
    )
    totalElements: int = Field(
        ge=0,
        description="Quantidade total de registros compatíveis com os filtros.",
        examples=[42],
    )
    totalPages: int = Field(ge=0, description="Quantidade total de páginas.", examples=[3])


# ---------------------------------------------------------------------------
# Autenticação e usuários
# ---------------------------------------------------------------------------


class CreateAdminDTO(_ContractModel):
    """Dados para criar a primeira conta Administrador. A operação deve ser recusada se já existir um Administrador inicial."""

    model_config = _example(
        {
            "nome": "Mariana Oliveira",
            "email": "mariana.oliveira@exemplo.com",
            "senha": "SenhaForte#2026",
        }
    )

    nome: str = Field(
        min_length=2,
        max_length=150,
        description="Nome de exibição do Administrador.",
        examples=["Mariana Oliveira"],
    )
    email: Email = Field(
        description="E-mail único utilizado no login.", examples=["mariana.oliveira@exemplo.com"]
    )
    senha: str = Field(
        min_length=8,
        max_length=128,
        repr=False,
        description=(
            "Senha em texto claro enviada somente por HTTPS; o backend deve armazenar apenas "
            "hash seguro. Mínimo de 8 caracteres."
        ),
        examples=["SenhaForte#2026"],
    )


class CreateFuncionarioDTO(_ContractModel):
    """Dados para cadastrar um Funcionário. O perfil é definido pelo servidor como FUNCIONARIO."""

    model_config = _example(
        {
            "nome": "Rafael Santos",
            "email": "rafael.santos@exemplo.com",
            "senha": "AcessoInicial#2026",
        }
    )

    nome: str = Field(
        min_length=2,
        max_length=150,
        description="Nome de exibição do funcionário.",
        examples=["Rafael Santos"],
    )
    email: Email = Field(
        description="E-mail único utilizado no login.", examples=["rafael.santos@exemplo.com"]
    )
    senha: str = Field(
        min_length=8,
        max_length=128,
        repr=False,
        description="Senha inicial enviada somente por HTTPS; armazenar apenas hash seguro.",
        examples=["AcessoInicial#2026"],
    )


class UpdateUsuarioDTO(_ContractModel):
    """Atualização parcial dos dados editáveis do usuário. O perfil não pode ser alterado por esta operação."""

    model_config = _example(
        {"nome": "Rafael Santos", "email": "rafael.novo@exemplo.com", "ativo": True}
    )

    # Campos opcionais e NÃO nullable: ausência é permitida, ``null`` é rejeitado.
    nome: str = Field(  # type: ignore[assignment]
        default=None,
        min_length=2,
        max_length=150,
        description="Novo nome de exibição.",
        examples=["Rafael Santos"],
    )
    email: Email = Field(  # type: ignore[assignment]
        default=None,
        description="Novo e-mail único de login.",
        examples=["rafael.novo@exemplo.com"],
    )
    ativo: bool = Field(  # type: ignore[assignment]
        default=None,
        description="Indica se o usuário pode autenticar e utilizar o sistema.",
        examples=[True],
    )


class Usuario(_ContractModel):
    """Representação pública do usuário. senha e senha_hash nunca são retornados."""

    model_config = _example(
        {
            "id": 12,
            "nome": "Rafael Santos",
            "email": "rafael.santos@exemplo.com",
            "perfil": "FUNCIONARIO",
            "ativo": True,
        }
    )

    id: Id = Field(description="Identificador único do usuário.", examples=[12])
    nome: str = Field(max_length=150, description="Nome de exibição.", examples=["Rafael Santos"])
    email: Email = Field(
        description="E-mail de login, único no sistema.", examples=["rafael.santos@exemplo.com"]
    )
    perfil: Perfil = Field(
        description="Papel de autorização do usuário.", examples=["FUNCIONARIO"]
    )
    ativo: bool = Field(description="Indica se a conta está ativa.", examples=[True])


class LoginDTO(_ContractModel):
    """Credenciais para autenticação. A API nunca deve registrar a senha em logs."""

    model_config = _example(
        {"email": "rafael.santos@exemplo.com", "senha": "AcessoInicial#2026"}
    )

    email: Email = Field(description="E-mail cadastrado.", examples=["rafael.santos@exemplo.com"])
    senha: str = Field(
        min_length=8,
        max_length=128,
        repr=False,
        description="Senha em texto claro recebida por HTTPS.",
        examples=["AcessoInicial#2026"],
    )


class AuthToken(_ContractModel):
    """Resultado da autenticação. O token é enviado no cabeçalho Authorization como Bearer."""

    # `tokenType` é obrigatório no contrato E possui default "Bearer": o default é
    # mantido para construção no servidor, e o schema de serialização o marca como
    # obrigatório.
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True,
        json_schema_extra={
            "example": {
                "accessToken": "eyJhbGciOiJIUzI1NiJ9.mock.signature",
                "tokenType": "Bearer",
                "expiresInSeconds": 3600,
                "usuario": {
                    "id": 12,
                    "nome": "Rafael Santos",
                    "email": "rafael.santos@exemplo.com",
                    "perfil": "FUNCIONARIO",
                    "ativo": True,
                },
            }
        },
    )

    accessToken: str = Field(
        description="Token de acesso assinado.", examples=["eyJhbGciOiJIUzI1NiJ9.mock.signature"]
    )
    tokenType: Literal["Bearer"] = Field(
        default="Bearer", description="Esquema de autenticação utilizado.", examples=["Bearer"]
    )
    expiresInSeconds: int = Field(
        ge=1, description="Tempo de validade do token em segundos.", examples=[3600]
    )
    usuario: Usuario = Field(description="Dados públicos do usuário autenticado.")


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------


class CreateClienteDTO(_ContractModel):
    """Dados necessários para cadastrar um cliente."""

    model_config = _example(
        {
            "nome": "Ana Clara Souza",
            "contato": "(16) 99999-1234",
            "endereco": "Rua das Acácias, 120 - Ribeirão Preto/SP",
        }
    )

    nome: str = Field(
        min_length=2, max_length=150, description="Nome do cliente.", examples=["Ana Clara Souza"]
    )
    contato: str = Field(
        min_length=3,
        max_length=50,
        description="Telefone ou outro meio de contato informado pelo cliente.",
        examples=["(16) 99999-1234"],
    )
    endereco: str = Field(
        min_length=3,
        max_length=255,
        description="Endereço do cliente.",
        examples=["Rua das Acácias, 120 - Ribeirão Preto/SP"],
    )


class UpdateClienteDTO(_ContractModel):
    """Substituição dos dados cadastrais do cliente."""

    model_config = _example(
        {
            "nome": "Ana Clara Souza",
            "contato": "(16) 98888-1234",
            "endereco": "Av. Independência, 500 - Ribeirão Preto/SP",
        }
    )

    nome: str = Field(
        min_length=2, max_length=150, description="Nome atualizado.", examples=["Ana Clara Souza"]
    )
    contato: str = Field(
        min_length=3,
        max_length=50,
        description="Telefone ou meio de contato atualizado.",
        examples=["(16) 98888-1234"],
    )
    endereco: str = Field(
        min_length=3,
        max_length=255,
        description="Endereço atualizado.",
        examples=["Av. Independência, 500 - Ribeirão Preto/SP"],
    )


class Cliente(_ContractModel):
    """Representação de cliente cadastrado."""

    model_config = _example(
        {
            "id": 31,
            "nome": "Ana Clara Souza",
            "contato": "(16) 99999-1234",
            "endereco": "Rua das Acácias, 120 - Ribeirão Preto/SP",
        }
    )

    id: Id = Field(description="Identificador único do cliente.", examples=[31])
    nome: str = Field(max_length=150, description="Nome do cliente.", examples=["Ana Clara Souza"])
    contato: str = Field(
        max_length=50, description="Telefone ou meio de contato.", examples=["(16) 99999-1234"]
    )
    endereco: str = Field(
        max_length=255,
        description="Endereço cadastrado.",
        examples=["Rua das Acácias, 120 - Ribeirão Preto/SP"],
    )


# ---------------------------------------------------------------------------
# Unidades de medida
# ---------------------------------------------------------------------------

_UNIDADE_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_-]{0,19}$"


class UnidadeMedida(_ContractModel):
    """Porção padrão sugerida para novos ingredientes da unidade correspondente."""

    model_config = _example({"unidadeMedida": "kg", "porcaoPadrao": 0.04})

    unidadeMedida: str = Field(
        min_length=1,
        max_length=20,
        pattern=_UNIDADE_PATTERN,
        description="Código textual da unidade, utilizado também como chave primária.",
        examples=["kg"],
    )
    porcaoPadrao: Qtd3Pos = Field(  # type: ignore[valid-type]
        description=(
            "Valor sugerido no cadastro de novos ingredientes. Deve ser maior que zero; "
            "não altera ingredientes existentes."
        ),
        examples=[0.04],
    )


class CreateUnidadeMedidaDTO(_ContractModel):
    """Dados para definir uma unidade e sua sugestão de porção padrão."""

    model_config = _example({"unidadeMedida": "kg", "porcaoPadrao": 0.04})

    unidadeMedida: str = Field(
        min_length=1,
        max_length=20,
        pattern=_UNIDADE_PATTERN,
        description="Código único da unidade de medida.",
        examples=["kg"],
    )
    porcaoPadrao: Qtd3Pos = Field(  # type: ignore[valid-type]
        description="Sugestão de porção para novos ingredientes dessa unidade.",
        examples=[0.04],
    )


class UpdateUnidadeMedidaDTO(_ContractModel):
    """Atualiza a sugestão de porção padrão de uma unidade. Não altera porções de ingredientes já cadastrados."""

    model_config = _example({"porcaoPadrao": 0.05})

    porcaoPadrao: Qtd3Pos = Field(  # type: ignore[valid-type]
        description="Novo valor sugerido para novos ingredientes.", examples=[0.05]
    )


# ---------------------------------------------------------------------------
# Ingredientes
# ---------------------------------------------------------------------------


class CreateIngredienteDTO(_ContractModel):
    """Cadastro de ingrediente. O saldo de estoque não é informado aqui: deve ser criado por movimentação ENTRADA."""

    model_config = _example(
        {
            "nome": "Açaí (polpa)",
            "unidadeMedida": "kg",
            "custoUnitario": 18.5,
            "porcaoPadrao": 0.15,
            "quantidadeMinima": 10,
        }
    )

    nome: str = Field(
        min_length=2,
        max_length=100,
        description="Nome do ingrediente ou insumo.",
        examples=["Açaí (polpa)"],
    )
    unidadeMedida: str = Field(
        min_length=1,
        max_length=20,
        description="Unidade previamente cadastrada em unidade_medida_porcao_padrao.",
        examples=["kg"],
    )
    custoUnitario: ReaisNaoNegMax = Field(  # type: ignore[valid-type]
        description="Custo por unidade de medida, em reais. Aceita zero ou valor positivo.",
        examples=[18.5],
    )
    porcaoPadrao: Qtd3Pos = Field(  # type: ignore[valid-type]
        description=(
            "Porção efetiva deste ingrediente usada nos cálculos e composição. "
            "Deve ser maior que zero."
        ),
        examples=[0.15],
    )
    quantidadeMinima: Qtd3NaoNeg = Field(  # type: ignore[valid-type]
        default=Decimal(0),
        description="Limite de estoque que dispara alerta de reposição.",
        examples=[10],
    )


class UpdateIngredienteDTO(_ContractModel):
    """Atualização cadastral de ingrediente. quantidadeEstoque permanece sob controle exclusivo das movimentações."""

    model_config = _example(
        {
            "nome": "Açaí (polpa)",
            "unidadeMedida": "kg",
            "custoUnitario": 19,
            "porcaoPadrao": 0.15,
            "quantidadeMinima": 12,
        }
    )

    nome: str = Field(
        min_length=2, max_length=100, description="Nome atualizado.", examples=["Açaí (polpa)"]
    )
    unidadeMedida: str = Field(
        min_length=1,
        max_length=20,
        description="Unidade cadastrada previamente.",
        examples=["kg"],
    )
    custoUnitario: ReaisNaoNegMax = Field(  # type: ignore[valid-type]
        description="Custo por unidade de medida em reais.", examples=[19]
    )
    porcaoPadrao: Qtd3Pos = Field(  # type: ignore[valid-type]
        description="Porção efetiva individual para cálculos.", examples=[0.15]
    )
    quantidadeMinima: Qtd3NaoNeg = Field(  # type: ignore[valid-type]
        description="Limite de estoque que dispara alerta.", examples=[12]
    )


class Ingrediente(_ContractModel):
    """Representação completa do ingrediente, incluindo saldo atual calculado pelas entradas ainda disponíveis."""

    model_config = _example(
        {
            "id": 1,
            "nome": "Açaí (polpa)",
            "unidadeMedida": "kg",
            "custoUnitario": 18.5,
            "porcaoPadrao": 0.15,
            "quantidadeEstoque": 40,
            "quantidadeMinima": 10,
            "precisaReposicao": False,
        }
    )

    id: Id = Field(description="Identificador único do ingrediente.", examples=[1])
    nome: str = Field(max_length=100, description="Nome do ingrediente.", examples=["Açaí (polpa)"])
    unidadeMedida: str = Field(
        max_length=20, description="Unidade de medida cadastrada.", examples=["kg"]
    )
    custoUnitario: ReaisNaoNegMax = Field(  # type: ignore[valid-type]
        description="Custo por unidade de medida em reais.", examples=[18.5]
    )
    porcaoPadrao: Qtd3PosSemMax = Field(  # type: ignore[valid-type]
        description="Porção efetiva individual usada nos cálculos.", examples=[0.15]
    )
    quantidadeEstoque: Qtd3NaoNegSemMax = Field(  # type: ignore[valid-type]
        description="Saldo total atual: soma da quantidade restante das entradas do ingrediente.",
        examples=[40],
    )
    quantidadeMinima: Qtd3NaoNegSemMax = Field(  # type: ignore[valid-type]
        description="Saldo mínimo que dispara alerta de reposição.", examples=[10]
    )
    precisaReposicao: bool = Field(
        description="Indica se o saldo válido está abaixo do limite mínimo.", examples=[False]
    )


# ---------------------------------------------------------------------------
# Produtos e composição
# ---------------------------------------------------------------------------


class ComposicaoProdutoItemDTO(_ContractModel):
    """Ingrediente e quantidade utilizada por unidade do produto."""

    model_config = _example({"ingredienteId": 1, "quantidadeUtilizada": 0.3})

    ingredienteId: Id = Field(
        description="Identificador do ingrediente que compõe o produto.", examples=[1]
    )
    quantidadeUtilizada: Qtd3Pos = Field(  # type: ignore[valid-type]
        description=(
            "Quantidade consumida do ingrediente para produzir uma unidade do produto, "
            "na unidade cadastrada."
        ),
        examples=[0.3],
    )


class ComposicaoProdutoItem(_ContractModel):
    """Item da composição de um produto com dados básicos do ingrediente."""

    model_config = _example(
        {
            "ingredienteId": 1,
            "nomeIngrediente": "Açaí (polpa)",
            "unidadeMedida": "kg",
            "quantidadeUtilizada": 0.3,
        }
    )

    ingredienteId: Id = Field(description="Identificador do ingrediente.", examples=[1])
    nomeIngrediente: str = Field(
        max_length=100, description="Nome do ingrediente.", examples=["Açaí (polpa)"]
    )
    unidadeMedida: str = Field(
        max_length=20, description="Unidade usada na quantidade da composição.", examples=["kg"]
    )
    quantidadeUtilizada: Qtd3PosSemMax = Field(  # type: ignore[valid-type]
        description="Quantidade utilizada para uma unidade do produto.", examples=[0.3]
    )


class CreateProdutoDTO(_ContractModel):
    """Cadastro de produto e sua composição de ingredientes. A composição deve conter ao menos um item; regras específicas do domínio podem exigir o ingrediente-base açaí."""

    model_config = _example(
        {
            "nome": "Açaí Tradicional 300ml",
            "precoVenda": 12.9,
            "ativo": True,
            "composicao": [
                {"ingredienteId": 1, "quantidadeUtilizada": 0.3},
                {"ingredienteId": 2, "quantidadeUtilizada": 0.03},
                {"ingredienteId": 7, "quantidadeUtilizada": 1},
            ],
        }
    )

    nome: str = Field(
        min_length=2,
        max_length=100,
        description="Nome comercial do produto.",
        examples=["Açaí Tradicional 300ml"],
    )
    precoVenda: ReaisPosMax = Field(  # type: ignore[valid-type]
        description="Preço atual de venda em reais, maior que zero.", examples=[12.9]
    )
    ativo: bool = Field(
        default=True,
        description="Indica se o produto está disponível para venda.",
        examples=[True],
    )
    composicao: list[ComposicaoProdutoItemDTO] = Field(
        min_length=1,
        description="Lista de ingredientes e quantidades que compõem o produto.",
        examples=[
            [
                {"ingredienteId": 1, "quantidadeUtilizada": 0.3},
                {"ingredienteId": 2, "quantidadeUtilizada": 0.03},
                {"ingredienteId": 7, "quantidadeUtilizada": 1},
            ]
        ],
    )


class UpdateProdutoDTO(_ContractModel):
    """Atualização dos dados comerciais do produto. A composição é atualizada separadamente no recurso /produtos/{id}/composicao."""

    model_config = _example({"nome": "Açaí Tradicional 300ml", "precoVenda": 13.9, "ativo": True})

    nome: str = Field(
        min_length=2,
        max_length=100,
        description="Nome comercial atualizado.",
        examples=["Açaí Tradicional 300ml"],
    )
    precoVenda: ReaisPosMax = Field(  # type: ignore[valid-type]
        description="Novo preço de venda em reais, maior que zero.", examples=[13.9]
    )
    ativo: bool = Field(
        description="Indica se o produto está disponível para venda.", examples=[True]
    )


class Produto(_ContractModel):
    """Produto comercializável e sua composição."""

    model_config = _example(
        {
            "id": 1,
            "nome": "Açaí Tradicional 300ml",
            "precoVenda": 12.9,
            "ativo": True,
            "composicao": [
                {
                    "ingredienteId": 1,
                    "nomeIngrediente": "Açaí (polpa)",
                    "unidadeMedida": "kg",
                    "quantidadeUtilizada": 0.3,
                }
            ],
        }
    )

    id: Id = Field(description="Identificador único do produto.", examples=[1])
    nome: str = Field(
        max_length=100,
        description="Nome comercial do produto.",
        examples=["Açaí Tradicional 300ml"],
    )
    precoVenda: ReaisPos = Field(  # type: ignore[valid-type]
        description="Preço de venda vigente em reais.", examples=[12.9]
    )
    ativo: bool = Field(
        description="Indica se o produto está disponível para venda.", examples=[True]
    )
    composicao: list[ComposicaoProdutoItem] = Field(
        min_length=1,
        description="Ingredientes e quantidades por unidade do produto.",
        examples=[
            [
                {
                    "ingredienteId": 1,
                    "nomeIngrediente": "Açaí (polpa)",
                    "unidadeMedida": "kg",
                    "quantidadeUtilizada": 0.3,
                }
            ]
        ],
    )


# ---------------------------------------------------------------------------
# Movimentações de estoque
# ---------------------------------------------------------------------------


class CreateMovimentacaoEstoqueDTO(_ContractModel):
    """Registro de movimentação manual. PEDIDO é motivo reservado para baixa automática criada no fluxo de pedido; quantidadeRestante é calculada pelo servidor."""

    model_config = _example(
        {
            "ingredienteId": 1,
            "tipo": "ENTRADA",
            "quantidade": 15,
            "observacao": "Compra semanal de polpa",
            "dataValidade": "2026-11-30",
        }
    )

    ingredienteId: Id = Field(description="Ingrediente movimentado.", examples=[1])
    tipo: TipoMovimentacao = Field(
        description="ENTRADA adiciona uma nova linha de estoque; SAIDA consome saldo disponível.",
        examples=["ENTRADA"],
    )
    quantidade: Qtd3Pos = Field(  # type: ignore[valid-type]
        description="Quantidade movimentada, maior que zero.", examples=[15]
    )
    observacao: str | None = Field(
        default=None,
        max_length=255,
        description="Observação opcional sobre a movimentação.",
        examples=["Compra semanal de polpa"],
    )
    dataValidade: date | None = Field(
        default=None,
        description=(
            "Validade da linha de entrada. Obrigatória para ENTRADA conforme regra de "
            "negócio; proibida em SAIDA."
        ),
        examples=["2026-11-30"],
    )
    motivo: MotivoSaidaManual | None = Field(
        default=None,
        description=(
            "Obrigatório em SAIDA: CONVENCIONAL ou DESCARTE_VENCIDO. Não enviar em ENTRADA; "
            "PEDIDO é reservado ao sistema."
        ),
        examples=["CONVENCIONAL"],
    )


class MovimentacaoEstoque(_ContractModel):
    """Registro de entrada ou saída de estoque. As saídas são imutáveis e mantêm trilha de auditoria."""

    model_config = _example(
        {
            "id": 102,
            "ingredienteId": 1,
            "usuarioId": 12,
            "tipo": "ENTRADA",
            "quantidade": 15,
            "dataMovimentacao": "2026-10-30T15:10:00-03:00",
            "observacao": "Compra semanal de polpa",
            "dataValidade": "2026-11-30",
            "quantidadeRestante": 15,
            "motivo": None,
        }
    )

    id: Id = Field(description="Identificador da movimentação.", examples=[102])
    ingredienteId: Id = Field(
        description="Identificador do ingrediente movimentado.", examples=[1]
    )
    usuarioId: Id = Field(description="Usuário responsável pelo registro.", examples=[12])
    tipo: TipoMovimentacao = Field(description="Tipo da movimentação.", examples=["ENTRADA"])
    quantidade: Qtd3PosSemMax = Field(  # type: ignore[valid-type]
        description="Quantidade movimentada.", examples=[15]
    )
    dataMovimentacao: datetime = Field(
        description="Data e hora do registro, conforme horário de São Paulo.",
        examples=["2026-10-30T15:10:00-03:00"],
    )
    observacao: str | None = Field(
        default=None,
        max_length=255,
        description="Observação opcional.",
        examples=["Compra semanal de polpa"],
    )
    dataValidade: date | None = Field(
        default=None,
        description="Validade da linha de estoque criada por ENTRADA; nula em SAIDA.",
        examples=["2026-11-30"],
    )
    quantidadeRestante: Qtd3NaoNegSemMax | None = Field(  # type: ignore[valid-type]
        default=None,
        description="Saldo ainda disponível desta linha de entrada. Nulo em SAIDA.",
        examples=[15],
    )
    motivo: MotivoMovimentacao | None = Field(
        default=None,
        description="Motivo da saída. PEDIDO indica consumo automático por pedido.",
    )


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------


class PedidoItemDTO(_ContractModel):
    """Produto e quantidade solicitada em um pedido. O preço é obtido pelo servidor e gravado como snapshot."""

    model_config = _example({"produtoId": 2, "quantidade": 2})

    produtoId: Id = Field(description="Identificador do produto solicitado.", examples=[2])
    quantidade: int = Field(
        ge=1,
        le=10000,
        description="Quantidade de unidades do produto.",
        examples=[2],
    )


class CreatePedidoDTO(_ContractModel):
    """Dados para registrar pedido. usuarioId, preço unitário e valorTotal são definidos pelo backend; clienteId é opcional."""

    model_config = _example({"clienteId": 31, "itens": [{"produtoId": 2, "quantidade": 2}]})

    clienteId: Id | None = Field(
        default=None,
        description=(
            "Cliente associado ao pedido. Pode ser omitido para venda sem cadastro de cliente."
        ),
        examples=[31],
    )
    itens: list[PedidoItemDTO] = Field(
        min_length=1,
        description="Produtos e quantidades do pedido. Deve conter ao menos um item.",
        examples=[[{"produtoId": 2, "quantidade": 2}]],
    )


class PedidoItem(_ContractModel):
    """Item de pedido com preço unitário registrado no momento da venda."""

    model_config = _example(
        {
            "produtoId": 2,
            "nomeProduto": "Açaí Especial 500ml",
            "quantidade": 2,
            "precoUnitarioRegistrado": 18.9,
            "subtotal": 37.8,
        }
    )

    produtoId: Id = Field(description="Identificador do produto.", examples=[2])
    nomeProduto: str = Field(
        max_length=100,
        description="Nome do produto no momento da resposta.",
        examples=["Açaí Especial 500ml"],
    )
    quantidade: Id = Field(description="Quantidade vendida.", examples=[2])
    precoUnitarioRegistrado: ReaisPos = Field(  # type: ignore[valid-type]
        description="Preço unitário congelado no momento do pedido.", examples=[18.9]
    )
    subtotal: ReaisNaoNeg = Field(  # type: ignore[valid-type]
        description="Quantidade multiplicada pelo preço unitário registrado.", examples=[37.8]
    )


class Pedido(_ContractModel):
    """Pedido registrado no sistema. Pedido cancelado permanece armazenado para rastreabilidade e não deve ser contabilizado no faturamento."""

    model_config = _example(
        {
            "id": 501,
            "clienteId": 31,
            "usuarioId": 12,
            "dataPedido": "2026-10-30T15:25:00-03:00",
            "valorTotal": 37.8,
            "status": "ATIVO",
            "dataCancelamento": None,
            "usuarioCancelamentoId": None,
            "itens": [
                {
                    "produtoId": 2,
                    "nomeProduto": "Açaí Especial 500ml",
                    "quantidade": 2,
                    "precoUnitarioRegistrado": 18.9,
                    "subtotal": 37.8,
                }
            ],
        }
    )

    id: Id = Field(description="Identificador único do pedido.", examples=[501])
    clienteId: Id | None = Field(
        default=None,
        description="Identificador do cliente; nulo em venda sem cliente cadastrado.",
        examples=[31],
    )
    usuarioId: Id = Field(
        description="Identificador do usuário que registrou o pedido.", examples=[12]
    )
    dataPedido: datetime = Field(
        description="Data e hora em que o pedido foi registrado.",
        examples=["2026-10-30T15:25:00-03:00"],
    )
    valorTotal: ReaisNaoNeg = Field(  # type: ignore[valid-type]
        description="Soma dos subtotais dos itens, calculada pelo backend.", examples=[37.8]
    )
    status: StatusPedido = Field(description="Situação atual do pedido.", examples=["ATIVO"])
    dataCancelamento: datetime | None = Field(
        default=None,
        description="Data e hora do cancelamento; preenchida somente se status=CANCELADO.",
    )
    usuarioCancelamentoId: Id | None = Field(
        default=None,
        description="Usuário que realizou o cancelamento; preenchido somente se status=CANCELADO.",
    )
    itens: list[PedidoItem] = Field(
        min_length=1,
        description="Itens que compõem o pedido.",
        examples=[
            [
                {
                    "produtoId": 2,
                    "nomeProduto": "Açaí Especial 500ml",
                    "quantidade": 2,
                    "precoUnitarioRegistrado": 18.9,
                    "subtotal": 37.8,
                }
            ]
        ],
    )


class CancelamentoPedidoDTO(_ContractModel):
    """Informação opcional para auditoria do cancelamento."""

    model_config = _example({"observacao": "Pedido lançado em duplicidade"})

    observacao: str | None = Field(
        default=None,
        max_length=255,
        description="Justificativa textual do cancelamento, se informada.",
        examples=["Pedido lançado em duplicidade"],
    )


# ---------------------------------------------------------------------------
# Recomendações
# ---------------------------------------------------------------------------


class ProducaoRecomendacaoItem(_ContractModel):
    """Quantidade recomendada de produção de um produto para o cenário de estoque válido atual."""

    model_config = _example(
        {
            "produtoId": 2,
            "nomeProduto": "Açaí Especial 500ml",
            "quantidadeRecomendada": 18,
            "lucroEstimadoUnitario": 8.2,
            "lucroEstimadoTotal": 147.6,
        }
    )

    produtoId: Id = Field(description="Produto recomendado.", examples=[2])
    nomeProduto: str = Field(
        max_length=100, description="Nome do produto.", examples=["Açaí Especial 500ml"]
    )
    quantidadeRecomendada: int = Field(
        ge=0,
        le=INT32_MAX,
        description="Quantidade inteira ótima de unidades a produzir.",
        examples=[18],
    )
    lucroEstimadoUnitario: ReaisNaoNeg = Field(  # type: ignore[valid-type]
        description="Preço de venda menos custo dos ingredientes por unidade.", examples=[8.2]
    )
    lucroEstimadoTotal: ReaisNaoNeg = Field(  # type: ignore[valid-type]
        description="Lucro estimado unitário multiplicado pela quantidade recomendada.",
        examples=[147.6],
    )


class ProducaoRecomendacao(_ContractModel):
    """Resultado sob demanda do modelo de Programação Linear Inteira. Não representa histórico persistido."""

    model_config = _example(
        {
            "calculadoEm": "2026-10-30T15:30:00-03:00",
            "criterioOtimizacao": "LUCRO_ESTIMADO",
            "lucroTotalEstimado": 147.6,
            "itens": [
                {
                    "produtoId": 2,
                    "nomeProduto": "Açaí Especial 500ml",
                    "quantidadeRecomendada": 18,
                    "lucroEstimadoUnitario": 8.2,
                    "lucroEstimadoTotal": 147.6,
                }
            ],
            "observacao": "O cálculo considera somente linhas de estoque não vencidas.",
        }
    )

    calculadoEm: datetime = Field(
        description="Data e hora do cálculo.", examples=["2026-10-30T15:30:00-03:00"]
    )
    criterioOtimizacao: Literal["LUCRO_ESTIMADO"] = Field(
        description="Critério da função objetivo aprovado no adendo do projeto.",
        examples=["LUCRO_ESTIMADO"],
    )
    lucroTotalEstimado: ReaisNaoNeg = Field(  # type: ignore[valid-type]
        description="Lucro estimado total da solução ótima em reais.", examples=[327.6]
    )
    itens: list[ProducaoRecomendacaoItem] = Field(
        description="Quantidade ótima recomendada por produto.",
        examples=[
            [
                {
                    "produtoId": 2,
                    "nomeProduto": "Açaí Especial 500ml",
                    "quantidadeRecomendada": 18,
                    "lucroEstimadoUnitario": 8.2,
                    "lucroEstimadoTotal": 147.6,
                }
            ]
        ],
    )
    # Opcional e NÃO nullable: ausência permitida, ``null`` rejeitado.
    observacao: str = Field(  # type: ignore[assignment]
        default=None,
        max_length=500,
        description="Nota sobre limites do cálculo e estoque considerado.",
        examples=["O cálculo considera somente linhas de estoque não vencidas."],
    )


class CreateReposicaoDTO(_ContractModel):
    """Parâmetros para cálculo de reposição de ingredientes com horizonte e orçamento disponíveis."""

    model_config = _example({"periodoDias": 30, "orcamento": 500})

    periodoDias: int = Field(
        ge=1,
        le=365,
        description="Horizonte de consumo em dias utilizado na estimativa.",
        examples=[30],
    )
    orcamento: ReaisNaoNegMax = Field(  # type: ignore[valid-type]
        description="Orçamento máximo disponível em reais.", examples=[500]
    )


class ReposicaoRecomendacaoItem(_ContractModel):
    """Quantidade de compra sugerida para um ingrediente."""

    model_config = _example(
        {
            "ingredienteId": 4,
            "nomeIngrediente": "Banana",
            "quantidadeRecomendada": 8.5,
            "unidadeMedida": "kg",
            "custoEstimado": 46.75,
        }
    )

    ingredienteId: Id = Field(description="Identificador do ingrediente.", examples=[4])
    nomeIngrediente: str = Field(
        max_length=100, description="Nome do ingrediente.", examples=["Banana"]
    )
    quantidadeRecomendada: Qtd3NaoNegSemMax = Field(  # type: ignore[valid-type]
        description="Quantidade sugerida para compra, na unidade do ingrediente.", examples=[8.5]
    )
    unidadeMedida: str = Field(
        max_length=20, description="Unidade em que a quantidade é expressa.", examples=["kg"]
    )
    custoEstimado: ReaisNaoNeg = Field(  # type: ignore[valid-type]
        description="Custo estimado da compra em reais.", examples=[46.75]
    )


class ReposicaoRecomendacao(_ContractModel):
    """Resultado sob demanda da otimização de reposição, respeitando o orçamento e o período informados."""

    model_config = _example(
        {
            "calculadoEm": "2026-10-30T15:35:00-03:00",
            "periodoDias": 30,
            "orcamento": 500,
            "custoTotalEstimado": 46.75,
            "itens": [
                {
                    "ingredienteId": 4,
                    "nomeIngrediente": "Banana",
                    "quantidadeRecomendada": 8.5,
                    "unidadeMedida": "kg",
                    "custoEstimado": 46.75,
                }
            ],
        }
    )

    calculadoEm: datetime = Field(
        description="Data e hora do cálculo.", examples=["2026-10-30T15:35:00-03:00"]
    )
    periodoDias: int = Field(
        ge=1, le=365, description="Horizonte de consumo utilizado.", examples=[30]
    )
    orcamento: ReaisNaoNeg = Field(  # type: ignore[valid-type]
        description="Orçamento máximo informado em reais.", examples=[500]
    )
    custoTotalEstimado: ReaisNaoNeg = Field(  # type: ignore[valid-type]
        description="Soma dos custos estimados da recomendação.", examples=[346.75]
    )
    itens: list[ReposicaoRecomendacaoItem] = Field(
        description="Ingredientes e quantidades recomendadas.",
        examples=[
            [
                {
                    "ingredienteId": 4,
                    "nomeIngrediente": "Banana",
                    "quantidadeRecomendada": 8.5,
                    "unidadeMedida": "kg",
                    "custoEstimado": 46.75,
                }
            ]
        ],
    )


# ---------------------------------------------------------------------------
# Alertas, marketing, dashboard e saúde
# ---------------------------------------------------------------------------


class AlertaReposicao(_ContractModel):
    """Ingrediente cujo saldo válido atingiu o limite mínimo configurado."""

    model_config = _example(
        {
            "ingredienteId": 4,
            "nomeIngrediente": "Banana",
            "quantidadeEstoqueValido": 2,
            "quantidadeMinima": 3,
            "unidadeMedida": "kg",
            "deficit": 1,
        }
    )

    ingredienteId: Id = Field(description="Identificador do ingrediente.", examples=[4])
    nomeIngrediente: str = Field(
        max_length=100, description="Nome do ingrediente.", examples=["Banana"]
    )
    quantidadeEstoqueValido: Qtd3NaoNegSemMax = Field(  # type: ignore[valid-type]
        description="Saldo não vencido disponível para consumo.", examples=[2]
    )
    quantidadeMinima: Qtd3NaoNegSemMax = Field(  # type: ignore[valid-type]
        description="Limite mínimo configurado.", examples=[3]
    )
    unidadeMedida: str = Field(
        max_length=20, description="Unidade de medida do ingrediente.", examples=["kg"]
    )
    deficit: Qtd3NaoNegSemMax = Field(  # type: ignore[valid-type]
        description="Diferença positiva entre o mínimo e o saldo válido.", examples=[1]
    )


class AlertaValidade(_ContractModel):
    """Linha de entrada de estoque próxima do vencimento ou já vencida."""

    model_config = _example(
        {
            "movimentacaoId": 102,
            "ingredienteId": 1,
            "nomeIngrediente": "Açaí (polpa)",
            "dataValidade": "2026-11-02",
            "quantidadeRestante": 5,
            "diasAteVencimento": 3,
            "situacao": "PROXIMO_VENCIMENTO",
        }
    )

    movimentacaoId: Id = Field(
        description="Identificador da movimentação de entrada que criou a linha.", examples=[102]
    )
    ingredienteId: Id = Field(description="Identificador do ingrediente.", examples=[1])
    nomeIngrediente: str = Field(
        max_length=100, description="Nome do ingrediente.", examples=["Açaí (polpa)"]
    )
    dataValidade: date = Field(
        description="Data de validade da linha de estoque.", examples=["2026-11-02"]
    )
    quantidadeRestante: Qtd3NaoNegSemMax = Field(  # type: ignore[valid-type]
        description="Quantidade ainda disponível nesta linha.", examples=[5]
    )
    diasAteVencimento: int = Field(
        description="Dias até a validade; valores negativos indicam vencimento passado.",
        examples=[3],
    )
    situacao: Literal["PROXIMO_VENCIMENTO", "VENCIDO"] = Field(
        description="Classificação temporal da linha.", examples=["PROXIMO_VENCIMENTO"]
    )


class SugestaoMarketing(_ContractModel):
    """Sugestão de marketing gerada sob demanda a partir dos dados comerciais disponíveis."""

    model_config = _example(
        {
            "geradoEm": "2026-10-30T15:40:00-03:00",
            "sugestoes": ["Divulgar o Açaí Especial 500ml como opção de maior margem."],
            "observacao": "Sugestões baseadas nos produtos cadastrados e indicadores disponíveis.",
        }
    )

    geradoEm: datetime = Field(
        description="Data e hora da geração.", examples=["2026-10-30T15:40:00-03:00"]
    )
    sugestoes: list[Annotated[str, Field(max_length=1000)]] = Field(
        description="Lista de textos sugeridos. As sugestões não são publicadas automaticamente.",
        examples=[["Divulgar o Açaí Especial 500ml como opção de maior margem."]],
    )
    observacao: str | None = Field(
        default=None,
        max_length=500,
        description="Limitações ou contexto usado na geração.",
        examples=["Sugestões baseadas nos produtos cadastrados e indicadores disponíveis."],
    )


class ProdutoMaisVendido(_ContractModel):
    """Resumo de quantidade vendida por produto."""

    model_config = _example(
        {"produtoId": 2, "nomeProduto": "Açaí Especial 500ml", "quantidadeVendida": 45}
    )

    produtoId: Id = Field(description="Identificador do produto.", examples=[2])
    nomeProduto: str = Field(
        max_length=100, description="Nome do produto.", examples=["Açaí Especial 500ml"]
    )
    quantidadeVendida: int = Field(
        ge=0, description="Unidades vendidas em pedidos ATIVOS do período.", examples=[45]
    )


class Dashboard(_ContractModel):
    """Indicadores consolidados para acompanhamento gerencial."""

    model_config = _example(
        {
            "periodoInicio": "2026-10-01",
            "periodoFim": "2026-10-30",
            "quantidadePedidos": 128,
            "faturamentoTotal": 2450.7,
            "ticketMedio": 19.14,
            "produtosMaisVendidos": [
                {"produtoId": 2, "nomeProduto": "Açaí Especial 500ml", "quantidadeVendida": 45}
            ],
            "ingredientesEmReposicao": 2,
            "linhasProximasVencimento": 1,
        }
    )

    periodoInicio: date = Field(description="Início do intervalo consultado.", examples=["2026-10-01"])
    periodoFim: date = Field(description="Fim do intervalo consultado.", examples=["2026-10-30"])
    quantidadePedidos: int = Field(
        ge=0, description="Quantidade de pedidos ATIVOS no período.", examples=[128]
    )
    faturamentoTotal: ReaisNaoNeg = Field(  # type: ignore[valid-type]
        description="Soma do valor dos pedidos ATIVOS no período, em reais.", examples=[2450.7]
    )
    ticketMedio: ReaisNaoNeg = Field(  # type: ignore[valid-type]
        description=(
            "Faturamento dividido pela quantidade de pedidos, em reais; zero quando não "
            "houver pedidos."
        ),
        examples=[19.14],
    )
    produtosMaisVendidos: list[ProdutoMaisVendido] = Field(
        description="Ranking resumido de produtos por quantidade vendida.",
        examples=[
            [{"produtoId": 2, "nomeProduto": "Açaí Especial 500ml", "quantidadeVendida": 45}]
        ],
    )
    ingredientesEmReposicao: int = Field(
        ge=0, description="Quantidade de ingredientes abaixo do limite mínimo.", examples=[2]
    )
    linhasProximasVencimento: int = Field(
        ge=0,
        description="Quantidade de linhas de entrada próximas do vencimento.",
        examples=[1],
    )


class HealthStatus(_ContractModel):
    """Estado operacional básico da API e da conexão com o banco."""

    model_config = _example({"status": "ok", "banco": "ok"})

    status: Literal["ok", "degradado"] = Field(
        description="Estado geral da aplicação.", examples=["ok"]
    )
    banco: Literal["ok", "indisponivel"] = Field(
        description="Estado da conexão com banco de dados.", examples=["ok"]
    )


# ---------------------------------------------------------------------------
# Respostas paginadas (envelope: {data, paginacao})
# ---------------------------------------------------------------------------

_EMPTY_PAGE_EXAMPLE: dict[str, object] = {
    "data": [],
    "paginacao": {"page": 0, "size": 20, "totalElements": 0, "totalPages": 0},
}


class PaginatedUsuarios(_ContractModel):
    """Lista paginada de usuarios."""

    model_config = _example(_EMPTY_PAGE_EXAMPLE)

    data: list[Usuario] = Field(description="Itens da página atual.", examples=[[]])
    paginacao: PageMetadata = Field(description="Metadados de paginação.")


class PaginatedClientes(_ContractModel):
    """Lista paginada de clientes."""

    model_config = _example(_EMPTY_PAGE_EXAMPLE)

    data: list[Cliente] = Field(description="Itens da página atual.", examples=[[]])
    paginacao: PageMetadata = Field(description="Metadados de paginação.")


class PaginatedUnidadesMedida(_ContractModel):
    """Lista paginada de unidadesmedida."""

    model_config = _example(_EMPTY_PAGE_EXAMPLE)

    data: list[UnidadeMedida] = Field(description="Itens da página atual.", examples=[[]])
    paginacao: PageMetadata = Field(description="Metadados de paginação.")


class PaginatedIngredientes(_ContractModel):
    """Lista paginada de ingredientes."""

    model_config = _example(_EMPTY_PAGE_EXAMPLE)

    data: list[Ingrediente] = Field(description="Itens da página atual.", examples=[[]])
    paginacao: PageMetadata = Field(description="Metadados de paginação.")


class PaginatedProdutos(_ContractModel):
    """Lista paginada de produtos."""

    model_config = _example(_EMPTY_PAGE_EXAMPLE)

    data: list[Produto] = Field(description="Itens da página atual.", examples=[[]])
    paginacao: PageMetadata = Field(description="Metadados de paginação.")


class PaginatedMovimentacoesEstoque(_ContractModel):
    """Lista paginada de movimentacoesestoque."""

    model_config = _example(_EMPTY_PAGE_EXAMPLE)

    data: list[MovimentacaoEstoque] = Field(description="Itens da página atual.", examples=[[]])
    paginacao: PageMetadata = Field(description="Metadados de paginação.")


class PaginatedPedidos(_ContractModel):
    """Lista paginada de pedidos."""

    model_config = _example(_EMPTY_PAGE_EXAMPLE)

    data: list[Pedido] = Field(description="Itens da página atual.", examples=[[]])
    paginacao: PageMetadata = Field(description="Metadados de paginação.")


# ---------------------------------------------------------------------------
# Composição, alertas agregados e utilitários
# ---------------------------------------------------------------------------


class ComposicaoProduto(_ContractModel):
    """Representação isolada da composição de um produto."""

    model_config = _example(
        {
            "produtoId": 1,
            "itens": [
                {
                    "ingredienteId": 1,
                    "nomeIngrediente": "Açaí (polpa)",
                    "unidadeMedida": "kg",
                    "quantidadeUtilizada": 0.3,
                }
            ],
        }
    )

    produtoId: Id = Field(description="Identificador do produto.", examples=[1])
    itens: list[ComposicaoProdutoItem] = Field(
        min_length=1,
        description="Ingredientes e quantidades da composição.",
        examples=[
            [
                {
                    "ingredienteId": 1,
                    "nomeIngrediente": "Açaí (polpa)",
                    "unidadeMedida": "kg",
                    "quantidadeUtilizada": 0.3,
                }
            ]
        ],
    )


class SubstituirComposicaoDTO(_ContractModel):
    """Lista integral que substituirá a composição atual de um produto."""

    model_config = _example(
        {
            "itens": [
                {"ingredienteId": 1, "quantidadeUtilizada": 0.3},
                {"ingredienteId": 7, "quantidadeUtilizada": 1},
            ]
        }
    )

    itens: list[ComposicaoProdutoItemDTO] = Field(
        min_length=1,
        description="Nova composição completa; deve conter ao menos um ingrediente.",
        examples=[
            [
                {"ingredienteId": 1, "quantidadeUtilizada": 0.3},
                {"ingredienteId": 7, "quantidadeUtilizada": 1},
            ]
        ],
    )


class VazioDTO(_ContractModel):
    """Objeto vazio para operações que não recebem parâmetros de entrada."""

    model_config = _example({})


class ListaAlertasReposicao(_ContractModel):
    """Coleção de alertas de reposição."""

    model_config = _example({"itens": []})

    itens: list[AlertaReposicao] = Field(description="Alertas retornados.", examples=[[]])


class ListaAlertasValidade(_ContractModel):
    """Coleção de alertas de validade."""

    model_config = _example({"itens": []})

    itens: list[AlertaValidade] = Field(description="Alertas retornados.", examples=[[]])


# `type: string, format: binary` (text/csv). Não é um objeto JSON.
CsvFile = Annotated[
    str,
    Field(
        description=(
            "Arquivo CSV UTF-8 retornado no corpo da resposta. O conteúdo é texto CSV, "
            "não um objeto JSON."
        ),
        json_schema_extra={"format": "binary"},
    ),
]
