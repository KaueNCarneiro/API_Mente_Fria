# ruff: noqa: BLE001, DTZ001  -- script auxiliar: exceções amplas e datetime ingênuo são intencionais
"""Verificação prática da Fase 3 (ORM + banco) — Mente Fria API.

NÃO é a suíte definitiva da Fase 6. Executa, em SQLite em memória, as conferências de
modelos, relacionamentos, constraints, sessão/``get_db``, isolamento de banco e
compatibilidade com os schemas Pydantic. Uso, na raiz do repositório:

    python verify_models.py
"""

from __future__ import annotations

import os
import sys
import threading
import warnings
from datetime import UTC, date, datetime, timedelta
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

from pydantic import ValidationError
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session, configure_mappers

from src.api import database as db
from src.api import models as M
from src.api import schemas as S
from src.api.config import Settings

OK = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global OK, FAIL
    if cond:
        OK += 1
    else:
        FAIL += 1
        print(f"  FALHOU: {name} {detail}")


def raises(exc: type[BaseException], fn) -> bool:
    try:
        fn()
    except exc:
        return True
    except Exception as e:
        print(f"    (exceção inesperada: {type(e).__name__}: {e})")
        return False
    return False


def fresh() -> tuple[object, Session]:
    engine = db.create_db_engine(db.get_settings())
    db.init_db(engine)
    return engine, db.SessionLocal(bind=engine)


def seed_base(s: Session) -> dict[str, object]:
    """Grafo mínimo válido reutilizado pelas verificações."""
    u = M.UsuarioModel(nome="Ana", email="ana@x.com", senha_hash="$argon2id$fake", perfil="ADMINISTRADOR")
    u2 = M.UsuarioModel(nome="Bia", email="bia@x.com", senha_hash="$argon2id$fake2", perfil="FUNCIONARIO")
    c = M.ClienteModel(nome="Cli", contato="1199", endereco="Rua A")
    un = M.UnidadeMedidaModel(unidadeMedida="g", porcaoPadrao=Decimal("100.000"))
    s.add_all([u, u2, c, un])
    s.flush()
    ing = M.IngredienteModel(nome="Açaí", unidadeMedida="g", custoUnitario=Decimal("12.50"), porcaoPadrao=Decimal("100.000"), quantidadeMinima=Decimal("15.000"))
    s.add(ing)
    s.flush()
    p = M.ProdutoModel(nome="Copo", precoVenda=Decimal("19.90"))
    p.composicao = [M.ComposicaoProdutoModel(ingredienteId=ing.id, quantidadeUtilizada=Decimal("0.250"))]
    s.add(p)
    s.flush()
    ped = M.PedidoModel(clienteId=c.id, usuarioId=u.id, valorTotal=Decimal("39.80"))
    ped.itens = [M.PedidoItemModel(produtoId=p.id, nomeProduto=p.nome, quantidade=2, precoUnitarioRegistrado=Decimal("19.90"), subtotal=Decimal("39.80"))]
    s.add(ped)
    s.commit()
    return {"u": u, "u2": u2, "c": c, "un": un, "ing": ing, "p": p, "ped": ped}


def main() -> int:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run()
    sa_warn = sorted({str(w.message)[:110] for w in caught if "sqlalchemy" in str(w.filename).lower() or "Decimal" in str(w.message)})
    print(f"\nAvisos do SQLAlchemy/Decimal capturados: {len(sa_warn)}")
    for w in sa_warn:
        print("  -", w)
    print(f"\nResultado: {OK} verificações OK, {FAIL} falhas")
    return 1 if FAIL else 0


