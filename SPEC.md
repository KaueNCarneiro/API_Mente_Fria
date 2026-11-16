# SPEC.md — Especificação de Negócio, ORM e Autenticação (Mente Fria API)

## 1. Visão geral e fonte da verdade

A **Mente Fria API** é uma API REST para apoiar a gestão de pequenos comércios, com piloto em uma açaiteria. Centraliza usuários, clientes, unidades de medida, ingredientes, produtos e suas composições, movimentações de estoque e pedidos; disponibiliza alertas, dashboard, recomendações e sugestões de marketing.

A fonte da verdade para o contrato HTTP é [`Mente Fria API.openapi.json`](Mente%20Fria%20API.openapi.json), OpenAPI 3.0.1, versão `1.0.0`. O documento descreve o contrato desejado em `/api/v1`; não significa que todas as operações já estejam implementadas.

**Regra de precedência:** caminhos, métodos, `operationId`, parâmetros, schemas, exemplos, respostas e requisitos `security` vêm do OpenAPI. Este documento detalha decisões de implementação (Pydantic, ORM, transações, segurança e testes), sem redefinir o contrato.

## 2. Escopo funcional e inventário de operações

O contrato contém 26 caminhos e as operações abaixo:

| Domínio | Método e caminho | Operação (`operationId`) | Finalidade |
|---|---|---|---|
| Saúde | `GET /api/v1/saude` | `consultarSaude` | Verificar API e banco; público |
| Autenticação | `POST /api/v1/auth/administrador` | `criarContaAdministrador` | Criar o primeiro administrador |
| Autenticação | `POST /api/v1/auth/login` | `autenticarUsuario` | Autenticar e emitir token Bearer |
| Usuários | `GET /api/v1/usuarios` | `listarUsuarios` | Listar usuários (administrador) |
| Usuários | `POST /api/v1/usuarios` | `cadastrarFuncionario` | Cadastrar funcionário (administrador) |
| Usuários | `GET /api/v1/usuarios/{id}` | `consultarUsuario` | Consultar usuário (administrador) |
| Usuários | `PATCH /api/v1/usuarios/{id}` | `atualizarUsuario` | Atualizar nome, e-mail ou ativo (administrador) |
| Usuários | `DELETE /api/v1/usuarios/{id}` | `desativarUsuario` | Desativar logicamente usuário (administrador) |
| Clientes | `GET /api/v1/clientes` | `listarClientes` | Listar e pesquisar clientes |
| Clientes | `POST /api/v1/clientes` | `cadastrarCliente` | Cadastrar cliente |
| Clientes | `GET /api/v1/clientes/{id}` | `consultarCliente` | Consultar cliente |
| Clientes | `PUT /api/v1/clientes/{id}` | `atualizarCliente` | Substituir dados do cliente |
| Clientes | `DELETE /api/v1/clientes/{id}` | `excluirCliente` | Excluir se não houver pedidos associados |
| Unidades de medida | `GET /api/v1/unidades-medida` | `listarUnidadesMedida` | Listar unidades e porções padrão |
| Unidades de medida | `POST /api/v1/unidades-medida` | `cadastrarUnidadeMedida` | Criar unidade (administrador) |
| Unidades de medida | `GET /api/v1/unidades-medida/{unidadeMedida}` | `consultarUnidadeMedida` | Consultar unidade (administrador) |
| Unidades de medida | `PUT /api/v1/unidades-medida/{unidadeMedida}` | `atualizarUnidadeMedida` | Atualizar porção padrão |
| Unidades de medida | `DELETE /api/v1/unidades-medida/{unidadeMedida}` | `excluirUnidadeMedida` | Excluir unidade sem ingredientes vinculados |
| Ingredientes | `GET /api/v1/ingredientes` | `listarIngredientes` | Listar, paginar e filtrar ingredientes |
| Ingredientes | `POST /api/v1/ingredientes` | `cadastrarIngrediente` | Cadastrar ingrediente com estoque inicial zero |
| Ingredientes | `GET /api/v1/ingredientes/{id}` | `consultarIngrediente` | Consultar cadastro e saldo |
| Ingredientes | `PUT /api/v1/ingredientes/{id}` | `atualizarIngrediente` | Atualizar cadastro e limite mínimo |
| Ingredientes | `DELETE /api/v1/ingredientes/{id}` | `excluirIngrediente` | Excluir se não houver composição/histórico |
| Estoque | `GET /api/v1/ingredientes/{id}/movimentacoes` | `listarMovimentacoesDoIngrediente` | Histórico de movimentações do ingrediente |
| Estoque | `GET /api/v1/movimentacoes-estoque` | `listarMovimentacoesEstoque` | Consultar livro de movimentações |
| Estoque | `POST /api/v1/movimentacoes-estoque` | `registrarMovimentacaoEstoque` | Registrar entrada ou saída |
| Produtos | `GET /api/v1/produtos` | `listarProdutos` | Listar e filtrar produtos |
| Produtos | `POST /api/v1/produtos` | `cadastrarProduto` | Cadastrar produto e composição |
| Produtos | `GET /api/v1/produtos/{id}` | `consultarProduto` | Consultar produto e composição |
| Produtos | `PUT /api/v1/produtos/{id}` | `atualizarProduto` | Atualizar dados comerciais |
| Produtos | `DELETE /api/v1/produtos/{id}` | `desativarProduto` | Desativar produto logicamente |
| Produtos | `GET /api/v1/produtos/{id}/composicao` | `consultarComposicaoProduto` | Consultar composição |
| Produtos | `PUT /api/v1/produtos/{id}/composicao` | `substituirComposicaoProduto` | Substituir composição integralmente |
| Pedidos | `GET /api/v1/pedidos` | `listarPedidos` | Listar e filtrar pedidos |
| Pedidos | `POST /api/v1/pedidos` | `registrarPedido` | Registrar pedido e baixar estoque |
| Pedidos | `GET /api/v1/pedidos/{id}` | `consultarPedido` | Consultar pedido e itens |
| Pedidos | `POST /api/v1/pedidos/{id}/cancelamento` | `cancelarPedido` | Cancelar pedido sem devolver estoque |
| Alertas | `GET /api/v1/alertas/reposicao` | `listarAlertasReposicao` | Listar ingredientes abaixo do mínimo |
| Alertas | `GET /api/v1/alertas/validade` | `listarAlertasValidade` | Listar lotes próximos do vencimento/vencidos |
| Recomendações | `POST /api/v1/recomendacoes/producao` | `calcularRecomendacaoProducao` | Otimizar quantidades de produção |
| Recomendações | `POST /api/v1/recomendacoes/reposicao` | `calcularRecomendacaoReposicao` | Recomendar compras sob orçamento |
| Marketing | `POST /api/v1/sugestoes-marketing` | `gerarSugestoesMarketing` | Gerar sugestões textuais informativas |
| Dashboard | `GET /api/v1/dashboard` | `consultarDashboard` | Consultar indicadores por período |
| Dashboard | `GET /api/v1/dashboard/exportacao` | `exportarDashboardCsv` | Exportar dados em CSV UTF-8 |

