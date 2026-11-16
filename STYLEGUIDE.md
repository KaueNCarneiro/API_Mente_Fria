# STYLEGUIDE.md — Constituição Técnica (Mente Fria API)

Este documento define as regras técnicas obrigatórias para implementar a API. O contrato HTTP e os schemas têm como fonte de verdade o arquivo [`Mente Fria API.openapi.json`](Mente%20Fria%20API.openapi.json). Não introduza rotas, campos, enums, parâmetros ou respostas que não estejam previstos nele sem uma alteração explícita e revisada do contrato.

## 1. Stack tecnológica e versões obrigatórias

- **Linguagem:** Python 3.12+ com anotações estáticas (`typing`, `Decimal`, `date`, `datetime`, `Enum` e `Annotated`). Use `Decimal` para valores monetários e quantidades que exijam precisão decimal; evite `float` para cálculos financeiros.
- **Framework Web:** FastAPI.
- **Validação e serialização:** Pydantic v2 (`BaseModel`, `ConfigDict`, `Field`, validadores apropriados e `from_attributes=True`). Os modelos devem espelhar os schemas OpenAPI e preservar os nomes JSON do contrato.
- **Persistência e ORM:** SQLAlchemy 2.0+ com API declarativa (`DeclarativeBase`, `Mapped`, `mapped_column`, `relationship`, `ForeignKey`, `select()` e `Session`). Banco SQLite no desenvolvimento local (`sqlite:///./mente_fria.db`) e banco isolado em memória ou arquivo temporário nos testes.
- **Segurança:** autenticação stateless por JWT com `PyJWT`, esquema HTTP Bearer e autorização RBAC. Os papéis do domínio são exatamente `ADMINISTRADOR` e `FUNCIONARIO`.
- **Testes:** `pytest`, `fastapi.testclient.TestClient` e `httpx`.
- **Otimização:** a recomendação de produção deve respeitar o contrato e a integração do solver de Programação Linear Inteira. A indisponibilidade do serviço de otimização deve ser tratada como `503` quando aplicável.

## 2. Arquitetura de diretórios e separação de camadas

A estrutura abaixo é uma organização recomendada para a implementação. Pode ser refinada no `PLAN.md`, mas não deve misturar regras HTTP, domínio, persistência e integração externa.

```text
src/api/
├── __init__.py
├── main.py                 # FastAPI, lifespan, CORS, registro de routers e handlers
├── config.py               # Configurações por ambiente e segredos
├── schemas.py              # Pydantic v2: DTOs e respostas derivados dos 54 schemas OpenAPI
├── models.py               # Modelos ORM SQLAlchemy 2.0
├── database.py             # Engine, SessionLocal, get_db, inicialização e seed
├── security.py             # Hash de senha, JWT, get_current_user e require_role
├── exceptions.py           # Exceções de domínio e resposta ApiError
├── services/
│   ├── __init__.py
│   ├── estoque.py          # Regras de saldo, validade e consumo FEFO
│   ├── pedidos.py          # Registro/cancelamento transacional de pedidos
│   ├── recomendacoes.py    # Orquestração das recomendações e solver
│   └── dashboard.py        # Agregações gerenciais
├── integrations/
│   ├── __init__.py
│   └── optimizer.py        # Integração com o otimizador externo/solver
├── routers/
│   ├── __init__.py
│   ├── saude.py
│   ├── auth.py
│   ├── usuarios.py
│   ├── clientes.py
│   ├── unidades_medida.py
│   ├── ingredientes.py
│   ├── movimentacoes_estoque.py
│   ├── produtos.py
│   ├── pedidos.py
│   ├── alertas.py
│   ├── recomendacoes.py
│   ├── sugestoes_marketing.py
│   └── dashboard.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_saude.py
    ├── test_auth.py
    ├── test_usuarios.py
    ├── test_clientes.py
    ├── test_unidades_medida.py
    ├── test_ingredientes.py
    ├── test_movimentacoes_estoque.py
    ├── test_produtos.py
    ├── test_pedidos.py
    ├── test_alertas.py
    ├── test_recomendacoes.py
    ├── test_dashboard.py
    └── test_errors.py
```

## 3. Regras inegociáveis de implementação

### 3.1. Contrato-first e fidelidade ao OpenAPI