def run() -> None:
    # 1 e 2 — importação, tabelas, ausência de saldo editável ---------------------------
    print("[1-2] importação e tabelas")
    configure_mappers()
    esperadas = {"usuarios", "clientes", "unidades_medida", "ingredientes", "movimentacoes_estoque", "produtos", "composicoes_produto", "pedidos", "itens_pedido"}
    check("9 tabelas reconhecidas pelo Base", set(M.Base.metadata.tables) == esperadas, str(set(M.Base.metadata.tables) ^ esperadas))
    cols_ing = {c.name for c in M.IngredienteModel.__table__.columns}
    check("ingredientes sem coluna de saldo", not (cols_ing & {"quantidade_estoque", "saldo", "saldo_valido", "estoque"}), str(cols_ing))
    check("senha em texto claro inexistente", all("senha" not in c.name or c.name == "senha_hash" for t in M.Base.metadata.tables.values() for c in t.columns))
    check("Numeric (não Float) em dinheiro/quantidades", all(type(M.Base.metadata.tables[t].c[c].type).__name__ == "Numeric" for t, c in [("produtos", "preco_venda"), ("ingredientes", "custo_unitario"), ("ingredientes", "porcao_padrao"), ("movimentacoes_estoque", "quantidade"), ("pedidos", "valor_total"), ("itens_pedido", "subtotal"), ("composicoes_produto", "quantidade_utilizada")]))

    # 3 — FKs / relacionamentos ---------------------------------------------------------
    print("[3] FKs e relacionamentos")
    fks = {(t.name, fk.parent.name, fk.column.table.name, fk.ondelete) for t in M.Base.metadata.tables.values() for fk in t.foreign_keys}
    esperado_fk = {
        ("ingredientes", "unidade_medida", "unidades_medida", "RESTRICT"),
        ("movimentacoes_estoque", "ingrediente_id", "ingredientes", "RESTRICT"),
        ("movimentacoes_estoque", "usuario_id", "usuarios", "RESTRICT"),
        ("composicoes_produto", "produto_id", "produtos", "CASCADE"),
        ("composicoes_produto", "ingrediente_id", "ingredientes", "RESTRICT"),
        ("pedidos", "cliente_id", "clientes", "RESTRICT"),
        ("pedidos", "usuario_id", "usuarios", "RESTRICT"),
        ("pedidos", "usuario_cancelamento_id", "usuarios", "RESTRICT"),
        ("itens_pedido", "pedido_id", "pedidos", "RESTRICT"),
        ("itens_pedido", "produto_id", "produtos", "RESTRICT"),
    }
    check("10 FKs com ondelete esperado", fks == esperado_fk, str(fks ^ esperado_fk))
    check("nenhuma FK com CASCADE em histórico", all(od != "CASCADE" or t == "composicoes_produto" for t, _, _, od in fks))
    check("nenhuma FK com SET NULL", all(od != "SET NULL" for *_, od in fks))
    for mapper in M.Base.registry.mappers:
        for rel in mapper.relationships:
            check(f"{mapper.class_.__name__}.{rel.key} resolve", rel.mapper is not None)
            if rel.direction.name == "ONETOMANY" and mapper.class_ is not M.ProdutoModel or rel.key == "itensPedido":
                check(f"{mapper.class_.__name__}.{rel.key} sem cascade destrutivo", "delete" not in rel.cascade and rel.passive_deletes == "all", str(rel.cascade))
    check("Produto.composicao é delete-orphan", "delete-orphan" in M.ProdutoModel.composicao.property.cascade)

    # 7 (parte) — persistência e grafo completo --------------------------------------------
    print("[7] persistência")
    engine, s = fresh()
    g = seed_base(s)
    ing, p, ped, u, u2, c, un = (g[k] for k in ("ing", "p", "ped", "u", "u2", "c", "un"))
    insp = inspect(engine)
    check("tabelas criadas no SQLite", set(insp.get_table_names()) == esperadas)
    check("grafo persistido e relido", s.scalar(select(M.PedidoModel).where(M.PedidoModel.id == ped.id)).itens[0].nomeProduto == "Copo")
    check("IDs autoincrementais", (u.id, u2.id) == (1, 2))
    s.expire_all()
    p2 = s.get(M.ProdutoModel, p.id)
    check("Decimal preservado (preço)", p2.precoVenda == Decimal("19.90") and isinstance(p2.precoVenda, Decimal))
    check("Decimal preservado (quantidade 3 casas)", p2.composicao[0].quantidadeUtilizada == Decimal("0.250"))
    extremo = M.IngredienteModel(nome="X", unidadeMedida="g", custoUnitario=Decimal("99999999.99"), porcaoPadrao=Decimal("9999999.999"), quantidadeMinima=Decimal("9999999.999"))
    s.add(extremo); s.commit(); s.refresh(extremo)
    check("valores nos limites do contrato sem perda", (extremo.custoUnitario, extremo.porcaoPadrao) == (Decimal("99999999.99"), Decimal("9999999.999")))
    ped_grande = M.PedidoModel(usuarioId=u.id, valorTotal=Decimal("999999999999.99"))
    s.add(ped_grande); s.commit(); s.refresh(ped_grande)
    check("valorTotal grande sem perda de centavos", ped_grande.valorTotal == Decimal("999999999999.99"))
    sem_minimo = M.IngredienteModel(nome="Y", unidadeMedida="g", custoUnitario=Decimal(1), porcaoPadrao=Decimal(1))
    s.add(sem_minimo); s.commit()
    check("quantidadeMinima omitida assume zero", sem_minimo.quantidadeMinima == Decimal(0))
    check("quantidadeMinima informada é preservada", s.get(M.IngredienteModel, extremo.id).quantidadeMinima == Decimal("9999999.999"))

    # datas e fusos
    ts = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
    m = M.MovimentacaoEstoqueModel(ingredienteId=ing.id, usuarioId=u.id, tipo="ENTRADA", quantidade=Decimal(1), quantidadeRestante=Decimal(1), dataValidade=date(2030, 1, 1), dataMovimentacao=ts)
    s.add(m); s.commit(); s.refresh(m)
    check("datetime volta com fuso de São Paulo (-03:00)", m.dataMovimentacao.utcoffset() == timedelta(hours=-3) and m.dataMovimentacao == ts, str(m.dataMovimentacao))
    check("date permanece date", type(m.dataValidade) is date and m.dataValidade == date(2030, 1, 1))
    check("datetime default (agora) com fuso", s.get(M.PedidoModel, ped.id).dataPedido.tzinfo is not None)
    check("datetime sem fuso é recusado", raises(StatementError, lambda: (s.add(M.PedidoModel(usuarioId=u.id, valorTotal=Decimal(1), dataPedido=datetime(2026, 1, 1))), s.commit())))
    s.rollback()

    # saldo derivado
    print("[7] saldo derivado")
    _, s = fresh()
    g = seed_base(s)
    ing, u = g["ing"], g["u"]
    hoje = M.hoje()
    def entrada(qtd: str, rest: str, validade: date | None) -> None:
        s.add(M.MovimentacaoEstoqueModel(ingredienteId=ing.id, usuarioId=u.id, tipo="ENTRADA", quantidade=Decimal(qtd), quantidadeRestante=Decimal(rest), dataValidade=validade))
    s.refresh(ing)
    check("ingrediente novo: estoque 0 e precisa reposição", ing.quantidadeEstoque == 0 and ing.saldoValido == 0 and ing.precisaReposicao is True)
    entrada("10", "10", None)
    entrada("5", "5", hoje - timedelta(days=1))   # vencido
    entrada("4", "4", hoje + timedelta(days=3))   # válido
    entrada("2", "2", hoje)                       # vence hoje: ainda válido
    s.add(M.MovimentacaoEstoqueModel(ingredienteId=ing.id, usuarioId=u.id, tipo="SAIDA", quantidade=Decimal(3), motivo="CONVENCIONAL"))
    s.commit()
    s.refresh(ing)
    check("quantidadeEstoque = soma das entradas (inclui vencidas; ignora saídas)", ing.quantidadeEstoque == Decimal(21), str(ing.quantidadeEstoque))
    check("saldoValido exclui vencidos", ing.saldoValido == Decimal(16), str(ing.saldoValido))
    check("precisaReposicao falso (16 >= 15)", ing.precisaReposicao is False)
    lote = s.scalar(select(M.MovimentacaoEstoqueModel).where(M.MovimentacaoEstoqueModel.quantidade == 10))
    lote.quantidadeRestante = Decimal(8); s.commit(); s.refresh(ing)
    check("saldo acompanha quantidadeRestante e reabre precisaReposicao", ing.saldoValido == Decimal(14) and ing.precisaReposicao is True, str(ing.saldoValido))
    check("saldo é somente leitura (sem coluna)", "quantidadeEstoque" not in {c.key for c in inspect(M.IngredienteModel).columns if c.table is M.IngredienteModel.__table__})

    # 4 — constraints e integridade ------------------------------------------------------
    print("[4] constraints e integridade")
    _, s = fresh()
    g = seed_base(s)
    ing, p, ped, u, c, un = (g[k] for k in ("ing", "p", "ped", "u", "c", "un"))
    def commit_fails(*objs: object) -> bool:
        ok = raises(IntegrityError, lambda: (s.add_all(objs), s.commit()))
        s.rollback()
        return ok
    def delete_fails(obj: object) -> bool:
        ok = raises(IntegrityError, lambda: (s.delete(obj), s.commit()))
        s.rollback()
        return ok
    check("e-mail único", commit_fails(M.UsuarioModel(nome="Z", email="ana@x.com", senha_hash="h", perfil="FUNCIONARIO")))
    check("perfil limitado (ADMIN/MEMBER recusados)", commit_fails(M.UsuarioModel(nome="Z", email="z@x.com", senha_hash="h", perfil="ADMIN")) and commit_fails(M.UsuarioModel(nome="Z", email="z2@x.com", senha_hash="h", perfil="MEMBER")))
    check("usuário ativo por padrão", s.get(M.UsuarioModel, u.id).ativo is True)
    check("ingrediente duplicado na composição (chave composta)", commit_fails(M.ComposicaoProdutoModel(produtoId=p.id, ingredienteId=ing.id, quantidadeUtilizada=Decimal(1))))
    check("FK: ingrediente com unidade inexistente", commit_fails(M.IngredienteModel(nome="Q", unidadeMedida="zz", custoUnitario=Decimal(1), porcaoPadrao=Decimal(1))))
    check("FK: pedido com cliente inexistente", commit_fails(M.PedidoModel(clienteId=999, usuarioId=u.id, valorTotal=Decimal(1))))
    check("pedido sem cliente é permitido", (s.add(M.PedidoModel(usuarioId=u.id, valorTotal=Decimal(1))), s.commit()) is not None)
    check("unidade em uso não pode ser excluída", delete_fails(un))
    check("cliente com pedido não pode ser excluído", delete_fails(c))
    check("ingrediente com composição não pode ser excluído", delete_fails(ing))
    check("produto com itens de pedido não pode ser excluído", delete_fails(p))
    check("usuário com pedidos não pode ser excluído", delete_fails(u))
    check("pedido com itens não pode ser excluído (itens preservados)", delete_fails(ped) and s.scalar(select(M.PedidoItemModel).limit(1)) is not None)
    mv = M.MovimentacaoEstoqueModel(ingredienteId=g["u2"].id and ing.id, usuarioId=g["u2"].id, tipo="ENTRADA", quantidade=Decimal(1), quantidadeRestante=Decimal(1))
    s.add(mv); s.commit()
    ing2 = M.IngredienteModel(nome="Sem uso", unidadeMedida="g", custoUnitario=Decimal(1), porcaoPadrao=Decimal(1)); s.add(ing2); s.commit()
    s.add(M.MovimentacaoEstoqueModel(ingredienteId=ing2.id, usuarioId=g["u2"].id, tipo="ENTRADA", quantidade=Decimal(1), quantidadeRestante=Decimal(1))); s.commit()
    check("ingrediente com histórico de movimentação não pode ser excluído", delete_fails(ing2))
    check("usuário com movimentações não pode ser excluído", delete_fails(g["u2"]))
    # checks de domínio
    check("CHECK: quantidade < 0.001 recusada", commit_fails(M.MovimentacaoEstoqueModel(ingredienteId=ing.id, usuarioId=u.id, tipo="ENTRADA", quantidade=Decimal(0), quantidadeRestante=Decimal(0))))
    check("CHECK: SAIDA com quantidadeRestante recusada", commit_fails(M.MovimentacaoEstoqueModel(ingredienteId=ing.id, usuarioId=u.id, tipo="SAIDA", quantidade=Decimal(1), quantidadeRestante=Decimal(1))))
    check("CHECK: ENTRADA sem quantidadeRestante recusada", commit_fails(M.MovimentacaoEstoqueModel(ingredienteId=ing.id, usuarioId=u.id, tipo="ENTRADA", quantidade=Decimal(1))))
    check("CHECK: restante > quantidade recusado", commit_fails(M.MovimentacaoEstoqueModel(ingredienteId=ing.id, usuarioId=u.id, tipo="ENTRADA", quantidade=Decimal(1), quantidadeRestante=Decimal(2))))
    check("CHECK: tipo/motivo inválidos recusados", commit_fails(M.MovimentacaoEstoqueModel(ingredienteId=ing.id, usuarioId=u.id, tipo="AJUSTE", quantidade=Decimal(1))) and commit_fails(M.MovimentacaoEstoqueModel(ingredienteId=ing.id, usuarioId=u.id, tipo="SAIDA", quantidade=Decimal(1), motivo="OUTRO")))
    check("CHECK: preço de produto < 0.01 recusado", commit_fails(M.ProdutoModel(nome="Z", precoVenda=Decimal(0))))
    check("CHECK: item com quantidade 0 / 10001 recusado", commit_fails(M.PedidoItemModel(pedidoId=ped.id, produtoId=p.id, nomeProduto="x", quantidade=0, precoUnitarioRegistrado=Decimal(1), subtotal=Decimal(0))) and commit_fails(M.PedidoItemModel(pedidoId=ped.id, produtoId=p.id, nomeProduto="x", quantidade=10001, precoUnitarioRegistrado=Decimal(1), subtotal=Decimal(1))))
    check("CHECK: status inválido recusado", commit_fails(M.PedidoModel(usuarioId=u.id, valorTotal=Decimal(1), status="PENDENTE")))
    check("CHECK: ATIVO com dados de cancelamento recusado", commit_fails(M.PedidoModel(usuarioId=u.id, valorTotal=Decimal(1), status="ATIVO", usuarioCancelamentoId=u.id, dataCancelamento=M.agora())))
    check("CHECK: CANCELADO sem data/usuário recusado", commit_fails(M.PedidoModel(usuarioId=u.id, valorTotal=Decimal(1), status="CANCELADO")))
    canc = M.PedidoModel(usuarioId=u.id, valorTotal=Decimal(5), status="CANCELADO", dataCancelamento=M.agora(), usuarioCancelamentoId=u.id, observacaoCancelamento="erro")
    s.add(canc); s.commit()
    check("pedido CANCELADO coerente é aceito", s.get(M.PedidoModel, canc.id).usuarioCancelamentoId == u.id)
    # histórico preservado após alteração/desativação do produto
    p = s.get(M.ProdutoModel, p.id)
    p.nome = "Copo Premium"; p.precoVenda = Decimal("25.00"); p.ativo = False; s.commit(); s.expire_all()
    item = s.get(M.PedidoModel, ped.id).itens[0]
    check("item preserva nome/preço após alterar e desativar produto", (item.nomeProduto, item.precoUnitarioRegistrado, item.subtotal) == ("Copo", Decimal("19.90"), Decimal("39.80")))
    usuario = s.get(M.UsuarioModel, u.id); usuario.ativo = False; s.commit()
    check("desativação lógica de usuário preserva pedidos/movimentações", s.get(M.PedidoModel, ped.id).usuarioId == u.id)
    # substituição integral da composição (delete-orphan) e cascata só na composição
    ing3 = M.IngredienteModel(nome="Leite", unidadeMedida="g", custoUnitario=Decimal(2), porcaoPadrao=Decimal(1)); s.add(ing3); s.commit()
    p.composicao = [M.ComposicaoProdutoModel(ingredienteId=ing3.id, quantidadeUtilizada=Decimal("1.500"))]; s.commit(); s.expire_all()
    check("composição substituída integralmente", [x.ingredienteId for x in s.get(M.ProdutoModel, p.id).composicao] == [ing3.id])
    novo = M.ProdutoModel(nome="Temp", precoVenda=Decimal(1)); novo.composicao = [M.ComposicaoProdutoModel(ingredienteId=ing3.id, quantidadeUtilizada=Decimal(1))]
    s.add(novo); s.commit(); nid = novo.id
    s.delete(novo); s.commit()
    check("excluir produto sem histórico remove só a composição", s.scalar(select(M.ComposicaoProdutoModel).where(M.ComposicaoProdutoModel.produtoId == nid)) is None)
    check("PRAGMA foreign_keys ativo na conexão", s.execute(text("PRAGMA foreign_keys")).scalar() == 1)

    # 5 — sessão e get_db ---------------------------------------------------------------
    print("[5] sessão e get_db")
    db.get_engine.cache_clear()
    gen = db.get_db()
    sess = next(gen)
    check("get_db é gerador", hasattr(gen, "send"))
    check("get_db entrega Session com bind SQLite", isinstance(sess, Session) and sess.get_bind().dialect.name == "sqlite")
    db.init_db()
    sess.execute(select(1)).scalar()
    check("sessão aberta em transação durante a requisição", sess.in_transaction())
    sess.add(M.ClienteModel(nome="Pendente", contato="123", endereco="Rua"))  # sem commit
    sess.flush()
    gen.close()
    check("get_db encerra a sessão (transação descartada)", not sess.in_transaction())
    check("escrita sem commit não persiste", db.SessionLocal(bind=db.get_engine()).scalar(select(M.ClienteModel)) is None)
    gen2 = db.get_db(); s2 = next(gen2)
    check("get_db fecha a sessão também em exceção", raises(RuntimeError, lambda: gen2.throw(RuntimeError("falha na requisição"))) and not s2.in_transaction())
    out: list[int | str] = []
    def worker() -> None:
        try:
            with db.SessionLocal(bind=db.get_engine()) as other:
                out.append(other.execute(text("select count(*) from usuarios")).scalar() or 0)
        except Exception as e:
            out.append(repr(e))
    t = threading.Thread(target=worker); t.start(); t.join()
    check("SQLite usável de outra thread (check_same_thread=False + StaticPool)", out == [0], str(out))

    # 6 — isolamento dev x teste ---------------------------------------------------------
    print("[6] isolamento local x teste")
    base = {"_env_file": None, "jwt_secret_key": "x", "jwt_access_token_expire_seconds": 60}
    st = Settings(env="test", **base)
    check("teste usa SQLite em memória", st.database_url == "sqlite:///:memory:")
    check("teste recusa o banco de desenvolvimento", raises(ValidationError, lambda: Settings(env="test", database_url="sqlite:///./mente_fria.db", **base)))
    sl = Settings(env="local", **base)
    check("local usa arquivo mente_fria.db", sl.database_url == "sqlite:///./mente_fria.db")
    e1, e2 = db.create_db_engine(st), db.create_db_engine(st)
    db.init_db(e1, st)
    check("dois bancos de teste são independentes", "usuarios" in inspect(e1).get_table_names() and "usuarios" not in inspect(e2).get_table_names())
    check("nenhum arquivo mente_fria.db criado", not Path("mente_fria.db").exists())
    prod = Settings(env="production", database_url="sqlite:///./prod.db", **{**base, "jwt_secret_key": "k" * 40})
    check("init_db recusada em production", raises(RuntimeError, lambda: db.init_db(db.create_db_engine(Settings(env="test", **base)), prod)))
    check("importar database.py não exige Engine/Settings (lazy)", "get_engine" in dir(db) and db.SessionLocal.kw.get("bind") is None)

    # seed ---------------------------------------------------------------------------------
    print("[7] seed")
    eng = db.create_db_engine(st); db.init_db(eng, st)
    with db.SessionLocal(bind=eng) as ss:
        check("seed padrão não insere nada (sem lista aprovada)", db.seed_reference_data(ss) == 0 and ss.scalar(select(M.UnidadeMedidaModel)) is None)
        check("seed não cria usuários", ss.scalar(select(M.UsuarioModel)) is None)
        dados = [("kg", Decimal("1.000")), ("ml", Decimal("100.000"))]
        check("seed idempotente: 1ª execução cria", db.seed_reference_data(ss, dados) == 2)
        check("seed idempotente: 2ª execução não duplica", db.seed_reference_data(ss, dados) == 0 and len(ss.scalars(select(M.UnidadeMedidaModel)).all()) == 2)
        ss.get(M.UnidadeMedidaModel, "kg").porcaoPadrao = Decimal("2.000"); ss.commit()
        db.seed_reference_data(ss, dados)
        check("seed não sobrescreve edição posterior", ss.get(M.UnidadeMedidaModel, "kg").porcaoPadrao == Decimal("2.000"))
    check("sem referência a ADMIN/MEMBER/aluno/admin@fatec no módulo", not any(t in Path("src/api/database.py").read_text().lower().replace("administrador", "") for t in ("admin@fatec", "aluno@fatec", "'member'", '"member"')))

    # 8 — compatibilidade com schemas ------------------------------------------------------
    print("[8] compatibilidade com schemas Pydantic")
    _, s = fresh()
    g = seed_base(s)
    ing, p, ped, u, c, un = (g[k] for k in ("ing", "p", "ped", "u", "c", "un"))
    s.add(M.MovimentacaoEstoqueModel(ingredienteId=ing.id, usuarioId=u.id, tipo="ENTRADA", quantidade=Decimal(20), quantidadeRestante=Decimal(20), dataValidade=M.hoje() + timedelta(days=5), observacao="lote 1"))
    s.add(M.MovimentacaoEstoqueModel(ingredienteId=ing.id, usuarioId=u.id, tipo="SAIDA", quantidade=Decimal(1), motivo="PEDIDO"))
    s.commit(); s.expire_all()
    pares = {
        S.Usuario: M.UsuarioModel, S.Cliente: M.ClienteModel, S.UnidadeMedida: M.UnidadeMedidaModel,
        S.Ingrediente: M.IngredienteModel, S.MovimentacaoEstoque: M.MovimentacaoEstoqueModel,
        S.Produto: M.ProdutoModel, S.Pedido: M.PedidoModel, S.PedidoItem: M.PedidoItemModel,
        S.ComposicaoProdutoItem: M.ComposicaoProdutoModel,
    }
    for schema, model in pares.items():
        faltando = [f for f in schema.model_fields if not hasattr(model, f)]
        check(f"{schema.__name__}: todos os campos existem em {model.__name__}", not faltando, str(faltando))
    um = S.Usuario.model_validate(u)
    check("Usuario validado sem senha/hash", set(um.model_dump()) == {"id", "nome", "email", "perfil", "ativo"} and "argon2" not in um.model_dump_json() and "senha" not in repr(u).lower())
    S.Cliente.model_validate(c)
    um_ = S.UnidadeMedida.model_validate(un)
    check("UnidadeMedida.porcaoPadrao Decimal", um_.porcaoPadrao == Decimal(100))
    ig = S.Ingrediente.model_validate(s.get(M.IngredienteModel, ing.id))
    check("Ingrediente: saldo derivado e precisaReposicao via from_attributes", ig.quantidadeEstoque == Decimal(20) and ig.precisaReposicao is False and ig.unidadeMedida == "g", f"{ig}")
    mvs = [S.MovimentacaoEstoque.model_validate(x) for x in s.scalars(select(M.MovimentacaoEstoqueModel))]
    check("MovimentacaoEstoque (ENTRADA e SAIDA) validam", len(mvs) == 2 and any(x.tipo == "SAIDA" and x.quantidadeRestante is None for x in mvs))
    pr = S.Produto.model_validate(s.get(M.ProdutoModel, p.id))
    check("Produto com composição aninhada (nomeIngrediente/unidadeMedida derivados)", pr.composicao[0].nomeIngrediente == "Açaí" and pr.composicao[0].unidadeMedida == "g")
    pd = S.Pedido.model_validate(s.get(M.PedidoModel, ped.id))
    check("Pedido com itens, status e datas validam", pd.status == "ATIVO" and pd.itens[0].subtotal == Decimal("39.80") and pd.dataPedido.tzinfo is not None and pd.clienteId == c.id)
    j = pd.model_dump_json()
    check("JSON mantém nomes do contrato e Decimal numérico", '"valorTotal":39.8' in j and '"precoUnitarioRegistrado":19.9' in j and '"dataPedido"' in j, j[:120])
    sem_cliente = M.PedidoModel(usuarioId=u.id, valorTotal=Decimal("1.00")); sem_cliente.itens = [M.PedidoItemModel(produtoId=p.id, nomeProduto="Copo", quantidade=1, precoUnitarioRegistrado=Decimal("1.00"), subtotal=Decimal("1.00"))]
    s.add(sem_cliente); s.commit(); s.refresh(sem_cliente)
    check("Pedido sem cliente valida (clienteId nulo)", S.Pedido.model_validate(sem_cliente).clienteId is None)


if __name__ == "__main__":
    sys.exit(main())