> O inventário acima é uma visão por operação; a definição normativa e completa de cada uma permanece no arquivo OpenAPI.

## 3. Contratos Pydantic — Schema-First

Antes de implementar ORM ou rotas, extraia os schemas de `components.schemas` para modelos Pydantic v2 em `src/api/schemas.py`. O contrato possui 54 schemas. Preserve os nomes JSON, campos obrigatórios/opcionais, limites, formatos, enums, exemplos e `additionalProperties: false`.

### 3.1. Erros e paginação

- `ApiErrorDetail`: `campo` (string até 100), `mensagem` (string até 500) e `valorRejeitado` (string até 500, opcional).
- `ApiError`: obrigatórios `codigo` (string até 80), `mensagem` (até 500), `detalhes` (lista de `ApiErrorDetail`), `timestamp` (`date-time`) e `caminho` (até 300); `correlationId` (até 100, opcional).
- `PageMetadata`: `page` (inteiro >= 0), `size` (inteiro entre 1 e 100), `totalElements` (inteiro >= 0) e `totalPages` (inteiro >= 0).
- Respostas paginadas seguem `{ "data": [...], "paginacao": { "page", "size", "totalElements", "totalPages" } }`. Não substitua `paginacao` por `meta` nem altere os nomes dos metadados.

### 3.2. Usuários e autenticação