- Antes de implementar qualquer rota, consulte `Mente Fria API.openapi.json`.
- Implemente os `operationId`, métodos, caminhos, parâmetros, request bodies, schemas, respostas e regras de segurança definidos no documento.
- Use os 54 schemas de `components.schemas` como referência dos modelos Pydantic. Reutilize DTOs e schemas de resposta; não crie objetos inline equivalentes nas rotas.
- Preserve `required`, `enum`, `format`, `minLength`, `maxLength`, `minimum`, `maximum`, `minItems`, `additionalProperties` e exemplos sempre que definidos.
- Os parâmetros de paginação seguem o contrato: `page` inicia em zero; `size` varia de 1 a 100 e tem padrão 20. `sort` usa o formato `campo,direção`. O parâmetro `q`, quando presente, admite até 100 caracteres.
- IDs numéricos de recursos são inteiros positivos (`int32`, mínimo 1), exceto `unidadeMedida`, que é chave textual com 1 a 20 caracteres.
- Não presuma que todas as rotas já estejam implementadas: o OpenAPI descreve o contrato desejado.

### 3.2. Nomenclatura JSON e Python

- Os nomes enviados e recebidos em JSON devem preservar exatamente o `camelCase`/português do contrato, por exemplo: `accessToken`, `tokenType`, `expiresInSeconds`, `porcaoPadrao`, `custoUnitario`, `quantidadeEstoque`, `quantidadeMinima`, `precisaReposicao`, `dataMovimentacao`, `dataValidade`, `quantidadeRestante`, `precoVenda`, `clienteId`, `usuarioId`, `dataPedido`, `valorTotal`, `dataCancelamento`, `calculadoEm`, `periodoDias`, `dataInicio`, `dataFim` e `totalElements`.
- Atributos Python podem usar `snake_case`, desde que a serialização Pydantic preserve o nome JSON exato por aliases explícitos.
- Use `Decimal` para `precoVenda`, `custoUnitario`, `porcaoPadrao`, `quantidade`, `valorTotal`, custos e lucros. Datas sem horário usam `date`; timestamps usam `datetime` com timezone quando aplicável.
- Não exponha senha, hash de senha, segredo JWT ou dados internos de autenticação em respostas públicas. O schema `Usuario` contém somente `id`, `nome`, `email`, `perfil` e `ativo`.

### 3.3. Tratamento de erros — schema `ApiError`

- É proibido deixar respostas de erro no formato padrão do FastAPI (`{"detail": "..."}`).
- Respostas de erro JSON devem seguir `components.schemas.ApiError` do OpenAPI, com os campos obrigatórios `codigo`, `mensagem`, `detalhes`, `timestamp` e `caminho`, e o campo opcional `correlationId`.
- Cada item de `detalhes` deve seguir `ApiErrorDetail`: `campo` e `mensagem` obrigatórios; `valorRejeitado` opcional. Não substitua esse formato por `type`, `title`, `status`, `instance` ou `invalidParams` — esses campos pertenciam a outro contrato.
- Reutilize os componentes de resposta `BadRequest`, `Unauthorized`, `Forbidden`, `NotFound`, `Conflict`, `ValidationError`, `InternalError` e `ServiceUnavailable`.
- Respeite os códigos HTTP declarados em cada operação: entre eles `400`, `401`, `403`, `404`, `409`, `422` e `503`. Operações de exclusão/desativação que declaram `204` não retornam corpo.
- A validação de entrada deve produzir detalhes úteis por campo e manter o código HTTP previsto no contrato. Não converta indiscriminadamente qualquer erro em `400` ou `422`.

### 3.4. ORM, integridade e transações

- Use exclusivamente a API moderna do SQLAlchemy 2.0 (`select()`, `Session.scalars()`, `Mapped[...]`, `mapped_column(...)`, `relationship(...)`).
- Modele as entidades necessárias ao domínio: usuários, clientes, unidades de medida, ingredientes, movimentações/lotes de estoque, produtos, composição de produtos, pedidos e itens de pedido.
- Respeite as referências descritas no OpenAPI: unidade de medida usada por ingredientes; ingredientes usados na composição de produtos; movimentações associadas a ingredientes e ao usuário responsável; pedidos associados ao usuário, opcionalmente ao cliente, e a itens/produtos.
- Preserve histórico e integridade referencial. Não faça exclusão física quando o contrato determina desativação lógica ou preservação de histórico. Regras de conflito devem resultar em `409` quando especificado.
- Registre pedido e baixas de estoque na mesma transação. Em falha, execute rollback para impedir pedido sem movimentações correspondentes ou baixas parciais.
- Toda escrita (`POST`, `PUT`, `PATCH`, `DELETE`) deve gerenciar transações explicitamente (`commit`, `refresh` e `rollback` em caso de erro).
- Use carregamento eficiente (`selectinload`/`joinedload`) para relações retornadas em conjunto e evite N+1. Não carregue coleções inteiras sem necessidade.

