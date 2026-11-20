"""Sistema de Oficina – Passo 1
Módulos: Cadastro de Clientes, Cadastro de Produtos e Ordem de Serviço.
Tecnologias: Streamlit + SQLite (o banco é o arquivo oficina.db, criado sozinho).

Para rodar:
    pip install -r requirements.txt
    streamlit run app.py
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
DB_PATH = Path(__file__).with_name("oficina.db")

UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
       "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
       "SP", "SE", "TO"]
PLACA_RE = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")  # ABC1234 ou ABC1D23

SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    cpf TEXT PRIMARY KEY, nome TEXT NOT NULL, sobrenome TEXT NOT NULL,
    rua TEXT NOT NULL, bairro TEXT NOT NULL, cidade TEXT NOT NULL, uf TEXT NOT NULL,
    placa TEXT NOT NULL, fabricante TEXT NOT NULL, modelo TEXT, nota INTEGER
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
    placa TEXT, fabricante TEXT, modelo TEXT, nota INTEGER, observacoes TEXT
);
CREATE TABLE IF NOT EXISTS os_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT, os_numero TEXT NOT NULL,
    sku TEXT, part_number TEXT, descricao TEXT, quantidade INTEGER, preco_unit REAL
);
"""


# ============================================================ BANCO DE DADOS
def init_db():
    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(SCHEMA)
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


def salvar_os(cli, itens, observacoes):
    """Grava a OS e seus itens numa única transação e devolve o número gerado."""
    con = sqlite3.connect(DB_PATH)
    try:
        with con:
            seq = con.execute(
                "SELECT COALESCE(MAX(CAST(substr(numero, 6) AS INTEGER)), 0) "
                "FROM ordens WHERE numero LIKE ?", (f"{ANO_OS}.%",)).fetchone()[0] + 1
            numero = f"{ANO_OS}.{seq:03d}"
            con.execute(
                "INSERT INTO ordens VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (numero, datetime.now().strftime("%Y-%m-%d %H:%M"),
                 cli["cpf"], cli["nome"], cli["sobrenome"], cli["rua"], cli["bairro"],
                 cli["cidade"], cli["uf"], cli["placa"], cli["fabricante"],
                 cli["modelo"], cli["nota"], observacoes))
            con.executemany(
                "INSERT INTO os_itens (os_numero, sku, part_number, descricao, "
                "quantidade, preco_unit) VALUES (?,?,?,?,?,?)",
                [(numero, i["sku"], i["part_number"], i["descricao"],
                  i["quantidade"], i["preco_unit"]) for i in itens])
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


def flash(msg):
    st.session_state["_flash"] = msg


def mostrar_flash():
    msg = st.session_state.pop("_flash", None)
    if msg:
        st.success(msg)


def contador(nome):
    return st.session_state.setdefault(nome, 0)


def cabecalho_cliente(d):
    """Mostra todos os campos do cadastro do cliente (usado na OS)."""
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**CPF**  \n{fmt_cpf(d['cpf'])}")
    c2.markdown(f"**Cliente**  \n{d['nome']} {d['sobrenome']}")
    c3.markdown(f"**Avaliação**  \n{estrelas(d['nota'])}")
    st.markdown(f"**Endereço**  \n{d['rua']}, {d['bairro']} — {d['cidade']}/{d['uf']}")
    c4, c5, c6 = st.columns(3)
    c4.markdown(f"**Placa**  \n{d['placa']}")
    c5.markdown(f"**Fabricante**  \n{d['fabricante']}")
    c6.markdown(f"**Modelo**  \n{d['modelo'] or '—'}")