- `CreateAdminDTO` e `CreateFuncionarioDTO`: `nome` (2–150), `email` (formato email, até 150) e `senha` (8–128), todos obrigatórios.
- `UpdateUsuarioDTO`: campos opcionais `nome` (2–150), `email` (formato email, até 150) e `ativo` (boolean).
- `Usuario`: `id` (inteiro positivo), `nome`, `email`, `perfil` (`ADMINISTRADOR` ou `FUNCIONARIO`) e `ativo`. Nunca inclui senha ou hash.
- `LoginDTO`: `email` e `senha` (8–128), ambos obrigatórios.
- `AuthToken`: `accessToken`, `tokenType` (enum `Bearer`), `expiresInSeconds` (inteiro >= 1) e `usuario` (`Usuario`).

### 3.3. Clientes, unidades e ingredientes

- `CreateClienteDTO` e `UpdateClienteDTO`: `nome` (2–150), `contato` (3–50) e `endereco` (3–255), todos obrigatórios. `Cliente` adiciona `id` positivo.
- `UnidadeMedida`, `CreateUnidadeMedidaDTO`: `unidadeMedida` (1–20) e `porcaoPadrao` (número entre 0.001 e 9,999,999.999). `UpdateUnidadeMedidaDTO` recebe somente `porcaoPadrao`.
- `CreateIngredienteDTO`: `nome` (2–100), `unidadeMedida` (1–20), `custoUnitario` (0–99,999,999.99), `porcaoPadrao` (0.001–9,999,999.999) e `quantidadeMinima` (0–9,999,999.999, opcional conforme `required` no schema).
- `UpdateIngredienteDTO`: mesmos campos cadastrais, incluindo `quantidadeMinima` como obrigatório.
- `Ingrediente`: `id`, `nome`, `unidadeMedida`, `custoUnitario`, `porcaoPadrao`, `quantidadeEstoque`, `quantidadeMinima` e `precisaReposicao`. O saldo é calculado a partir do estoque; não é campo editável no DTO de atualização.

### 3.4. Produtos e composição

- `ComposicaoProdutoItemDTO`: `ingredienteId` positivo e `quantidadeUtilizada` entre 0.001 e 9,999,999.999.
- `ComposicaoProdutoItem`: `ingredienteId`, `nomeIngrediente`, `unidadeMedida` e `quantidadeUtilizada`.
- `CreateProdutoDTO`: `nome` (2–100), `precoVenda` (0.01–99,999,999.99), `ativo` (boolean, conforme schema) e `composicao` (lista de itens DTO; obrigatória).
- `UpdateProdutoDTO`: `nome`, `precoVenda` e `ativo`, todos obrigatórios.
- `Produto`: `id`, `nome`, `precoVenda`, `ativo` e `composicao`.
- `ComposicaoProduto`: `produtoId` e `itens`. `SubstituirComposicaoDTO` contém `itens` obrigatórios.

### 3.5. Estoque e movimentações