### 3.5. Regras de estoque e pedidos

- O saldo de ingrediente é derivado das entradas ainda disponíveis; não deve ser editado diretamente no cadastro do ingrediente.
- Uma movimentação `ENTRADA` cria registro/lote com `quantidadeRestante` inicial igual à quantidade recebida e pode conter `dataValidade`.
- Uma movimentação `SAIDA` consome lotes válidos em ordem FEFO (primeiro a vencer, primeiro a sair) e não pode consumir estoque vencido.
- O `usuarioId` da movimentação e do pedido é obtido da identidade autenticada, não aceito livremente do cliente.
- O registro de pedido captura os preços vigentes, calcula subtotais e total, valida o estoque válido e cria as baixas com motivo `PEDIDO`.
- O cancelamento marca o pedido como `CANCELADO`, registra data e usuário responsável e, conforme decisão de negócio descrita no contrato, **não devolve estoque automaticamente**.
- Pedidos cancelados continuam consultáveis, mas não entram nos indicadores de faturamento, ticket médio ou ranking de vendas.

### 3.6. Segurança JWT e RBAC

- Use `Authorization: Bearer <token>` nas operações que declaram `security: [{ bearerAuth: [] }]`. `GET /api/v1/saude`, `POST /api/v1/auth/administrador` e `POST /api/v1/auth/login` são explicitamente públicos no contrato.
- O login recebe `LoginDTO` (`email`, `senha`) e retorna `AuthToken` com `accessToken`, `tokenType` (`Bearer`), `expiresInSeconds` e `usuario`.
- A criação inicial de administrador só pode ocorrer enquanto não existir uma conta com perfil `ADMINISTRADOR`. A senha deve ser armazenada exclusivamente como hash.
- O cadastro comum em `/api/v1/usuarios` sempre cria `FUNCIONARIO`; o cliente não escolhe o perfil.
- Papéis e permissões devem respeitar as descrições das operações: operações administrativas (usuários, unidades, ingredientes, produtos, recomendações e dashboard) são restritas a `ADMINISTRADOR`; operações explicitamente liberadas a ambos aceitam `ADMINISTRADOR` e `FUNCIONARIO`.
- Para rotas cuja descrição apenas exige autenticação e não explicita o papel, exija usuário autenticado e não invente uma restrição de papel. Consulte o contrato antes de ampliar a matriz RBAC.
- Token ausente, inválido ou expirado resulta em `401`; usuário autenticado sem permissão resulta em `403`. Ambos usam `ApiError`.
- A implementação pode adotar `HS256` com `PyJWT`; segredo, emissão e expiração devem ser configuráveis por ambiente. O contrato não fixa duração do token nem define endpoint `/auth/me`; não invente esses requisitos como parte da API pública.

### 3.7. Regras especiais de domínio

- **Unidades:** atualizar `porcaoPadrao` altera a sugestão para novos ingredientes, sem recalcular ingredientes existentes. Excluir unidade em uso deve ser impedido.
- **Ingredientes:** cadastro inicia com estoque zero; entradas são registradas em `/movimentacoes-estoque`. Não permita alterar saldo por `PUT`.
- **Produtos:** composição deve referenciar ingredientes existentes e quantidades positivas. `DELETE /produtos/{id}` desativa o produto, não o apaga fisicamente.
- **Clientes:** associação a pedido é opcional. Não exclua cliente referenciado por pedido; responda `409`.
- **Recomendações:** resultados são calculados sob demanda e não criam histórico persistido no modelo atual. A produção maximiza lucro estimado e respeita estoque válido. Reposição respeita período e orçamento informados.
- **Marketing:** sugestões são informativas e não são publicadas automaticamente.
- **Dashboard/CSV:** respeite o período informado; somente pedidos `ATIVO` compõem os indicadores financeiros. CSV é conteúdo `text/csv` UTF-8, não JSON.