# ============================================================ 1) CLIENTES
def pagina_clientes():
    st.header("👤 Cadastro de Clientes")
    mostrar_flash()

    clientes = query("SELECT * FROM clientes ORDER BY nome, sobrenome")
    opcoes = {"➕ Novo cliente": None}
    for c in clientes:
        opcoes[f"{fmt_cpf(c['cpf'])} — {c['nome']} {c['sobrenome']} ({c['placa']})"] = c
    escolha = st.selectbox("Cliente", list(opcoes),
                           help="Escolha um cliente já cadastrado para editar ou excluir.")
    atual = opcoes[escolha] or {}
    suf = f"{atual.get('cpf', 'novo')}_{contador('n_cli')}"

    with st.form(f"form_cli_{suf}"):
        st.caption("Campos com * são obrigatórios.")
        c1, c2, c3 = st.columns(3)
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
            execute("INSERT OR REPLACE INTO clientes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (cpf_n, nome.strip(), sobrenome.strip(), rua.strip(), bairro.strip(),
                     cidade.strip(), uf, placa_n, fabricante.strip(),
                     modelo.strip() or None, nota))
            flash("Cliente atualizado!" if atual else "Cliente cadastrado!")
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
            "CPF": fmt_cpf(c["cpf"]), "Cliente": f"{c['nome']} {c['sobrenome']}",
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

    produtos = query("SELECT * FROM produtos ORDER BY descricao")
    opcoes = {"➕ Novo produto": None}
    for p in produtos:
        opcoes[f"{p['sku']} — {p['descricao']}"] = p
    escolha = st.selectbox("Produto", list(opcoes),
                           help="Escolha um produto já cadastrado para editar ou excluir.")
    atual = opcoes[escolha] or {}
    suf = f"{atual.get('sku', 'novo')}_{contador('n_prod')}"

    st.caption("Campos com * são obrigatórios.")
    c1, c2 = st.columns(2)
    sku = c1.text_input("SKU *", value=atual.get("sku", ""), disabled=bool(atual),
                        key=f"prod_sku_{suf}")
    pn = c2.text_input("Part Number *", value=atual.get("part_number", ""),
                       key=f"prod_pn_{suf}")
    descricao = st.text_input("Descrição *", value=atual.get("descricao", ""),
                              key=f"prod_desc_{suf}")
    aplicacao = st.text_input("Aplicação (modelo e ano do carro)",
                              value=atual.get("aplicacao") or "",
                              placeholder="Ex.: Gol G5 2009–2013 / Voyage 2010–2014",
                              key=f"prod_apl_{suf}")
    q1, q2, q3, q4 = st.columns(4)
    quantidade = q1.number_input("Quantidade", min_value=0, step=1,
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
    st.caption("Preço de venda = CMV × (1 + Markup%). Ex.: markup de 40% → CMV × 1,40.")

    if st.button("💾 Salvar produto", type="primary", key=f"prod_save_{suf}"):
        sku_n = atual.get("sku") or sku.strip().upper()
        erros = [f"Preencha o campo: {rot}" for rot, val in [
            ("SKU", sku_n), ("Part Number", pn), ("Descrição", descricao)]
            if not (val or "").strip()]
        if not erros:
            try:
                if atual:
                    execute("UPDATE produtos SET part_number=?, descricao=?, aplicacao=?, "
                            "quantidade=?, custo_unit=?, frete=?, markup=? WHERE sku=?",
                            (pn.strip(), descricao.strip(), aplicacao.strip() or None,
                             quantidade, custo, frete, markup, sku_n))
                else:
                    execute("INSERT INTO produtos VALUES (?,?,?,?,?,?,?,?)",
                            (sku_n, pn.strip(), descricao.strip(), aplicacao.strip() or None,
                             quantidade, custo, frete, markup))
                flash("Produto atualizado!" if atual else "Produto cadastrado!")
                st.session_state["n_prod"] += 1
                st.rerun()
            except sqlite3.IntegrityError:
                erros.append("Já existe um produto com este SKU ou esta descrição.")
        for e in erros:
            st.error(e)

    if atual:
        with st.expander("🗑️ Excluir este produto"):
            st.caption("As ordens de serviço já geradas não são afetadas.")
            if st.button("Confirmar exclusão", key=f"del_prod_{suf}"):
                execute("DELETE FROM produtos WHERE sku = ?", (atual["sku"],))
                flash("Produto excluído.")
                st.session_state["n_prod"] += 1
                st.rerun()

    st.divider()
    st.subheader("Produtos cadastrados")
    if produtos:
        df = pd.DataFrame([{
            "SKU": p["sku"], "Part Number": p["part_number"], "Descrição": p["descricao"],
            "Aplicação": p["aplicacao"] or "", "Qtd": p["quantidade"],
            "Custo unit.": p["custo_unit"], "Frete": p["frete"], "CMV": cmv(p),
            "Markup %": p["markup"], "Preço de venda": preco_venda(p)}
            for p in produtos])
        moeda = st.column_config.NumberColumn(format="R$ %.2f")
        st.dataframe(df, hide_index=True, column_config={
            "Custo unit.": moeda, "Frete": moeda, "CMV": moeda, "Preço de venda": moeda,
            "Markup %": st.column_config.NumberColumn(format="%.2f%%")})
    else:
        st.info("Nenhum produto cadastrado ainda.")


# ============================================================ 3) ORDEM DE SERVIÇO
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
        f"<div><b>CPF</b>{fmt_cpf(o['cpf'])}</div>"
        f"<div><b>Cliente</b>{e(o['nome'])} {e(o['sobrenome'])}</div>"
        f"<div><b>Avaliação</b>{estrelas(o['nota'])}</div>"
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
        cabecalho_cliente(o)
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
        st.success(f"Ordem de serviço {ultima} gerada com sucesso!")
        with st.expander(f"📄 Ver / imprimir OS {ultima}", expanded=True):
            mostrar_os(ultima)
        st.divider()

    n = contador("os_n")
    st.markdown(f"**Próxima OS:** `{proximo_numero_os()}`")
    mapa_cli = {f"{fmt_cpf(c['cpf'])} — {c['nome']} {c['sobrenome']} ({c['placa']})": c
                for c in clientes}
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

    if itens:
        df = pd.DataFrame([{
            "SKU": i["sku"], "Part Number": i["part_number"], "Descrição": i["descricao"],
            "Qtd": i["quantidade"], "Preço de venda": i["preco_unit"],
            "Total": i["quantidade"] * i["preco_unit"]} for i in itens])
        moeda = st.column_config.NumberColumn(format="R$ %.2f")
        st.dataframe(df, hide_index=True,
                     column_config={"Preço de venda": moeda, "Total": moeda})
        st.metric("Total da OS", brl(sum(i["quantidade"] * i["preco_unit"] for i in itens)))

    obs = st.text_area("Observações (opcional)", key=f"os_obs_{n}")
    if st.button("✅ Gerar Ordem de Serviço", type="primary", key=f"os_gerar_{n}"):
        if not itens:
            st.error("Selecione pelo menos um produto na tabela.")
        else:
            st.session_state["ultima_os"] = salvar_os(cli, itens, obs.strip() or None)
            st.session_state["os_n"] += 1
            st.rerun()


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
    pagina = st.sidebar.radio("Menu", ["👤 Clientes", "📦 Produtos",
                                       "🧾 Gerar OS", "🔎 Consultar OS"])
    {"👤 Clientes": pagina_clientes, "📦 Produtos": pagina_produtos,
     "🧾 Gerar OS": pagina_os, "🔎 Consultar OS": pagina_consulta}[pagina]()


main()