- `CreateMovimentacaoEstoqueDTO`: `ingredienteId` positivo, `tipo` (`ENTRADA` ou `SAIDA`), `quantidade` positiva (0.001–9,999,999.999), `observacao` opcional (até 255), `dataValidade` opcional (`date`) e `motivo` opcional (`CONVENCIONAL` ou `DESCARTE_VENCIDO`).
- `MovimentacaoEstoque`: `id`, `ingredienteId`, `usuarioId`, `tipo`, `quantidade`, `dataMovimentacao`, além de `observacao`, `dataValidade`, `quantidadeRestante` e `motivo` (`PEDIDO`, `CONVENCIONAL` ou `DESCARTE_VENCIDO`) conforme o schema.
- Filtros de movimentação incluem `ingredienteId`, `tipo`, `dataInicio` e `dataFim`; no sub-recurso, `id`, paginação, `tipo`, `dataInicio` e `dataFim`.

### 3.6. Pedidos

- `PedidoItemDTO`: `produtoId` positivo e `quantidade` inteira entre 1 e 10.000.
- `CreatePedidoDTO`: `itens` obrigatório; `clienteId` é opcional.
- `PedidoItem`: `produtoId`, `nomeProduto`, `quantidade`, `precoUnitarioRegistrado` e `subtotal`.
- `Pedido`: `id`, `usuarioId`, `dataPedido`, `valorTotal`, `status` (`ATIVO` ou `CANCELADO`) e `itens`; `clienteId`, `dataCancelamento` e `usuarioCancelamentoId` conforme opcionais no schema.
- `CancelamentoPedidoDTO` aceita `observacao` opcional (até 255).

### 3.7. Recomendações, alertas e dashboard

- Produção: `ProducaoRecomendacaoItem` e `ProducaoRecomendacao`; `criterioOtimizacao` é `LUCRO_ESTIMADO`.
- Reposição: `CreateReposicaoDTO` exige `periodoDias` (1–365) e `orcamento` (0–99,999,999.99); resposta em `ReposicaoRecomendacao` e itens correspondentes.
- Alertas: `AlertaReposicao`, `AlertaValidade`, `ListaAlertasReposicao` e `ListaAlertasValidade`. `situacao` do alerta de validade é `PROXIMO_VENCIMENTO` ou `VENCIDO`.
- Marketing: `SugestaoMarketing` contém `geradoEm`, `sugestoes` e `observacao` opcional.
- Dashboard: `Dashboard` contém período, quantidade de pedidos, faturamento, ticket médio, produtos mais vendidos, ingredientes em reposição e linhas próximas do vencimento; `ProdutoMaisVendido` representa o ranking.
- Saúde: `HealthStatus.status` é `ok` ou `degradado`; `banco` é `ok` ou `indisponivel`.
- Exportação: `CsvFile` é binário/texto CSV UTF-8, não um objeto JSON.

## 4. Persistência relacional — SQLAlchemy 2.0

A camada `src/api/models.py` e `src/api/database.py` deve utilizar SQLAlchemy 2.0 com `Mapped`, `mapped_column`, `relationship` e chaves estrangeiras. O contrato define relações de domínio, mas não fixa nomes físicos de tabelas; os nomes abaixo são uma proposta consistente para a implementação e devem ser registrados no `PLAN.md`.

### 4.1. Entidades e relações

