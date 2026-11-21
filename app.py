"""Sistema de Oficina – Passo 2
Módulos: Clientes, Produtos, Estoque, Gerar OS e Consultar OS.
Tecnologias: Streamlit + SQLite (o banco é o arquivo oficina.db, criado sozinho).

Para rodar:
    pip install -r requirements.txt
    streamlit run app.py

Se você já usava o banco do Passo 1, basta manter o oficina.db na mesma pasta:
o sistema atualiza a estrutura sozinho e preserva os dados.
"""
import html
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ============================================================ CONFIGURAÇÕES
EMPRESA = "NOME DA SUA EMPRESA"   # aparece no cabeçalho da Ordem de Serviço
ANO_OS = 2027                     # prefixo da numeração: 2027.001, 2027.002, ...
LIMITE_ALERTA = 2                 # quantidade de 1 até este valor = "Alerta de estoque"
SERVICO = "mão de obra"           # produto com esta descrição é serviço: sem controle de estoque
DB_PATH = Path(__file__).with_name("oficina.db")

UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
       "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
       "SP", "SE", "TO"]
PLACA_RE = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")  # ABC1234 ou ABC1D23

SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    cpf TEXT PRIMARY KEY, nome TEXT NOT NULL, sobrenome TEXT NOT NULL,
    rua TEXT NOT NULL, bairro TEXT NOT NULL, cidade TEXT NOT NULL, uf TEXT NOT NULL,
    placa TEXT NOT NULL, fabricante TEXT NOT NULL, modelo TEXT, nota INTEGER,
    codigo TEXT
);
CREATE TABLE IF NOT EXISTS produtos (
    sku TEXT PRIMARY KEY, part_number TEXT NOT NULL, descricao TEXT NOT NULL UNIQUE,
    aplicacao TEXT, quantidade INTEGER NOT NULL DEFAULT 0,
    custo_unit REAL NOT NULL DEFAULT 0, frete REAL NOT NULL DEFAULT 0,
    markup REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ordens (
    numero TEXT PRIMARY KEY, data TEXT NOT NULL,
    cpf TEXT, nome TEXT, sobrenome TEXT, rua TEXT, bairro TEXT, cidade TEXT, uf TEXT,
    placa TEXT, fabricante TEXT, modelo TEXT, observacoes TEXT, cliente_codigo TEXT
);
CREATE TABLE IF NOT EXISTS os_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT, os_numero TEXT NOT NULL,
    sku TEXT, part_number TEXT, descricao TEXT, quantidade INTEGER, preco_unit REAL
);
CREATE TABLE IF NOT EXISTS movimentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL,
    sku TEXT NOT NULL, descricao TEXT, tipo TEXT NOT NULL,
    quantidade INTEGER NOT NULL, saldo INTEGER NOT NULL,
    origem TEXT, observacao TEXT
);
"""


# ============================================================ BANCO DE DADOS
def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def eh_servico(descricao):
    return (descricao or "").strip().lower() == SERVICO


def _tem_coluna(con, tabela, coluna):
    return any(r[1] == coluna for r in con.execute(f"PRAGMA table_info({tabela})"))


def init_db():
    """Cria as tabelas e atualiza bancos antigos (Passo 1) sem perder dados."""
    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(SCHEMA)
        with con:
            if not _tem_coluna(con, "clientes", "codigo"):
                con.execute("ALTER TABLE clientes ADD COLUMN codigo TEXT")
            if not _tem_coluna(con, "ordens", "cliente_codigo"):
                con.execute("ALTER TABLE ordens ADD COLUMN cliente_codigo TEXT")
            # códigos para clientes já existentes
            pend = con.execute(
                "SELECT cpf FROM clientes WHERE codigo IS NULL ORDER BY rowid").fetchall()
            if pend:
                ultimo = con.execute(
                    "SELECT COALESCE(MAX(CAST(substr(codigo, 5) AS INTEGER)), 0) "
                    "FROM clientes WHERE codigo LIKE 'CLI-%'").fetchone()[0]
                for k, (cpf,) in enumerate(pend, start=ultimo + 1):
                    con.execute("UPDATE clientes SET codigo = ? WHERE cpf = ?",
                                (f"CLI-{k:04d}", cpf))
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_codigo "
                        "ON clientes(codigo)")
            # saldo inicial dos produtos que já existiam antes do controle de estoque
            con.execute(
                "INSERT INTO movimentos (data, sku, descricao, tipo, quantidade, saldo, "
                "origem) SELECT ?, p.sku, p.descricao, 'Saldo inicial', p.quantidade, "
                "p.quantidade, 'Cadastro' FROM produtos p WHERE p.quantidade > 0 AND "
                "NOT EXISTS (SELECT 1 FROM movimentos m WHERE m.sku = p.sku)", (agora(),))
    finally:
        con.close()


def query(sql, params=()):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def execute(sql, params=()):
    con = sqlite3.connect(DB_PATH)
    try:
        with con:
            con.execute(sql, params)
    finally:
        con.close()


def _proximo(con, tabela, coluna, prefixo):
    ult = con.execute(
        f"SELECT COALESCE(MAX(CAST(substr({coluna}, {len(prefixo) + 1}) AS INTEGER)), 0) "
        f"FROM {tabela} WHERE {coluna} LIKE ?", (prefixo + "%",)).fetchone()[0]
    return f"{prefixo}{ult + 1:04d}"


def proximo_codigo(tabela, coluna, prefixo):
    con = sqlite3.connect(DB_PATH)
    try:
        return _proximo(con, tabela, coluna, prefixo)
    finally:
        con.close()


def _mov(con, sku, descricao, tipo, delta, saldo, origem, obs=None):
    con.execute(
        "INSERT INTO movimentos (data, sku, descricao, tipo, quantidade, saldo, origem, "
        "observacao) VALUES (?,?,?,?,?,?,?,?)",
        (agora(), sku, descricao, tipo, delta, saldo, origem, obs))


# ---------------------------------------------------------------- clientes
def inserir_cliente(d):
    """Cadastra o cliente com código automático (CLI-0001, CLI-0002...)."""
    con = sqlite3.connect(DB_PATH)
    try:
        with con:
            codigo = _proximo(con, "clientes", "codigo", "CLI-")
            con.execute(
                "INSERT INTO clientes (cpf, nome, sobrenome, rua, bairro, cidade, uf, "
                "placa, fabricante, modelo, nota, codigo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (d["cpf"], d["nome"], d["sobrenome"], d["rua"], d["bairro"], d["cidade"],
                 d["uf"], d["placa"], d["fabricante"], d["modelo"], d["nota"], codigo))
        return codigo
    finally:
        con.close()


def atualizar_cliente(d):
    execute("UPDATE clientes SET nome=?, sobrenome=?, rua=?, bairro=?, cidade=?, uf=?, "
            "placa=?, fabricante=?, modelo=?, nota=? WHERE cpf=?",
            (d["nome"], d["sobrenome"], d["rua"], d["bairro"], d["cidade"], d["uf"],
             d["placa"], d["fabricante"], d["modelo"], d["nota"], d["cpf"]))


# ---------------------------------------------------------------- produtos
def inserir_produto(pn, descricao, aplicacao, quantidade, custo, frete, markup):
    """Cadastra o produto com SKU automático (SKU-0001...) e lança a entrada inicial."""
    con = sqlite3.connect(DB_PATH)
    try:
        with con:
            sku = _proximo(con, "produtos", "sku", "SKU-")
            con.execute(
                "INSERT INTO produtos (sku, part_number, descricao, aplicacao, quantidade, "
                "custo_unit, frete, markup) VALUES (?,?,?,?,?,?,?,?)",
                (sku, pn, descricao, aplicacao, quantidade, custo, frete, markup))
            if quantidade > 0 and not eh_servico(descricao):
                _mov(con, sku, descricao, "Entrada", quantidade, quantidade, "Cadastro",
                     "Quantidade informada no cadastro")
        return sku
    finally:
        con.close()


CAMPOS_PRODUTO = {"part_number", "descricao", "aplicacao", "quantidade",
                  "custo_unit", "frete", "markup"}


def atualizar_produto(sku, campos):
    """Altera campos do produto. Mudança de quantidade vira um lançamento 'Ajuste'."""
    assert set(campos) <= CAMPOS_PRODUTO
    con = sqlite3.connect(DB_PATH)
    try:
        with con:
            row = con.execute("SELECT descricao, quantidade FROM produtos WHERE sku = ?",
                              (sku,)).fetchone()
            if row is None:
                raise ValueError("Produto não encontrado.")
            sets = ", ".join(f"{k} = ?" for k in campos)
            con.execute(f"UPDATE produtos SET {sets} WHERE sku = ?", (*campos.values(), sku))
            desc = campos.get("descricao", row[0])
            if ("quantidade" in campos and campos["quantidade"] != row[1]
                    and not eh_servico(desc)):
                _mov(con, sku, desc, "Ajuste", campos["quantidade"] - row[1],
                     campos["quantidade"], "Edição do cadastro")
    finally:
        con.close()


def movimentar(sku, tipo, qtd, obs):
    """Entrada ou saída manual de estoque (o saldo pode ficar negativo)."""
    con = sqlite3.connect(DB_PATH)
    try:
        with con:
            row = con.execute("SELECT descricao, quantidade FROM produtos WHERE sku = ?",
                              (sku,)).fetchone()
            if row is None:
                raise ValueError("Produto não encontrado.")
            delta = qtd if tipo == "Entrada" else -qtd
            novo = row[1] + delta
            con.execute("UPDATE produtos SET quantidade = ? WHERE sku = ?", (novo, sku))
            _mov(con, sku, row[0], tipo, delta, novo, "Manual", obs)
    finally:
        con.close()


# ---------------------------------------------------------------- ordens
def salvar_os(cli, itens, observacoes):
    """Grava a OS, seus itens e a baixa no estoque numa única transação.
    O estoque pode ficar negativo (o sistema apenas alerta)."""
    con = sqlite3.connect(DB_PATH)
    try:
        with con:
            necessario = {}
            for i in itens:
                necessario[i["sku"]] = necessario.get(i["sku"], 0) + i["quantidade"]
            atuais = {}
            for sku, qtd in necessario.items():
                row = con.execute("SELECT descricao, quantidade FROM produtos WHERE sku = ?",
                                  (sku,)).fetchone()
                if row is None:
                    raise ValueError(f"O produto {sku} não está mais cadastrado.")
                atuais[sku] = row

            seq = con.execute(
                "SELECT COALESCE(MAX(CAST(substr(numero, 6) AS INTEGER)), 0) "
                "FROM ordens WHERE numero LIKE ?", (f"{ANO_OS}.%",)).fetchone()[0] + 1
            numero = f"{ANO_OS}.{seq:03d}"
            con.execute(
                "INSERT INTO ordens (numero, data, cpf, nome, sobrenome, rua, bairro, cidade, "
                "uf, placa, fabricante, modelo, observacoes, cliente_codigo) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (numero, agora(), cli["cpf"], cli["nome"], cli["sobrenome"], cli["rua"],
                 cli["bairro"], cli["cidade"], cli["uf"], cli["placa"], cli["fabricante"],
                 cli["modelo"], observacoes, cli.get("codigo")))
            con.executemany(
                "INSERT INTO os_itens (os_numero, sku, part_number, descricao, "
                "quantidade, preco_unit) VALUES (?,?,?,?,?,?)",
                [(numero, i["sku"], i["part_number"], i["descricao"],
                  i["quantidade"], i["preco_unit"]) for i in itens])
            for sku, qtd in necessario.items():
                desc, saldo = atuais[sku]
                if eh_servico(desc):
                    continue
                con.execute("UPDATE produtos SET quantidade = ? WHERE sku = ?",
                            (saldo - qtd, sku))
                _mov(con, sku, desc, "Saída", -qtd, saldo - qtd, f"OS {numero}")
        return numero
    finally:
        con.close()


def proximo_numero_os():
    r = query("SELECT COALESCE(MAX(CAST(substr(numero, 6) AS INTEGER)), 0) AS m "
              "FROM ordens WHERE numero LIKE ?", (f"{ANO_OS}.%",))
    return f"{ANO_OS}.{r[0]['m'] + 1:03d}"


def carregar_os(numero):
    o = query("SELECT * FROM ordens WHERE numero = ?", (numero,))[0]
    itens = query("SELECT * FROM os_itens WHERE os_numero = ? ORDER BY id", (numero,))
    return o, itens


# ============================================================ FUNÇÕES AUXILIARES
def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_cpf(cpf):
    n = re.sub(r"\D", "", cpf or "")
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}" if len(n) == 11 else (cpf or "")


def cpf_valido(cpf):
    n = re.sub(r"\D", "", cpf or "")
    if len(n) != 11 or n == n[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(n[j]) * (i + 1 - j) for j in range(i))
        if (soma * 10) % 11 % 10 != int(n[i]):
            return False
    return True


def estrelas(nota):
    if nota is None or (isinstance(nota, float) and pd.isna(nota)):
        return "Sem avaliação"
    nota = int(nota)
    return "★" * nota + "☆" * (5 - nota) + f" ({nota}/5)"


def fmt_data(iso):
    return datetime.strptime(iso, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y %H:%M")


def cmv(p):
    """CMV = Custo unitário + Frete."""
    return p["custo_unit"] + p["frete"]


def preco_venda(p):
    """Preço de venda = CMV x (1 + Markup/100)."""
    return round(cmv(p) * (1 + p["markup"] / 100), 2)


def situacao_estoque(p):
    if eh_servico(p["descricao"]):
        return "Serviço (sem estoque)"
    if p["quantidade"] < 0:
        return "⛔ Estoque negativo"
    if p["quantidade"] == 0:
        return "🔴 Falta em estoque"
    if p["quantidade"] <= LIMITE_ALERTA:
        return "🟡 Alerta de estoque"
    return "🟢 Estoque OK"


def flash(msg):
    st.session_state["_flash"] = msg


def mostrar_flash():
    msg = st.session_state.pop("_flash", None)
    if msg:
        st.success(msg)


def contador(nome):
    return st.session_state.setdefault(nome, 0)


def cabecalho_cliente(d):
    """Mostra os dados do cadastro do cliente no cabeçalho da OS."""
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Código**  \n{d.get('codigo') or '—'}")
    c2.markdown(f"**CPF**  \n{fmt_cpf(d['cpf'])}")
    c3.markdown(f"**Cliente**  \n{d['nome']} {d['sobrenome']}")
    st.markdown(f"**Endereço**  \n{d['rua']}, {d['bairro']} — {d['cidade']}/{d['uf']}")
    c4, c5, c6 = st.columns(3)
    c4.markdown(f"**Placa**  \n{d['placa']}")
    c5.markdown(f"**Fabricante**  \n{d['fabricante']}")
    c6.markdown(f"**Modelo**  \n{d['modelo'] or '—'}")


# ============================================================ 1) CLIENTES
def pagina_clientes():
    st.header("👤 Cadastro de Clientes")
    mostrar_flash()

    clientes = query("SELECT * FROM clientes ORDER BY codigo")
    opcoes = {"➕ Novo cliente": None}
    for c in clientes:
        opcoes[f"{c['codigo']} — {fmt_cpf(c['cpf'])} — {c['nome']} {c['sobrenome']} "
               f"({c['placa']})"] = c
    escolha = st.selectbox("Cliente", list(opcoes),
                           help="Escolha um cliente já cadastrado para editar ou excluir.")
    atual = opcoes[escolha] or {}
    suf = f"{atual.get('cpf', 'novo')}_{contador('n_cli')}"

    with st.form(f"form_cli_{suf}"):
        st.caption("Campos com * são obrigatórios. O código do cliente é gerado "
                   "automaticamente ao salvar.")
        c0, c1, c2, c3 = st.columns(4)
        c0.text_input("Código", value=atual.get("codigo") or proximo_codigo(
            "clientes", "codigo", "CLI-"), disabled=True, key=f"cli_cod_{suf}")
        cpf = c1.text_input("CPF *", value=fmt_cpf(atual.get("cpf", "")),
                            placeholder="000.000.000-00", disabled=bool(atual),
                            key=f"cli_cpf_{suf}")
        nome = c2.text_input("Nome *", value=atual.get("nome", ""), key=f"cli_nome_{suf}")
        sobrenome = c3.text_input("Sobrenome *", value=atual.get("sobrenome", ""),
                                  key=f"cli_sob_{suf}")

        st.markdown("**Endereço**")
        e1, e2 = st.columns(2)
        rua = e1.text_input("Rua *", value=atual.get("rua", ""), key=f"cli_rua_{suf}")
        bairro = e2.text_input("Bairro *", value=atual.get("bairro", ""),
                               key=f"cli_bai_{suf}")
        e3, e4 = st.columns([3, 1])
        cidade = e3.text_input("Cidade *", value=atual.get("cidade", ""),
                               key=f"cli_cid_{suf}")
        uf = e4.selectbox("UF *", UFS, key=f"cli_uf_{suf}", placeholder="UF",
                          index=UFS.index(atual["uf"]) if atual else None)

        st.markdown("**Veículo**")
        v1, v2, v3 = st.columns(3)
        placa = v1.text_input("Placa do carro *", value=atual.get("placa", ""),
                              placeholder="ABC1D23", key=f"cli_pla_{suf}")
        fabricante = v2.text_input("Fabricante do carro *", value=atual.get("fabricante", ""),
                                   placeholder="Ex.: Volkswagen", key=f"cli_fab_{suf}")
        modelo = v3.text_input("Modelo do carro", value=atual.get("modelo") or "",
                               key=f"cli_mod_{suf}")

        notas = [None, 0, 1, 2, 3, 4, 5]
        nota = st.selectbox(
            "Nota de avaliação do cliente (0 a 5 estrelas)", notas,
            index=notas.index(atual.get("nota")), key=f"cli_nota_{suf}",
            format_func=lambda n: "Sem avaliação" if n is None else estrelas(n))
        enviado = st.form_submit_button("💾 Salvar cliente", type="primary")

    if enviado:
        cpf_n = atual.get("cpf") or re.sub(r"\D", "", cpf)
        placa_n = re.sub(r"[^A-Za-z0-9]", "", placa).upper()
        erros = [f"Preencha o campo: {rot}" for rot, val in [
            ("Nome", nome), ("Sobrenome", sobrenome), ("Rua", rua), ("Bairro", bairro),
            ("Cidade", cidade), ("UF", uf), ("Placa", placa), ("Fabricante", fabricante)]
            if not (val or "").strip()]
        if not cpf_valido(cpf_n):
            erros.append("CPF inválido.")
        elif not atual and query("SELECT 1 FROM clientes WHERE cpf = ?", (cpf_n,)):
            erros.append("Este CPF já está cadastrado — selecione-o na lista para editar.")
        if placa_n and not PLACA_RE.match(placa_n):
            erros.append("Placa inválida (use o formato ABC1234 ou ABC1D23).")

        if erros:
            for e in erros:
                st.error(e)
        else:
            dados = dict(cpf=cpf_n, nome=nome.strip(), sobrenome=sobrenome.strip(),
                         rua=rua.strip(), bairro=bairro.strip(), cidade=cidade.strip(),
                         uf=uf, placa=placa_n, fabricante=fabricante.strip(),
                         modelo=modelo.strip() or None, nota=nota)
            if atual:
                atualizar_cliente(dados)
                flash(f"Cliente {atual['codigo']} atualizado!")
            else:
                flash(f"Cliente cadastrado com o código {inserir_cliente(dados)}!")
            st.session_state["n_cli"] += 1
            st.rerun()

    if atual:
        with st.expander("🗑️ Excluir este cliente"):
            st.caption("As ordens de serviço já geradas não são afetadas.")
            if st.button("Confirmar exclusão", key=f"del_cli_{suf}"):
                execute("DELETE FROM clientes WHERE cpf = ?", (atual["cpf"],))
                flash("Cliente excluído.")
                st.session_state["n_cli"] += 1
                st.rerun()

    st.divider()
    st.subheader("Clientes cadastrados")
    if clientes:
        df = pd.DataFrame([{
            "Código": c["codigo"], "CPF": fmt_cpf(c["cpf"]),
            "Cliente": f"{c['nome']} {c['sobrenome']}",
            "Endereço": f"{c['rua']}, {c['bairro']} — {c['cidade']}/{c['uf']}",
            "Placa": c["placa"], "Fabricante": c["fabricante"],
            "Modelo": c["modelo"] or "", "Avaliação": estrelas(c["nota"])}
            for c in clientes])
        st.dataframe(df, hide_index=True)
    else:
        st.info("Nenhum cliente cadastrado ainda.")


# ============================================================ 2) PRODUTOS
def pagina_produtos():
    st.header("📦 Cadastro de Produtos")
    mostrar_flash()

    produtos = query("SELECT * FROM produtos ORDER BY sku")
    opcoes = {"➕ Novo produto": None}
    for p in produtos:
        opcoes[f"{p['sku']} — {p['descricao']}"] = p
    escolha = st.selectbox("Produto", list(opcoes),
                           help="Escolha um produto já cadastrado para editar ou excluir.")
    atual = opcoes[escolha] or {}
    suf = f"{atual.get('sku', 'novo')}_{contador('n_prod')}"

    st.caption("Campos com * são obrigatórios. O SKU é gerado automaticamente em sequência. "
               "Cadastre o serviço como um produto chamado **Mão de obra**.")
    c1, c2 = st.columns([1, 2])
    c1.text_input("SKU (automático)",
                  value=atual.get("sku") or proximo_codigo("produtos", "sku", "SKU-"),
                  disabled=True, key=f"prod_sku_{suf}")
    pn = c2.text_input("Part Number *", value=atual.get("part_number", ""),
                       key=f"prod_pn_{suf}")
    descricao = st.text_input("Descrição *", value=atual.get("descricao", ""),
                              key=f"prod_desc_{suf}")
    aplicacao = st.text_input("Aplicação (modelo e ano do carro)",
                              value=atual.get("aplicacao") or "",
                              placeholder="Ex.: Gol G5 2009–2013 / Voyage 2010–2014",
                              key=f"prod_apl_{suf}")
    q1, q2, q3, q4 = st.columns(4)
    quantidade = q1.number_input("Quantidade", step=1,
                                 value=int(atual.get("quantidade", 0)),
                                 key=f"prod_qtd_{suf}")
    custo = q2.number_input("Custo unitário (R$)", min_value=0.0, step=0.01, format="%.2f",
                            value=float(atual.get("custo_unit", 0.0)), key=f"prod_cus_{suf}")
    frete = q3.number_input("Frete (R$)", min_value=0.0, step=0.01, format="%.2f",
                            value=float(atual.get("frete", 0.0)), key=f"prod_fre_{suf}")
    markup = q4.number_input("Markup (%)", min_value=0.0, step=1.0, format="%.2f",
                             value=float(atual.get("markup", 50.0)), key=f"prod_mk_{suf}")

    novo = {"custo_unit": custo, "frete": frete, "markup": markup}
    m1, m2 = st.columns(2)
    m1.metric("CMV (Custo unitário + Frete)", brl(cmv(novo)))
    m2.metric("Preço de venda sugerido", brl(preco_venda(novo)))
    st.caption("Preço de venda = CMV × (1 + Markup%). Ex.: markup de 40% → CMV × 1,40. "
               "Alterar a quantidade de um produto já cadastrado gera um lançamento de "
               "'Ajuste' no estoque.")

    if st.button("💾 Salvar produto", type="primary", key=f"prod_save_{suf}"):
        erros = [f"Preencha o campo: {rot}" for rot, val in [
            ("Part Number", pn), ("Descrição", descricao)] if not (val or "").strip()]
        if not erros:
            try:
                if atual:
                    atualizar_produto(atual["sku"], dict(
                        part_number=pn.strip(), descricao=descricao.strip(),
                        aplicacao=aplicacao.strip() or None, quantidade=int(quantidade),
                        custo_unit=custo, frete=frete, markup=markup))
                    flash(f"Produto {atual['sku']} atualizado!")
                else:
                    sku = inserir_produto(pn.strip(), descricao.strip(),
                                          aplicacao.strip() or None, int(quantidade),
                                          custo, frete, markup)
                    flash(f"Produto cadastrado com o SKU {sku}!")
                st.session_state["n_prod"] += 1
                st.rerun()
            except sqlite3.IntegrityError:
                erros.append("Já existe um produto com esta descrição.")
        for e in erros:
            st.error(e)

    if atual:
        with st.expander("🗑️ Excluir este produto"):
            st.caption("As ordens de serviço e o histórico de estoque são mantidos.")
            if st.button("Confirmar exclusão", key=f"del_prod_{suf}"):
                execute("DELETE FROM produtos WHERE sku = ?", (atual["sku"],))
                flash("Produto excluído.")
                st.session_state["n_prod"] += 1
                st.rerun()

    st.divider()
    st.subheader("Produtos cadastrados")
    if not produtos:
        st.info("Nenhum produto cadastrado ainda.")
        return

    st.caption("✏️ Edição rápida: altere **Qtd, Custo unit., Frete e Markup %** direto na "
               "tabela e clique em salvar. CMV, preço e situação são recalculados ao salvar.")
    df = pd.DataFrame([{
        "SKU": p["sku"], "Part Number": p["part_number"], "Descrição": p["descricao"],
        "Aplicação": p["aplicacao"] or "", "Qtd": p["quantidade"],
        "Custo unit.": p["custo_unit"], "Frete": p["frete"], "Markup %": p["markup"],
        "CMV": cmv(p), "Preço de venda": preco_venda(p), "Situação": situacao_estoque(p)}
        for p in produtos])
    moeda = st.column_config.NumberColumn(format="R$ %.2f", min_value=0.0)
    editado = st.data_editor(
        df, hide_index=True, key=f"prod_tab_{contador('n_prod')}",
        disabled=["SKU", "Part Number", "Descrição", "Aplicação", "CMV",
                  "Preço de venda", "Situação"],
        column_config={
            "Qtd": st.column_config.NumberColumn(step=1, format="%d"),
            "Custo unit.": moeda, "Frete": moeda,
            "Markup %": st.column_config.NumberColumn(min_value=0.0, format="%.2f%%"),
            "CMV": st.column_config.NumberColumn(format="R$ %.2f"),
            "Preço de venda": st.column_config.NumberColumn(format="R$ %.2f")})

    if st.button("💾 Salvar alterações da tabela"):
        alterados = 0
        for idx, r in editado.iterrows():
            ant = df.loc[idx]
            campos = {}
            for col, campo in [("Qtd", "quantidade"), ("Custo unit.", "custo_unit"),
                               ("Frete", "frete"), ("Markup %", "markup")]:
                if pd.notna(r[col]) and r[col] != ant[col]:
                    campos[campo] = int(r[col]) if campo == "quantidade" else float(r[col])
            if campos:
                atualizar_produto(ant["SKU"], campos)
                alterados += 1
        if alterados:
            flash(f"{alterados} produto(s) atualizado(s).")
            st.session_state["n_prod"] += 1
            st.rerun()
        else:
            st.info("Nenhuma alteração para salvar.")


# ============================================================ 3) ESTOQUE
def pagina_estoque():
    st.header("📊 Controle de Estoque")
    mostrar_flash()
    produtos = [p for p in query("SELECT * FROM produtos ORDER BY quantidade, descricao")
                if not eh_servico(p["descricao"])]
    if not produtos:
        st.info("Cadastre produtos para controlar o estoque.")
        return

    negativos = [p for p in produtos if p["quantidade"] < 0]
    faltas = [p for p in produtos if p["quantidade"] == 0]
    alertas = [p for p in produtos if 0 < p["quantidade"] <= LIMITE_ALERTA]
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Produtos", len(produtos))
    k2.metric("⛔ Estoque negativo", len(negativos))
    k3.metric("🔴 Falta em estoque", len(faltas))
    k4.metric("🟡 Alerta de estoque", len(alertas))
    k5.metric("Unidades em estoque", sum(max(p["quantidade"], 0) for p in produtos))
    if negativos:
        st.error("⛔ Estoque negativo (saiu mais do que entrou): " + ", ".join(
            f"{p['descricao']} ({p['quantidade']})" for p in negativos))
    if faltas:
        st.error("Falta em estoque: " + ", ".join(p["descricao"] for p in faltas))
    if alertas:
        st.warning("Alerta de estoque (quantidade baixa): " + ", ".join(
            f"{p['descricao']} ({p['quantidade']})" for p in alertas))

    aba1, aba2, aba3 = st.tabs(["Posição atual", "Registrar entrada / saída", "Histórico"])

    with aba1:
        filtro = st.radio("Mostrar", ["Todos", "Estoque negativo", "Falta em estoque",
                                      "Alerta de estoque"], horizontal=True)
        linhas = [{"SKU": p["sku"], "Part Number": p["part_number"],
                   "Descrição": p["descricao"], "Aplicação": p["aplicacao"] or "",
                   "Quantidade": p["quantidade"], "Situação": situacao_estoque(p)}
                  for p in produtos if filtro == "Todos" or filtro in situacao_estoque(p)]
        if linhas:
            st.dataframe(pd.DataFrame(linhas), hide_index=True)
        else:
            st.info("Nenhum produto nesta situação.")

    with aba2:
        n = contador("n_est")
        mapa = {f"{p['sku']} — {p['descricao']} (saldo: {p['quantidade']})": p
                for p in produtos}
        p = mapa[st.selectbox("Produto", list(mapa), key=f"est_prod_{n}")]
        tipo = st.radio("Tipo de movimentação", ["Entrada", "Saída"], horizontal=True,
                        key=f"est_tipo_{n}")
        qtd = st.number_input("Quantidade", min_value=1, step=1, value=1, key=f"est_qtd_{n}")
        obs = st.text_input("Observação (ex.: nota fiscal de compra, motivo da saída)",
                            key=f"est_obs_{n}")
        st.caption("As saídas por Ordem de Serviço são lançadas automaticamente ao gerar a OS.")
        if st.button("💾 Registrar movimentação", type="primary", key=f"est_ok_{n}"):
            try:
                movimentar(p["sku"], tipo, int(qtd), obs.strip() or None)
                flash(f"{tipo} de {int(qtd)} un. de '{p['descricao']}' registrada.")
                st.session_state["n_est"] += 1
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    with aba3:
        opc = {"Todos os produtos": None}
        for p in produtos:
            opc[f"{p['sku']} — {p['descricao']}"] = p["sku"]
        sku = opc[st.selectbox("Filtrar por produto", list(opc), key="est_filtro")]
        sql = "SELECT * FROM movimentos"
        sql += " WHERE sku = ?" if sku else ""
        movs = query(sql + " ORDER BY id DESC LIMIT 500", (sku,) if sku else ())
        if movs:
            st.dataframe(pd.DataFrame([{
                "Data": fmt_data(m["data"]), "SKU": m["sku"], "Descrição": m["descricao"],
                "Tipo": m["tipo"], "Qtd": f"{m['quantidade']:+d}", "Saldo": m["saldo"],
                "Origem": m["origem"] or "", "Observação": m["observacao"] or ""}
                for m in movs]), hide_index=True)
        else:
            st.info("Nenhuma movimentação registrada.")


# ============================================================ 4) ORDEM DE SERVIÇO
CSS_OS = """
body{font-family:Arial,Helvetica,sans-serif;margin:32px;color:#222}
h1{font-size:20px;margin:0}h2{font-size:15px;margin:22px 0 8px}
.topo{display:flex;justify-content:space-between;border-bottom:2px solid #222;padding-bottom:8px}
.grade{display:grid;grid-template-columns:repeat(3,1fr);gap:8px 16px;margin-top:10px;font-size:13px}
.grade b{display:block;font-size:11px;color:#555;text-transform:uppercase}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border:1px solid #bbb;padding:6px 8px;text-align:left}th{background:#eee}
.n{text-align:right}.total{text-align:right;font-size:15px;margin-top:10px}
.ass{display:flex;gap:60px;margin-top:90px}
.ass div{flex:1;border-top:1px solid #222;text-align:center;padding-top:6px;font-size:13px}
"""


def os_html(numero):
    """Documento HTML da OS, pronto para imprimir (Ctrl+P) ou salvar em PDF."""
    o, itens = carregar_os(numero)
    e = html.escape
    total = sum(i["quantidade"] * i["preco_unit"] for i in itens)
    linhas = "".join(
        f"<tr><td>{e(i['sku'] or '')}</td><td>{e(i['part_number'] or '')}</td>"
        f"<td>{e(i['descricao'] or '')}</td><td class='n'>{i['quantidade']}</td>"
        f"<td class='n'>{brl(i['preco_unit'])}</td>"
        f"<td class='n'>{brl(i['quantidade'] * i['preco_unit'])}</td></tr>" for i in itens)
    obs = f"<h2>Observações</h2><p>{e(o['observacoes'])}</p>" if o["observacoes"] else ""
    corpo = (
        f"<div class='topo'><h1>{e(EMPRESA)}</h1>"
        f"<div><b>Ordem de Serviço nº {e(numero)}</b><br>{fmt_data(o['data'])}</div></div>"
        "<div class='grade'>"
        f"<div><b>Código</b>{e(o.get('cliente_codigo') or '—')}</div>"
        f"<div><b>CPF</b>{fmt_cpf(o['cpf'])}</div>"
        f"<div><b>Cliente</b>{e(o['nome'])} {e(o['sobrenome'])}</div>"
        f"<div style='grid-column:span 3'><b>Endereço</b>{e(o['rua'])}, {e(o['bairro'])} — "
        f"{e(o['cidade'])}/{e(o['uf'])}</div>"
        f"<div><b>Placa</b>{e(o['placa'])}</div>"
        f"<div><b>Fabricante</b>{e(o['fabricante'])}</div>"
        f"<div><b>Modelo</b>{e(o['modelo'] or '—')}</div></div>"
        "<h2>Produtos e serviços</h2><table><tr><th>SKU</th><th>Part Number</th>"
        "<th>Descrição</th><th>Qtd</th><th>Preço unit.</th><th>Total</th></tr>"
        f"{linhas}</table><div class='total'><b>Total: {brl(total)}</b></div>{obs}"
        "<div class='ass'><div>Cliente</div><div>Mecânico</div></div>")
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>OS {e(numero)}</title><style>{CSS_OS}</style></head>"
            f"<body>{corpo}</body></html>")


def mostrar_os(numero):
    o, itens = carregar_os(numero)
    with st.container(border=True):
        st.subheader(f"{EMPRESA} — Ordem de Serviço nº {numero}")
        st.caption(f"Emitida em {fmt_data(o['data'])}")
        cabecalho_cliente({**o, "codigo": o.get("cliente_codigo")})
        st.markdown("&nbsp;")
        df = pd.DataFrame([{
            "SKU": i["sku"], "Part Number": i["part_number"], "Descrição": i["descricao"],
            "Qtd": i["quantidade"], "Preço unit.": i["preco_unit"],
            "Total": i["quantidade"] * i["preco_unit"]} for i in itens])
        moeda = st.column_config.NumberColumn(format="R$ %.2f")
        st.dataframe(df, hide_index=True,
                     column_config={"Preço unit.": moeda, "Total": moeda})
        st.markdown(f"### Total: {brl(sum(i['quantidade'] * i['preco_unit'] for i in itens))}")
        if o["observacoes"]:
            st.markdown(f"**Observações**  \n{o['observacoes']}")
        st.markdown("&nbsp;\n\n&nbsp;\n\n&nbsp;")
        a1, a2 = st.columns(2)
        a1.markdown("────────────────────────────  \n**Cliente**")
        a2.markdown("────────────────────────────  \n**Mecânico**")
    st.download_button("⬇️ Baixar OS para imprimir (HTML)", data=os_html(numero),
                       file_name=f"OS_{numero}.html", mime="text/html",
                       key=f"dl_{numero}")


def pagina_os():
    st.header("🧾 Gerar Ordem de Serviço")
    clientes = query("SELECT * FROM clientes ORDER BY nome, sobrenome")
    produtos = query("SELECT * FROM produtos ORDER BY descricao")
    if not clientes or not produtos:
        st.warning("Cadastre pelo menos um cliente e um produto antes de gerar uma OS.")
        return

    ultima = st.session_state.get("ultima_os")
    if ultima:
        st.success(f"Ordem de serviço {ultima} gerada e estoque atualizado!")
        with st.expander(f"📄 Ver / imprimir OS {ultima}", expanded=True):
            mostrar_os(ultima)
        st.divider()

    n = contador("os_n")
    st.markdown(f"**Próxima OS:** `{proximo_numero_os()}`")
    mapa_cli = {f"{c['codigo']} — {fmt_cpf(c['cpf'])} — {c['nome']} {c['sobrenome']} "
                f"({c['placa']})": c for c in clientes}
    cli = mapa_cli[st.selectbox("Cliente", list(mapa_cli), key=f"os_cli_{n}")]

    st.subheader("Dados do cliente")
    with st.container(border=True):
        cabecalho_cliente(cli)

    st.markdown("&nbsp;")
    st.subheader("Produtos e serviços")
    st.caption("Escolha a descrição em cada linha (use a lista ou digite para filtrar). "
               "SKU, Part Number e Preço de venda são preenchidos automaticamente. "
               "Para mais linhas, clique no + no fim da tabela.")
    mapa_prod = {p["descricao"]: p for p in produtos}
    mapa_sku = {p["sku"]: p for p in produtos}
    base = pd.DataFrame({"Descrição": [None] * 8, "Quantidade": [1] * 8})
    editado = st.data_editor(
        base, key=f"os_itens_{n}", num_rows="dynamic", hide_index=True,
        column_config={
            "Descrição": st.column_config.SelectboxColumn(
                "Descrição do produto", options=list(mapa_prod), required=False),
            "Quantidade": st.column_config.NumberColumn(
                "Qtd", min_value=1, step=1, default=1)})

    itens = []
    for _, r in editado.iterrows():
        desc = r["Descrição"]
        if not isinstance(desc, str) or desc not in mapa_prod:
            continue
        p = mapa_prod[desc]
        qtd = int(r["Quantidade"]) if pd.notna(r["Quantidade"]) and r["Quantidade"] >= 1 else 1
        itens.append({"sku": p["sku"], "part_number": p["part_number"],
                      "descricao": p["descricao"], "quantidade": qtd,
                      "preco_unit": preco_venda(p)})

    ficam_negativos = []
    if itens:
        df = pd.DataFrame([{
            "SKU": i["sku"], "Part Number": i["part_number"], "Descrição": i["descricao"],
            "Qtd": i["quantidade"], "Preço de venda": i["preco_unit"],
            "Total": i["quantidade"] * i["preco_unit"],
            "Estoque": situacao_estoque(mapa_sku[i["sku"]])} for i in itens])
        moeda = st.column_config.NumberColumn(format="R$ %.2f")
        st.dataframe(df, hide_index=True,
                     column_config={"Preço de venda": moeda, "Total": moeda})
        st.metric("Total da OS", brl(sum(i["quantidade"] * i["preco_unit"] for i in itens)))

        pedido = {}
        for i in itens:
            pedido[i["sku"]] = pedido.get(i["sku"], 0) + i["quantidade"]
        for sku, qtd in pedido.items():
            p = mapa_sku[sku]
            if not eh_servico(p["descricao"]) and qtd > p["quantidade"]:
                ficam_negativos.append(
                    f"**{p['descricao']}**: pedido {qtd}, em estoque {p['quantidade']} "
                    f"→ saldo ficará {p['quantidade'] - qtd}")
        if ficam_negativos:
            st.warning("⚠️ Estoque insuficiente — a OS pode ser gerada, mas o saldo "
                       "ficará negativo:\n\n" + "\n".join(f"- {f}" for f in ficam_negativos))

    obs = st.text_area("Observações (opcional)", key=f"os_obs_{n}")
    if st.button("✅ Gerar Ordem de Serviço", type="primary", key=f"os_gerar_{n}"):
        if not itens:
            st.error("Selecione pelo menos um produto na tabela.")
        else:
            try:
                st.session_state["ultima_os"] = salvar_os(cli, itens, obs.strip() or None)
                st.session_state["os_n"] += 1
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def pagina_consulta():
    st.header("🔎 Consultar Ordens de Serviço")
    ordens = query("SELECT numero, data, nome, sobrenome, placa FROM ordens "
                   "ORDER BY CAST(substr(numero, 6) AS INTEGER) DESC, numero DESC")
    if not ordens:
        st.info("Nenhuma ordem de serviço gerada ainda.")
        return
    rotulos = {f"{o['numero']} — {o['nome']} {o['sobrenome']} ({o['placa']}) — "
               f"{fmt_data(o['data'])}": o["numero"] for o in ordens}
    mostrar_os(rotulos[st.selectbox("Ordem de serviço", list(rotulos))])


# ============================================================ APP
def main():
    st.set_page_config(page_title="Oficina – Gestão", page_icon="🔧", layout="wide")
    init_db()
    st.sidebar.title("🔧 Oficina")
    paginas = {"👤 Clientes": pagina_clientes, "📦 Produtos": pagina_produtos,
               "📊 Estoque": pagina_estoque, "🧾 Gerar OS": pagina_os,
               "🔎 Consultar OS": pagina_consulta}
    paginas[st.sidebar.radio("Menu", list(paginas))]()


main()