1. **Usuários (`usuarios`)**: ID inteiro autoincremental; nome, e-mail único, hash de senha, perfil (`ADMINISTRADOR`/`FUNCIONARIO`) e ativo. O hash e a senha nunca são serializados.
2. **Clientes (`clientes`)**: ID, nome, contato e endereço. Um cliente pode estar associado a vários pedidos; `clienteId` no pedido é opcional.
3. **Unidades (`unidades_medida`)**: chave textual `unidadeMedida` e `porcaoPadrao`. Uma unidade pode ser referenciada por vários ingredientes. Não excluir unidade em uso.
4. **Ingredientes (`ingredientes`)**: ID, nome, unidade, custo unitário, porção padrão e quantidade mínima. O saldo atual é derivado dos lotes/movimentações disponíveis.
5. **Movimentações/lotes (`movimentacoes_estoque`)**: ID, ingrediente, usuário responsável, tipo, quantidade, data de movimentação, validade, quantidade restante, observação e motivo. As entradas com validade constituem lotes consumíveis; as saídas preservam trilha de auditoria.
6. **Produtos (`produtos`)**: ID, nome, preço de venda e ativo.
7. **Composição (`composicoes_produto`)**: associação N:N entre produtos e ingredientes, com `quantidadeUtilizada` por ingrediente e produto. Use chave composta ou restrição única para impedir duplicação do mesmo ingrediente na composição, conforme decisão registrada no plano.
8. **Pedidos (`pedidos`)**: ID, cliente opcional, usuário criador, data, total, status e dados de cancelamento. Um pedido possui vários itens.
9. **Itens de pedido (`itens_pedido`)**: associação do pedido ao produto, guardando nome/preço unitário registrado, quantidade e subtotal para preservar o histórico mesmo após alteração do produto.

### 4.2. Integridade, carregamento e transações

- Configure `ForeignKey` e `relationship` para todas as relações. Defina `ondelete`, cascatas e exclusões somente após avaliar as regras de preservação histórica; não use cascata destrutiva indiscriminadamente.
- Use `selectinload`/`joinedload` para carregar itens de pedido, composição e relações necessárias sem N+1.
- Use `Decimal`/`Numeric` para dinheiro e quantidades decimais. Datas e timestamps devem manter semântica `date`/`datetime` do contrato.
- Escritas devem ser transacionais. Especialmente `POST /pedidos`, pedido e movimentações de saída precisam confirmar ou falhar em conjunto.
- O saldo disponível deve considerar somente quantidade restante de entradas válidas e a regra FEFO.

## 5. Autenticação JWT e autorização RBAC

### 5.1. Endpoints de autenticação

- `POST /api/v1/auth/administrador`: público, operação de bootstrap. Só cria o primeiro `ADMINISTRADOR`; depois que existir administrador, novas tentativas devem falhar com `409 Conflict`. A senha é armazenada somente como hash.
- `POST /api/v1/auth/login`: público. Recebe `LoginDTO` (`email`, `senha`), verifica credenciais e conta ativa e retorna `200` com `AuthToken`. Credenciais inválidas ou conta inativa devem resultar em `401`.
- O esquema de segurança publicado é `bearerAuth` (HTTP Bearer/JWT). O token deve identificar o usuário e seu perfil para autorização. `HS256` com PyJWT é a estratégia de implementação adotada; o tempo de expiração fica configurável, pois o contrato não determina duração fixa.
- Não existe `GET /api/v1/auth/me` no contrato atual. Não implemente nem documente essa rota sem alteração aprovada do OpenAPI.

### 5.2. Matriz de autorização

Todas as operações abaixo que não são explicitamente públicas declaram Bearer no OpenAPI. A descrição da operação determina a restrição de perfil:

| Operações | Acesso descrito |
|---|---|
| `GET /api/v1/saude`, `POST /api/v1/auth/administrador`, `POST /api/v1/auth/login` | Público |
| `/api/v1/usuarios` (todas as operações) | `ADMINISTRADOR` |
| `/api/v1/clientes` (todas as operações) | `ADMINISTRADOR` e `FUNCIONARIO` |
| `/api/v1/unidades-medida` (todas as operações) | `ADMINISTRADOR` |
| `/api/v1/ingredientes` (operações de cadastro/gestão) | `ADMINISTRADOR` |
| `GET /api/v1/ingredientes/{id}/movimentacoes` e `/api/v1/movimentacoes-estoque` | Exige Bearer; descrição não restringe perfil |
| `/api/v1/movimentacoes-estoque` `POST` | Exige Bearer; descrição não restringe perfil |
| `/api/v1/produtos` e `/api/v1/produtos/{id}/composicao` | `ADMINISTRADOR` |
| `/api/v1/pedidos` e `/api/v1/pedidos/{id}` e cancelamento | Exige Bearer; descrição não restringe perfil |
| `/api/v1/alertas/*` | Exige Bearer; descrição não restringe perfil |
| `/api/v1/recomendacoes/*` e `/api/v1/sugestoes-marketing` | `ADMINISTRADOR` |
| `/api/v1/dashboard` e `/api/v1/dashboard/exportacao` | `ADMINISTRADOR` |

- `401 Unauthorized`: token ausente, inválido ou expirado.
- `403 Forbidden`: usuário autenticado sem o perfil necessário.
- Não invente restrição de perfil para operações cuja descrição exige apenas autenticação.

## 6. Regras de negócio obrigatórias

### 6.1. Usuários

- A primeira conta é `ADMINISTRADOR`; o endpoint de cadastro comum sempre atribui `FUNCIONARIO` no servidor.
- Atualização de usuário não altera perfil nem credenciais; apenas `nome`, `email` e `ativo` podem ser atualizados.
- `DELETE /usuarios/{id}` é desativação lógica (`ativo=false`), preservando referências de pedidos e movimentações.

### 6.2. Clientes e unidades de medida

- Cliente pode ser associado opcionalmente ao pedido.
- Cliente referenciado por pedido não pode ser excluído; retorne `409` e preserve o histórico.
- `porcaoPadrao` de unidade serve como sugestão para novos ingredientes; atualizá-la não recalcula registros existentes.
- Unidade referenciada por ingrediente não pode ser excluída.

### 6.3. Ingredientes e estoque

- Ingrediente recém-cadastrado começa com estoque zero. A entrada inicial deve ser registrada por movimentação `ENTRADA`.
- O saldo é derivado das entradas ainda disponíveis. Não altere `quantidadeEstoque` diretamente.
- `ENTRADA`: cria lote com `quantidadeRestante` inicial igual a `quantidade` e validade opcional.
- `SAIDA`: consome lotes não vencidos em ordem FEFO (First Expire, First Out); não consome estoque vencido.
- O motivo da movimentação pode ser `CONVENCIONAL` ou `DESCARTE_VENCIDO` na entrada DTO; saídas automáticas de pedidos usam `PEDIDO`.
- Ingrediente com composição ou histórico de movimentação não pode ser excluído.

### 6.4. Produtos e composição

- Produto exige composição com ao menos um ingrediente existente e quantidades positivas.
- Atualização comercial altera nome, preço e disponibilidade; não reescreve preço histórico dos itens de pedidos já registrados.
- `DELETE /produtos/{id}` é desativação lógica (`ativo=false`).
- A substituição de composição é integral e deve validar existência de todos os ingredientes e quantidades positivas.

### 6.5. Pedidos e cancelamento

- `POST /pedidos` recebe um ou mais itens; `usuarioId` vem do token.
- O backend captura os preços vigentes, calcula subtotal/total, valida estoque válido e gera as saídas com motivo `PEDIDO`.
- Persistência do pedido, itens e movimentações deve ser atômica.
- Cancelamento altera status para `CANCELADO` e registra data e usuário responsável. Não devolve estoque automaticamente.
- Pedidos cancelados permanecem consultáveis, mas são excluídos de faturamento, ticket médio e ranking do dashboard.

### 6.6. Alertas, recomendações, marketing e dashboard

- Alerta de reposição considera saldo válido abaixo da quantidade mínima.
- Alerta de validade considera lotes de entrada com validade informada; pode incluir próximos do vencimento e vencidos.
- Recomendação de produção usa Programação Linear Inteira, quantidades inteiras e maximização do lucro estimado (preço de venda menos custo dos ingredientes), respeitando estoque válido. É calculada sob demanda e não persiste histórico.
- Recomendação de reposição considera período de consumo e orçamento máximo; também é sob demanda e não persiste histórico.
- Sugestões de marketing são informativas, não publicadas automaticamente e sem histórico persistido no modelo atual.
- Dashboard agrega o período informado e considera apenas pedidos `ATIVO` nos indicadores financeiros.
- Exportação deve gerar CSV UTF-8 e aplicar as mesmas regras de período e inclusão de pedidos ativos.

## 7. Parâmetros, paginação e respostas

- IDs `{id}`: inteiro `int32`, mínimo 1.
- `{unidadeMedida}`: string de 1 a 20 caracteres.
- Paginação: `page` >= 0, padrão 0; `size` de 1 a 100, padrão 20; `sort` no formato `campo,direção`.
- Busca textual `q`: até 100 caracteres.
- Filtros específicos devem ser extraídos diretamente dos parâmetros de cada operação OpenAPI; não aplique filtros globais a todos os recursos.
- Respostas paginadas usam `data` e `paginacao` (`page`, `size`, `totalElements`, `totalPages`).
- Operações `204` não retornam corpo. A exportação do dashboard retorna CSV, não JSON.

## 8. Tratamento de erros

Todas as respostas de erro JSON devem seguir `components.schemas.ApiError`:

```json
{
  "codigo": "VALIDATION_ERROR",
  "mensagem": "A requisição contém dados que não atendem às regras de validação.",
  "detalhes": [
    {
      "campo": "precoVenda",
      "mensagem": "Deve ser maior que zero.",
      "valorRejeitado": "0.00"
    }
  ],
  "timestamp": "2026-11-04T14:00:00-03:00",
  "caminho": "/api/v1/produtos",
  "correlationId": "7c8b4fb3-9da1-4baf-9f7d-3f2f0b7a0d2a"
}
```

- `detalhes` pode ser vazio; em validação, deve identificar os campos rejeitados.
- Use os componentes de resposta definidos no OpenAPI: `BadRequest`, `Unauthorized`, `Forbidden`, `NotFound`, `Conflict`, `ValidationError`, `InternalError` e `ServiceUnavailable`.
- Respeite o status documentado por operação. `503` representa indisponibilidade temporária de otimização/dependência.
- Não use o formato RFC 9457 antigo com `type`, `title`, `status`, `instance` e `invalidParams`: ele não corresponde ao schema atual `ApiError`.

## 9. Estratégia de testes e critérios de aceite

1. **Contrato:** validar os 26 caminhos, métodos, `operationId`, schemas, parâmetros, códigos de resposta e segurança contra o OpenAPI.
2. **Schemas:** testar obrigatoriedade, limites, formatos, enums, arrays e objetos fechados dos DTOs.
3. **Auth/RBAC:** bootstrap de administrador único; login válido/inválido; conta inativa; token ausente/inválido/expirado (`401`); papel insuficiente (`403`); cadastro de funcionário sempre com perfil `FUNCIONARIO`.
4. **CRUD e integridade:** usuários, clientes, unidades, ingredientes e produtos; referências inexistentes (`404`); conflito por dependência (`409`); exclusão lógica quando definida.
5. **Estoque:** entrada, saída, saldo derivado, FEFO, validade, bloqueio de consumo vencido, quantidade restante e auditoria do usuário.
6. **Produtos:** composição válida, ingredientes inexistentes, quantidades positivas e substituição integral.
7. **Pedidos:** cálculo de preços históricos, total, estoque insuficiente, transação atômica, cancelamento e ausência de devolução automática.
8. **Relatórios:** alertas, recomendações, indisponibilidade `503`, dashboard sem pedidos cancelados e CSV UTF-8.
9. **Erros:** validar envelope `ApiError` em `400`, `401`, `403`, `404`, `409`, `422`, `503` e erros internos tratados.
10. **Isolamento:** usar SQLite isolado por teste, fixtures determinísticas e rollback/limpeza para não contaminar casos.

Só marque uma etapa como concluída em `PLAN.md` após executar e verificar seus critérios de aceite.
