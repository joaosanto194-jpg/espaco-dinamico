from datetime import date, datetime
import hashlib
import os
import re
import secrets
import shutil
import sqlite3
import urllib.parse
import textwrap
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import (
    Column, Date, Float, ForeignKey, Integer, String, Text,
    create_engine, inspect
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# ============================================================
# ESPAÇO DINÂMICO — versão aprimorada, sem dependência obrigatória
# de extra-streamlit-components.
# ============================================================

st.set_page_config(
    page_title="Espaço Dinâmico | Gestão",
    page_icon="🧩",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
# Preserve an existing database in either the app folder or the current launch folder.
# Prefer the app folder when its database already exists; otherwise reuse an existing
# database in the launch folder before creating a new one.
DB_IN_APP = BASE_DIR / "espaco_dinamico.db"
DB_IN_CWD = Path.cwd() / "espaco_dinamico.db"
if os.getenv("DATABASE_URL"):
    DATABASE_URL = os.getenv("DATABASE_URL")
else:
    if DB_IN_APP.exists():
        DB_PATH = DB_IN_APP
    elif DB_IN_CWD.exists():
        DB_PATH = DB_IN_CWD
    else:
        DB_PATH = DB_IN_APP
    DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"
CONNECT_ARGS = {"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=CONNECT_ARGS, pool_pre_ping=True)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

LOGO_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_espaco_dinamico.png"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "ABC DINÂMICO.png"),
    "logo_espaco_dinamico.png",
    "ABC DINÂMICO.png",
]


# --------------------------- MODELOS -------------------------
class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    cpf = Column(String(14), unique=True, nullable=False)
    senha_hash = Column(String(256), nullable=False)
    perfil = Column(String(30), default="Admin", nullable=False)
    ativo = Column(Integer, default=1, nullable=False)


class Responsavel(Base):
    __tablename__ = "responsaveis"
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False, unique=True)
    telefone = Column(String(30))
    email = Column(String(150))
    alunos = relationship("Aluno", back_populates="responsavel")


class Aluno(Base):
    __tablename__ = "alunos"
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    data_nascimento = Column(Date, nullable=True)
    escolaridade = Column(String(100), nullable=True)
    responsavel_id = Column(Integer, ForeignKey("responsaveis.id"), nullable=True)
    ativo = Column(Integer, default=1, nullable=False)
    responsavel = relationship("Responsavel", back_populates="alunos")
    prontuarios = relationship("Prontuario", back_populates="aluno")
    contratos = relationship("Contrato", back_populates="aluno")
    atividades = relationship("AtividadeAluno", back_populates="aluno")


class Prontuario(Base):
    __tablename__ = "prontuarios"
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False)
    data_registro = Column(Date, default=date.today, nullable=False)
    queixa_principal = Column(Text)
    hipotese_diagnostica = Column(Text)
    conduta = Column(Text)
    aluno = relationship("Aluno", back_populates="prontuarios")


class Contrato(Base):
    __tablename__ = "contratos"
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False)
    descricao_servico = Column(String(150), default="Intervenção Neuropsicopedagógica")
    valor_mensalidade = Column(Float, nullable=False, default=0)
    dia_vencimento = Column(Integer, nullable=False, default=10)
    data_inicio = Column(Date)
    status = Column(String(20), default="Ativo")
    aluno = relationship("Aluno", back_populates="contratos")


class AtividadeAluno(Base):
    __tablename__ = "atividades_alunos"
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False)
    categoria = Column(String(50), default="Intervenção")
    data_atividade = Column(Date, default=date.today)
    titulo = Column(String(150), nullable=False)
    descricao = Column(Text)
    status = Column(String(30), default="Realizado")
    aluno = relationship("Aluno", back_populates="atividades")


class ConfiguracaoSistema(Base):
    __tablename__ = "configuracoes"
    id = Column(Integer, primary_key=True)
    chave = Column(String(80), unique=True, nullable=False)
    valor = Column(Text)


class LancamentoFinanceiro(Base):
    __tablename__ = "lancamentos_financeiros"
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=True)
    tipo = Column(String(20), nullable=False)  # Receita ou Despesa
    descricao = Column(String(200), nullable=False)
    categoria = Column(String(80), default="Geral")
    valor = Column(Float, nullable=False)
    data_vencimento = Column(Date, nullable=False)
    data_pagamento = Column(Date, nullable=True)
    status = Column(String(30), default="Pendente")
    observacao = Column(Text)
    aluno = relationship("Aluno")


def backup_sqlite_automatico():
    """Cria uma cópia diária antes de alterações no esquema, sem copiar banco aberto à força."""
    if not DATABASE_URL.startswith("sqlite:///"):
        return
    caminho_texto = urllib.parse.unquote(DATABASE_URL.split("sqlite:///", 1)[1])
    banco = Path(caminho_texto)
    if not banco.is_absolute():
        banco = (Path.cwd() / banco).resolve()
    if not banco.exists() or banco.name == ":memory:":
        return
    pasta_backup = BASE_DIR / "backups_banco"
    pasta_backup.mkdir(parents=True, exist_ok=True)
    destino = pasta_backup / f"{banco.stem}_{datetime.now():%Y%m%d}.db"
    if destino.exists():
        return
    # A API backup do SQLite é mais segura do que copiar um arquivo de banco em uso.
    origem_con = sqlite3.connect(str(banco), timeout=30)
    backup_con = sqlite3.connect(str(destino))
    try:
        origem_con.backup(backup_con)
    except Exception:
        backup_con.close()
        origem_con.close()
        try:
            destino.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        try:
            backup_con.close()
        except Exception:
            pass
        try:
            origem_con.close()
        except Exception:
            pass


# Cria backup diário antes de qualquer criação/alteração de tabelas.
try:
    backup_sqlite_automatico()
except Exception as exc:
    print(f"[AVISO] Backup automático não concluído: {exc}")
# create_all adds missing tables without deleting existing tables/rows.
Base.metadata.create_all(engine)


# --------------------------- UTILITÁRIOS ---------------------
def limpar_cpf(cpf):
    return re.sub(r"\D", "", str(cpf or ""))


def gerar_hash_senha(senha):
    # Compatível com os hashes SHA-256 da versão anterior.
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def verificar_senha(senha, senha_hash):
    # Mantém compatibilidade com os usuários existentes.
    return secrets.compare_digest(gerar_hash_senha(senha), senha_hash or "")


def criar_usuario_admin_padrao():
    db = SessionLocal()
    try:
        if db.query(Usuario).count() == 0:
            db.add(Usuario(
                nome="Administrador Espaço Dinâmico",
                cpf="00000000000",
                senha_hash=gerar_hash_senha("admin123"),
                perfil="Admin",
                ativo=1,
            ))
            db.commit()
    finally:
        db.close()


def obter_logo():
    for path in LOGO_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def para_str_br(valor):
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%d/%m/%Y")
    return str(valor) if valor not in (None, "") else "-"


def calcular_idade(data_nasc):
    if not data_nasc:
        return "-"
    hoje = date.today()
    anos = hoje.year - data_nasc.year - ((hoje.month, hoje.day) < (data_nasc.month, data_nasc.day))
    return f"{anos} anos"


def converter_data(texto):
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
    except (ValueError, AttributeError):
        return None


def moeda(valor):
    return f"R$ {float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def mensagem_erro(exc, contexto="operação"):
    st.error(f"Não foi possível concluir a {contexto}. Verifique os dados e tente novamente.")
    # Detalhe técnico apenas no terminal; não expõe informações internas na tela.
    print(f"[ERRO] {contexto}: {exc}")


def normalizar_texto(valor):
    """Normaliza texto para comparar nomes/categorias sem alterar o original."""
    return re.sub(r"\s+", " ", str(valor or "")).strip().casefold()


def localizar_coluna(df, termos, excluir=()):
    """Localiza uma coluna por palavras-chave, ignorando acentos não é obrigatório."""
    for coluna in df.columns:
        nome = str(coluna).casefold()
        if all(t.casefold() in nome for t in termos) and not any(x.casefold() in nome for x in excluir):
            return coluna
    return None


@st.cache_data(ttl=300, show_spinner=False)
def carregar_planilha_observacao_atendimento(url_sheets):
    """Importa a aba definida da planilha Google Sheets; retorna None em falha."""
    try:
        if not url_sheets or "docs.google.com/spreadsheets" not in url_sheets or "/d/" not in url_sheets:
            return None
        sheet_id = url_sheets.split("/d/", 1)[1].split("/", 1)[0]
        aba_nome = urllib.parse.quote("OBSERVAÇÃO DO ATENDIMENTO")
        csv_url = (f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
                   f"?tqx=out:csv&sheet={aba_nome}")
        df = pd.read_csv(csv_url, dtype=str, keep_default_na=False)
        df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
        return df
    except Exception as exc:
        print(f"[AVISO] Não foi possível carregar a planilha Google Sheets: {exc}")
        return None


def filtrar_e_analisar_aluno(df_obs, nome_aluno):
    """Filtra pelo nome exato normalizado e devolve colunas qualitativas F:M."""
    if df_obs is None or df_obs.empty:
        return pd.DataFrame(), []
    col_nome = localizar_coluna(df_obs, ("nome", "aluno"))
    if col_nome is None:
        col_nome = localizar_coluna(df_obs, ("nome",))
    if col_nome is None:
        return pd.DataFrame(), []
    termo = normalizar_texto(nome_aluno)
    mask = df_obs[col_nome].map(normalizar_texto).eq(termo)
    resultado = df_obs.loc[mask].copy()
    # Evita correspondência parcial ambígua: não seleciona todos os nomes que compartilham o primeiro nome.
    if resultado.empty:
        return pd.DataFrame(), []
    indicadores = [c for c in df_obs.columns[5:13]
                   if any(t in str(c).casefold() for t in ("participação", "participacao"))]
    # Fallback for older sheets without descriptive headers: use F:K, the six participation indicators.
    if not indicadores and len(df_obs.columns) >= 11:
        indicadores = list(df_obs.columns[5:11])
    # Datas de atendimento em ordem cronológica, mantendo o texto original da fonte.
    col_data = localizar_coluna(resultado, ("data",), excluir=("carimbo",))
    if col_data:
        resultado["__data_ordem"] = pd.to_datetime(resultado[col_data], dayfirst=True, errors="coerce")
        resultado = resultado.sort_values("__data_ordem", kind="stable", na_position="last")
        resultado = resultado.drop(columns=["__data_ordem"])
    return resultado, indicadores


def converter_coluna_numerica(serie):
    """Mantida para compatibilidade; não deve ser aplicada a classificações qualitativas."""
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce")
    def converter(valor):
        if pd.isna(valor):
            return None
        if isinstance(valor, (int, float)):
            return valor
        texto = str(valor).strip().replace("%", "")
        if not texto or texto in {"-", "—", "n/a", "N/A"}:
            return None
        texto = texto.replace("\u00a0", "").replace(" ", "")
        if "," in texto and "." in texto:
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                texto = texto.replace(",", "")
        elif "," in texto:
            texto = texto.replace(",", ".")
        try:
            return float(texto)
        except ValueError:
            return None
    return serie.map(converter).pipe(pd.to_numeric, errors="coerce")


def dividir_categorias(serie):
    """Divide respostas com várias categorias separadas por vírgula/ponto e vírgula."""
    itens = []
    for valor in serie.fillna("").astype(str):
        for parte in re.split(r"[,;\n]+", valor):
            parte = parte.strip()
            if parte and parte.casefold() not in {"nan", "não informado", "nao informado", "-"}:
                itens.append(parte)
    if not itens:
        return pd.Series(dtype="int64")
    return pd.Series(itens).value_counts().sort_values(ascending=False)


def preparar_datas_planilha(df):
    """Formata as colunas de data para exibição brasileira sem mudar o banco."""
    exibicao = df.copy()
    for coluna in exibicao.columns:
        nome = str(coluna).casefold()
        if "data" in nome or "carimbo" in nome or "timestamp" in nome:
            convertido = pd.to_datetime(exibicao[coluna], dayfirst=True, errors="coerce")
            mascara = convertido.notna()
            if mascara.any():
                exibicao[coluna] = exibicao[coluna].astype(str)
                exibicao.loc[mascara, coluna] = convertido[mascara].dt.strftime("%d/%m/%Y")
    return exibicao


# --------------------------- DESIGN --------------------------
def aplicar_estilo_global():
    # Estilo global com area superior segura.
    st.markdown("""
    <style>
      :root { --navy:#142b4a; --blue:#087e8b; --cyan:#20b8b0; --ink:#172b4d; }
      .stApp { background:#f4f7fb; color:var(--ink); }
      [data-testid="stSidebar"] { background:linear-gradient(180deg,#142b4a 0%,#1b4263 100%); }
      [data-testid="stSidebar"] * { color:#f8fafc; }
      div[data-testid="stMetric"] { background:#fff; border:1px solid #e4eaf2; border-radius:15px; padding:17px 18px; box-shadow:0 5px 18px rgba(20,43,74,.05); }
      div[data-testid="stMetricLabel"] { color:#64748b; }
      div[data-testid="stMetricValue"] { color:#142b4a; }
      .stAppViewBlockContainer, .main .block-container, [data-testid="stAppViewContainer"] .block-container {
        padding-top: 1.25rem !important; padding-bottom: 2.5rem !important;
      }
      /* O wrapper do Streamlit fica sticky; o restante da página continua rolando normalmente. */
      div[data-testid="stMarkdown"]:has(.ed-header) {
        position: sticky; top: 0.45rem; z-index: 1000; align-self: stretch;
        background: #f4f7fb; padding-top: 0.15rem; padding-bottom: 0.25rem;
      }
      .ed-header { position:relative; top:auto; left:auto; right:auto; z-index:1; display:flex; align-items:center; gap:22px; width:100%; min-height:108px; padding:18px 22px; margin:0; box-sizing:border-box; overflow:visible; background:linear-gradient(110deg,rgba(255,255,255,.99) 0%,rgba(248,251,255,.99) 100%); border:1px solid #e5ebf3; border-radius:16px; box-shadow:0 8px 24px rgba(20,43,74,.12); }
      .ed-header-logo { flex:0 0 82px; display:flex; align-items:center; justify-content:center; }
      .ed-header-logo img { max-width:78px; max-height:78px; object-fit:contain; }
      .ed-header-title { flex:1 1 auto; min-width:0; padding:4px 0; }
      .ed-header-title h1 { margin:0 !important; padding:0 !important; color:#142b4a; font-size:clamp(1.45rem,2.4vw,2rem); line-height:1.28 !important; font-weight:800; overflow-wrap:anywhere; }
      .ed-header-title p { margin:6px 0 0 0 !important; color:#64748b; font-size:.92rem; line-height:1.45 !important; }
      .ed-profissional { flex:0 0 230px; text-align:right; padding:8px 0 8px 12px; min-height:68px; box-sizing:border-box; display:flex; flex-direction:column; justify-content:center; line-height:1.55; overflow:visible; border-left:1px solid #e2e8f0; }
      .ed-profissional strong { display:block; color:#142b4a; font-size:1.02rem; white-space:normal; overflow-wrap:anywhere; margin:0 0 3px 0; }
      .ed-profissional span { color:#64748b; font-size:.88rem; }
      @media (max-width: 900px) { div[data-testid="stMarkdown"]:has(.ed-header) { top:0; } .ed-header { gap:12px; padding:13px 15px; flex-wrap:wrap; } .ed-header-logo { flex-basis:60px; } .ed-header-logo img { max-width:58px; max-height:58px; } .ed-profissional { flex:1 1 100%; text-align:left; border-left:0; border-top:1px solid #e2e8f0; padding:8px 0 0 0; min-height:0; } }
      @media (min-width: 901px) and (max-width: 1100px) { .ed-header { gap:12px; padding:15px; } .ed-profissional { flex-basis:190px; } }
      .stButton > button, .stFormSubmitButton > button { border-radius:9px; font-weight:600; min-height:2.55rem; }
      div[data-testid="stTabs"] button { font-weight:600; }
      [data-testid="stSidebar"] div.st-key-sair_sistema button { background:rgba(255,255,255,.10) !important; color:#fff !important; border:1px solid rgba(255,255,255,.28) !important; }
      [data-testid="stSidebar"] div.st-key-sair_sistema button:hover { background:rgba(255,255,255,.20) !important; border-color:rgba(255,255,255,.55) !important; }
      [data-testid="stSidebar"] div.st-key-sair_sistema button p { color:#fff !important; }
      .ed-note { background:#e8f7f6; border-left:4px solid #20b8b0; padding:12px 15px; border-radius:8px; }
    </style>
    """, unsafe_allow_html=True)


def cabecalho(logo):
    # Cabecalho em bloco unico HTML.
    logo_html = ""
    if logo and os.path.isfile(logo):
        try:
            import base64
            with open(logo, "rb") as arquivo_logo:
                codificado = base64.b64encode(arquivo_logo.read()).decode("ascii")
            ext = Path(logo).suffix.lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            logo_html = f'<div class="ed-header-logo"><img src="data:{mime};base64,{codificado}" alt="Logo Espaço Dinâmico"></div>'
        except OSError as exc:
            print(f"[AVISO] Não foi possível carregar a logo no cabeçalho: {exc}")
    if not logo_html:
        logo_html = '<div class="ed-header-logo" aria-label="Espaço Dinâmico"><span style="font-size:2.5rem">🧩</span></div>'
    bloco = f'''<section class="ed-header" role="banner">
      {logo_html}
      <div class="ed-header-title"><h1>Espaço Dinâmico</h1><p>Sistema Integrado de Gestão Neuropsicopedagógica</p></div>
      <div class="ed-profissional"><strong>Larissa Lyrio</strong><span>Neuropsicopedagoga</span></div>
    </section>'''
    st.markdown(bloco, unsafe_allow_html=True)


def exibir_grafico_barras_fino(df, categoria, valor, titulo, chave):
    # Grafico horizontal com rotulos completos.
    if df is None or df.empty or categoria not in df.columns or valor not in df.columns:
        st.info("Não há dados suficientes para montar este gráfico.")
        return
    graf = df[[categoria, valor]].copy()
    graf[categoria] = graf[categoria].astype(str).str.strip()
    graf[valor] = pd.to_numeric(graf[valor], errors="coerce")
    graf = graf.dropna(subset=[categoria, valor])
    graf = graf[graf[categoria].ne("")].sort_values(valor, ascending=True)
    if graf.empty:
        st.info("Não há dados válidos para montar este gráfico.")
        return
    graf["__rotulo"] = graf[categoria].map(lambda x: "<br>".join(textwrap.wrap(x, width=28, break_long_words=False, break_on_hyphens=False)) or x)
    altura = max(220, min(640, 54 * len(graf) + 75))
    fig = px.bar(graf, x=valor, y="__rotulo", orientation="h", text=valor,
                 custom_data=[categoria], color_discrete_sequence=["#168b9a"])
    fig.update_traces(width=0.48, textposition="outside", cliponaxis=False,
        marker_line_width=0,
        hovertemplate="<b>%{customdata[0]}</b><br>" + valor + ": %{x}<extra></extra>",
        textfont={"size": 11, "color": "#334155"})
    fig.update_layout(title={"text": titulo, "x": 0, "xanchor": "left", "font": {"size": 16, "color": "#142b4a"}},
        height=altura, autosize=True, showlegend=False,
        margin={"l": 18, "r": 55, "t": 62, "b": 24},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        bargap=0.62, font={"family": "Arial, sans-serif", "size": 11, "color": "#334155"},
        xaxis={"title": None, "showgrid": True, "gridcolor": "#e8edf4", "zeroline": False, "rangemode": "tozero", "automargin": True},
        yaxis={"title": None, "showgrid": False, "automargin": True, "tickfont": {"size": 11}},
        hoverlabel={"bgcolor": "#142b4a", "font": {"color": "#ffffff"}})
    st.plotly_chart(fig, use_container_width=True, key=chave,
                    config={"displayModeBar": False, "responsive": True})


# --------------------------- LOGIN ---------------------------
def renderizar_tela_login(db, logo):
    aplicar_estilo_global()
    st.markdown("<div style='height:3vh'></div>", unsafe_allow_html=True)
    esquerda, centro, direita = st.columns([1, 1.25, 1])
    with centro:
        if logo:
            _, imgcol, _ = st.columns([1, 1, 1])
            with imgcol:
                st.image(logo, use_container_width=True)
        st.markdown("<h1 style='text-align:center;color:#142b4a'>Espaço Dinâmico</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;color:#64748b'>Larissa Lyrio · Neuropsicopedagoga</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.subheader("🔐 Acesso ao sistema")
            with st.form("form_login", clear_on_submit=False):
                cpf = st.text_input("CPF", max_chars=14, placeholder="Digite apenas os números")
                senha = st.text_input("Senha", type="password")
                enviar = st.form_submit_button("Entrar", use_container_width=True, type="primary")
            if enviar:
                usuario = db.query(Usuario).filter(Usuario.cpf == limpar_cpf(cpf)).first()
                if usuario and usuario.ativo == 1 and verificar_senha(senha, usuario.senha_hash):
                    st.session_state["usuario_id"] = usuario.id
                    st.session_state["usuario_logado"] = usuario.nome
                    st.session_state["perfil_usuario"] = usuario.perfil
                    st.rerun()
                else:
                    st.error("CPF ou senha incorretos, ou usuário inativo.")
        st.caption("A sessão desta versão é mantida pelo Streamlit. Login persistente após recarregar o navegador requer configuração adicional de autenticação/cookies.")


# --------------------------- TELAS ---------------------------
def tela_painel(db):
    st.title("Painel de gestão")
    alunos = db.query(Aluno).filter_by(ativo=1).count()
    responsaveis = db.query(Responsavel).count()
    contratos = db.query(Contrato).filter_by(status="Ativo").count()
    prontuarios = db.query(Prontuario).count()
    receitas_pendentes = db.query(LancamentoFinanceiro).filter_by(tipo="Receita", status="Pendente").all()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Alunos ativos", alunos)
    c2.metric("Responsáveis", responsaveis)
    c3.metric("Contratos ativos", contratos)
    c4.metric("Registros de prontuário", prontuarios)
    c5.metric("Receitas pendentes", moeda(sum(x.valor for x in receitas_pendentes)))
    st.subheader("Alunos cadastrados")
    lista = db.query(Aluno).filter_by(ativo=1).order_by(Aluno.nome).all()
    if lista:
        st.dataframe(pd.DataFrame([{
            "ID": a.id, "Aluno": a.nome, "Nascimento": para_str_br(a.data_nascimento),
            "Idade": calcular_idade(a.data_nascimento), "Escolaridade": a.escolaridade or "-",
            "Responsável": a.responsavel.nome if a.responsavel else "-",
        } for a in lista]), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum aluno ativo cadastrado.")


def tela_cadastros(db):
    st.title("Alunos e responsáveis")
    tab1, tab2, tab3, tab4 = st.tabs([
        "➕ Cadastrar responsável", "➕ Cadastrar aluno", "✏️ Gerenciar alunos", "👥 Gerenciar responsáveis"
    ])

    with tab1:
        with st.form("f_resp", clear_on_submit=True):
            nome = st.text_input("Nome completo *")
            telefone = st.text_input("Telefone / WhatsApp")
            email = st.text_input("E-mail")
            salvar_resp = st.form_submit_button("Salvar responsável", type="primary")
        if salvar_resp:
            if not nome.strip():
                st.error("Informe o nome do responsável.")
            else:
                try:
                    db.add(Responsavel(nome=nome.strip(), telefone=telefone.strip(), email=email.strip()))
                    db.commit()
                    st.success("Responsável cadastrado.")
                    st.rerun()
                except IntegrityError:
                    db.rollback()
                    st.error("Já existe um responsável com esse nome.")
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "cadastro do responsável")

    with tab2:
        responsaveis = db.query(Responsavel).order_by(Responsavel.nome).all()
        mapa_resp = {f"{r.id} — {r.nome}": r.id for r in responsaveis}
        with st.form("f_aluno", clear_on_submit=True):
            nome_aluno = st.text_input("Nome completo do aluno *")
            nasc = st.date_input("Data de nascimento", value=None, min_value=date(1900, 1, 1), max_value=date.today(), format="DD/MM/YYYY")
            escolaridade = st.text_input("Escolaridade")
            resp_sel = st.selectbox("Responsável", ["Não informado"] + list(mapa_resp.keys()))
            salvar_aluno = st.form_submit_button("Salvar aluno", type="primary")
        if salvar_aluno:
            if not nome_aluno.strip():
                st.error("Informe o nome do aluno.")
            else:
                try:
                    db.add(Aluno(nome=nome_aluno.strip(), data_nascimento=nasc,
                                 escolaridade=escolaridade.strip(), responsavel_id=mapa_resp.get(resp_sel), ativo=1))
                    db.commit()
                    st.success("Aluno cadastrado.")
                    st.rerun()
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "cadastro do aluno")

    with tab3:
        alunos = db.query(Aluno).order_by(Aluno.nome).all()
        if not alunos:
            st.info("Não há alunos cadastrados.")
        else:
            mapa_alunos = {f"{a.id} — {a.nome}{'' if a.ativo else ' (inativo)'}": a.id for a in alunos}
            escolha = st.selectbox("Selecione o aluno para editar", list(mapa_alunos), key="gerenciar_aluno_sel")
            aluno = db.get(Aluno, mapa_alunos[escolha])
            responsaveis = db.query(Responsavel).order_by(Responsavel.nome).all()
            resp_map = {"Não informado": None}
            resp_map.update({f"{r.id} — {r.nome}": r.id for r in responsaveis})
            atual_resp = next((k for k, v in resp_map.items() if v == aluno.responsavel_id), "Não informado")
            with st.form(f"f_editar_aluno_{aluno.id}"):
                nome_edit = st.text_input("Nome", value=aluno.nome)
                nasc_edit = st.date_input("Nascimento", value=aluno.data_nascimento or date.today(), min_value=date(1900, 1, 1), max_value=date.today(), format="DD/MM/YYYY")
                esc_edit = st.text_input("Escolaridade", value=aluno.escolaridade or "")
                resp_edit = st.selectbox("Responsável", list(resp_map), index=list(resp_map).index(atual_resp))
                ativo_edit = st.checkbox("Aluno ativo", value=bool(aluno.ativo))
                salvar_edit = st.form_submit_button("Salvar alterações", type="primary")
            if salvar_edit:
                if not nome_edit.strip():
                    st.error("O nome do aluno é obrigatório.")
                else:
                    try:
                        aluno.nome = nome_edit.strip()
                        aluno.data_nascimento = nasc_edit
                        aluno.escolaridade = esc_edit.strip()
                        aluno.responsavel_id = resp_map[resp_edit]
                        aluno.ativo = 1 if ativo_edit else 0
                        db.commit()
                        st.success("Cadastro do aluno atualizado.")
                        st.rerun()
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "edição do aluno")
            st.caption("A inativação preserva prontuários, contratos, atividades e lançamentos vinculados.")
            if aluno.ativo:
                if st.button("Inativar aluno", key=f"inativar_aluno_{aluno.id}"):
                    aluno.ativo = 0
                    db.commit()
                    st.success("Aluno inativado; histórico preservado.")
                    st.rerun()
            else:
                if st.button("Reativar aluno", key=f"reativar_aluno_{aluno.id}"):
                    aluno.ativo = 1
                    db.commit()
                    st.success("Aluno reativado.")
                    st.rerun()

    with tab4:
        responsaveis = db.query(Responsavel).order_by(Responsavel.nome).all()
        if not responsaveis:
            st.info("Não há responsáveis cadastrados.")
        else:
            st.dataframe(pd.DataFrame([{
                "ID": r.id, "Nome": r.nome, "Telefone": r.telefone or "", "E-mail": r.email or "",
                "Alunos vinculados": len(r.alunos)
            } for r in responsaveis]), use_container_width=True, hide_index=True)
            mapa_r = {f"{r.id} — {r.nome}": r.id for r in responsaveis}
            escolha_r = st.selectbox("Selecione o responsável para editar", list(mapa_r), key="gerenciar_resp_sel")
            responsavel = db.get(Responsavel, mapa_r[escolha_r])
            with st.form(f"f_editar_resp_{responsavel.id}"):
                nome_r = st.text_input("Nome completo", value=responsavel.nome)
                telefone_r = st.text_input("Telefone / WhatsApp", value=responsavel.telefone or "")
                email_r = st.text_input("E-mail", value=responsavel.email or "")
                salvar_r = st.form_submit_button("Salvar responsável", type="primary")
            if salvar_r:
                if not nome_r.strip():
                    st.error("O nome é obrigatório.")
                else:
                    try:
                        responsavel.nome = nome_r.strip()
                        responsavel.telefone = telefone_r.strip()
                        responsavel.email = email_r.strip()
                        db.commit()
                        st.success("Responsável atualizado.")
                        st.rerun()
                    except IntegrityError:
                        db.rollback()
                        st.error("Já existe outro responsável com esse nome.")
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "edição do responsável")
            if responsavel.alunos:
                st.info("Este responsável possui aluno(s) vinculado(s). Para preservar o histórico, a exclusão física não é disponibilizada.")
            else:
                st.warning("Este responsável não possui alunos vinculados. A exclusão física é irreversível.")
                confirmar = st.checkbox("Confirmo que desejo excluir permanentemente este responsável", key=f"conf_excluir_resp_{responsavel.id}")
                if st.button("Excluir responsável", key=f"excluir_resp_{responsavel.id}", disabled=not confirmar):
                    try:
                        db.delete(responsavel)
                        db.commit()
                        st.success("Responsável excluído.")
                        st.rerun()
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "exclusão do responsável")

def tela_contratos(db):
    st.title("Contratos e mensalidades")
    alunos = db.query(Aluno).filter_by(ativo=1).order_by(Aluno.nome).all()
    mapa = {f"{a.id} — {a.nome}": a.id for a in alunos}
    tab1, tab2 = st.tabs(["➕ Novo contrato", "✏️ Consultar e gerenciar contratos"])
    with tab1:
        if not mapa:
            st.info("Cadastre um aluno ativo antes de criar um contrato.")
        else:
            with st.form("f_contrato", clear_on_submit=True):
                aluno_label = st.selectbox("Aluno", list(mapa))
                servico = st.text_input("Descrição do serviço", "Intervenção Neuropsicopedagógica")
                valor = st.number_input("Mensalidade (R$)", min_value=0.0, value=350.0, step=25.0)
                vencimento = st.number_input("Dia de vencimento", min_value=1, max_value=31, value=10)
                inicio = st.date_input("Data de início", value=date.today(), format="DD/MM/YYYY")
                criar = st.form_submit_button("Criar contrato", type="primary")
            if criar:
                if not servico.strip():
                    st.error("Informe a descrição do serviço.")
                else:
                    try:
                        db.add(Contrato(aluno_id=mapa[aluno_label], descricao_servico=servico.strip(),
                                        valor_mensalidade=valor, dia_vencimento=int(vencimento), data_inicio=inicio, status="Ativo"))
                        db.commit()
                        st.success("Contrato criado.")
                        st.rerun()
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "criação do contrato")
    with tab2:
        contratos = db.query(Contrato).order_by(Contrato.id.desc()).all()
        if not contratos:
            st.info("Nenhum contrato cadastrado.")
            return
        st.dataframe(pd.DataFrame([{
            "ID": c.id, "Aluno": c.aluno.nome if c.aluno else "Aluno não localizado",
            "Serviço": c.descricao_servico or "", "Mensalidade": moeda(c.valor_mensalidade),
            "Vencimento": f"Dia {c.dia_vencimento}", "Início": para_str_br(c.data_inicio), "Status": c.status
        } for c in contratos]), use_container_width=True, hide_index=True)
        cmap = {f"{c.id} — {c.aluno.nome if c.aluno else 'Aluno não localizado'} — {c.status}": c.id for c in contratos}
        selecionado = st.selectbox("Selecione o contrato para editar", list(cmap), key="contrato_editar_sel")
        contrato = db.get(Contrato, cmap[selecionado])
        with st.form(f"f_editar_contrato_{contrato.id}"):
            servico_e = st.text_input("Serviço", value=contrato.descricao_servico or "")
            valor_e = st.number_input("Mensalidade (R$)", min_value=0.0, value=float(contrato.valor_mensalidade or 0), step=25.0)
            venc_e = st.number_input("Dia de vencimento", min_value=1, max_value=31, value=int(contrato.dia_vencimento or 10))
            status_opcoes = ["Ativo", "Suspenso", "Encerrado"]
            status_atual = contrato.status if contrato.status in status_opcoes else "Ativo"
            status_e = st.selectbox("Situação", status_opcoes, index=status_opcoes.index(status_atual))
            salvar_e = st.form_submit_button("Salvar alterações", type="primary")
        if salvar_e:
            if not servico_e.strip():
                st.error("Informe a descrição do serviço.")
            else:
                contrato.descricao_servico = servico_e.strip()
                contrato.valor_mensalidade = float(valor_e)
                contrato.dia_vencimento = int(venc_e)
                contrato.status = status_e
                try:
                    db.commit()
                    st.success("Contrato atualizado.")
                    st.rerun()
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "edição do contrato")
        st.caption("Para preservar o histórico financeiro, contratos não são apagados: use o status Encerrado.")

def tela_prontuario(db):
    st.title("Prontuários e evolução")
    alunos = db.query(Aluno).filter_by(ativo=1).order_by(Aluno.nome).all()
    if not alunos:
        st.info("Cadastre um aluno ativo antes de registrar uma evolução.")
        return
    mapa = {f"{a.id} — {a.nome}": a.id for a in alunos}
    aluno_label = st.selectbox("Aluno", list(mapa), key="prontuario_aluno")
    aluno_id = mapa[aluno_label]
    tab1, tab2 = st.tabs(["➕ Nova evolução", "📚 Consultar e editar histórico"])
    with tab1:
        with st.form("f_prontuario_novo", clear_on_submit=True):
            data_reg = st.date_input("Data do registro", value=date.today(), format="DD/MM/YYYY")
            queixa = st.text_area("Queixa principal / observações")
            hipotese = st.text_area("Hipóteses / aspectos em investigação")
            conduta = st.text_area("Conduta / intervenção realizada")
            salvar = st.form_submit_button("Salvar evolução", type="primary")
        if salvar:
            if not any([queixa.strip(), hipotese.strip(), conduta.strip()]):
                st.error("Preencha pelo menos um campo antes de salvar.")
            else:
                try:
                    db.add(Prontuario(aluno_id=aluno_id, data_registro=data_reg,
                                      queixa_principal=queixa.strip(), hipotese_diagnostica=hipotese.strip(), conduta=conduta.strip()))
                    db.commit()
                    st.success("Registro salvo.")
                    st.rerun()
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "salvamento da evolução")
    with tab2:
        registros = db.query(Prontuario).filter_by(aluno_id=aluno_id).order_by(Prontuario.data_registro.desc(), Prontuario.id.desc()).all()
        if not registros:
            st.info("Nenhuma evolução registrada para este aluno.")
        else:
            st.dataframe(pd.DataFrame([{
                "ID": p.id, "Data": para_str_br(p.data_registro),
                "Queixa / observações": p.queixa_principal or "", "Hipóteses": p.hipotese_diagnostica or "", "Conduta": p.conduta or ""
            } for p in registros]), use_container_width=True, hide_index=True)
            mapa_p = {f"Registro #{p.id} — {para_str_br(p.data_registro)}": p.id for p in registros}
            escolha_p = st.selectbox("Selecione a evolução para editar", list(mapa_p), key=f"prontuario_editar_{aluno_id}")
            p = db.get(Prontuario, mapa_p[escolha_p])
            with st.form(f"f_editar_prontuario_{p.id}"):
                data_e = st.date_input("Data do registro", value=p.data_registro or date.today(), format="DD/MM/YYYY")
                queixa_e = st.text_area("Queixa principal / observações", value=p.queixa_principal or "")
                hipotese_e = st.text_area("Hipóteses / aspectos em investigação", value=p.hipotese_diagnostica or "")
                conduta_e = st.text_area("Conduta / intervenção realizada", value=p.conduta or "")
                salvar_e = st.form_submit_button("Salvar alterações", type="primary")
            if salvar_e:
                if not any([queixa_e.strip(), hipotese_e.strip(), conduta_e.strip()]):
                    st.error("O registro precisa conter pelo menos um campo preenchido.")
                else:
                    p.data_registro = data_e
                    p.queixa_principal = queixa_e.strip()
                    p.hipotese_diagnostica = hipotese_e.strip()
                    p.conduta = conduta_e.strip()
                    try:
                        db.commit()
                        st.success("Evolução atualizada.")
                        st.rerun()
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "edição da evolução")
            st.warning("Prontuários são registros históricos sensíveis. A exclusão física não é disponibilizada nesta tela; corrija o conteúdo mantendo o histórico no sistema.")

def tela_atividades(db):
    st.title("Atividades pedagógicas")
    alunos = db.query(Aluno).order_by(Aluno.nome).all()
    if not alunos:
        st.info("Cadastre um aluno antes de registrar atividades.")
        return
    mapa = {f"{a.id} — {a.nome}{'' if a.ativo else ' (inativo)'}": a.id for a in alunos}
    categorias = ["Intervenção", "Leitura", "Escrita", "Matemática", "Atenção", "Memória", "Outro"]
    status_opcoes = ["Planejada", "Realizada", "Reagendada", "Cancelada"]
    tab1, tab2 = st.tabs(["➕ Nova atividade", "✏️ Consultar e gerenciar atividades"])
    with tab1:
        alunos_ativos = {k: v for k, v in mapa.items() if db.get(Aluno, v).ativo}
        if not alunos_ativos:
            st.info("Não há alunos ativos para vincular à nova atividade.")
        else:
            with st.form("f_atividade_nova", clear_on_submit=True):
                aluno_sel = st.selectbox("Aluno", list(alunos_ativos))
                titulo = st.text_input("Título da atividade *")
                categoria = st.selectbox("Categoria", categorias)
                data_atividade = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
                descricao = st.text_area("Descrição / objetivo / observações")
                status = st.selectbox("Situação", status_opcoes, index=1)
                salvar = st.form_submit_button("Salvar atividade", type="primary")
            if salvar:
                if not titulo.strip():
                    st.error("Informe o título da atividade.")
                else:
                    try:
                        db.add(AtividadeAluno(aluno_id=alunos_ativos[aluno_sel], titulo=titulo.strip(), categoria=categoria,
                                              data_atividade=data_atividade, descricao=descricao.strip(), status=status))
                        db.commit()
                        st.success("Atividade registrada.")
                        st.rerun()
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "cadastro da atividade")
    with tab2:
        registros = db.query(AtividadeAluno).order_by(AtividadeAluno.data_atividade.desc(), AtividadeAluno.id.desc()).all()
        if not registros:
            st.info("Nenhuma atividade registrada.")
            return
        filtro_aluno = st.selectbox("Filtrar por aluno", ["Todos"] + list(mapa), key="filtro_atividades_aluno")
        filtro_status = st.selectbox("Filtrar situação", ["Todas"] + status_opcoes, key="filtro_atividades_status")
        filtrados = registros
        if filtro_aluno != "Todos":
            filtrados = [r for r in filtrados if r.aluno_id == mapa[filtro_aluno]]
        if filtro_status != "Todas":
            filtrados = [r for r in filtrados if r.status == filtro_status]
        st.dataframe(pd.DataFrame([{
            "ID": r.id, "Aluno": r.aluno.nome if r.aluno else "-", "Data": para_str_br(r.data_atividade),
            "Título": r.titulo, "Categoria": r.categoria, "Situação": r.status, "Descrição": r.descricao or ""
        } for r in filtrados]), use_container_width=True, hide_index=True)
        if filtrados:
            mapa_ativ = {f"#{r.id} — {r.aluno.nome if r.aluno else '-'} — {r.titulo} — {para_str_br(r.data_atividade)}": r.id for r in filtrados}
            escolha = st.selectbox("Selecione a atividade para editar", list(mapa_ativ), key="atividade_editar_sel")
            atividade = db.get(AtividadeAluno, mapa_ativ[escolha])
            with st.form(f"f_editar_atividade_{atividade.id}"):
                aluno_e = st.selectbox("Aluno", list(mapa), index=list(mapa.values()).index(atividade.aluno_id))
                titulo_e = st.text_input("Título", value=atividade.titulo)
                cat_atual = atividade.categoria if atividade.categoria in categorias else "Outro"
                cat_e = st.selectbox("Categoria", categorias, index=categorias.index(cat_atual))
                data_e = st.date_input("Data", value=atividade.data_atividade or date.today(), format="DD/MM/YYYY")
                desc_e = st.text_area("Descrição / objetivo / observações", value=atividade.descricao or "")
                st_atual = atividade.status if atividade.status in status_opcoes else "Planejada"
                status_e = st.selectbox("Situação", status_opcoes, index=status_opcoes.index(st_atual))
                salvar_e = st.form_submit_button("Salvar alterações", type="primary")
            if salvar_e:
                if not titulo_e.strip():
                    st.error("O título é obrigatório.")
                else:
                    atividade.aluno_id = mapa[aluno_e]
                    atividade.titulo = titulo_e.strip()
                    atividade.categoria = cat_e
                    atividade.data_atividade = data_e
                    atividade.descricao = desc_e.strip()
                    atividade.status = status_e
                    try:
                        db.commit()
                        st.success("Atividade atualizada.")
                        st.rerun()
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "edição da atividade")
            st.caption("Para preservar o histórico, use a situação Cancelada em vez de excluir definitivamente uma atividade.")

def tela_desempenho(db):
    st.title("Desempenho e planilha mestre")
    st.caption("Análise qualitativa por aluno, com evolução cronológica, distribuição das classificações e frequência das dificuldades.")
    cfg = db.query(ConfiguracaoSistema).filter_by(chave="link_planilha_mestre").first()
    link_atual = cfg.valor if cfg else ""
    with st.form("f_mestre"):
        st.write("Configure uma única vez o link da planilha mestre do Google Sheets. A aba esperada é OBSERVAÇÃO DO ATENDIMENTO.")
        novo_link = st.text_input("Link da planilha", value=link_atual or "")
        salvar = st.form_submit_button("Salvar configuração", type="primary")
    if salvar:
        if novo_link.strip() and "docs.google.com/spreadsheets" not in novo_link:
            st.error("Informe um link válido do Google Sheets.")
        else:
            if cfg:
                cfg.valor = novo_link.strip()
            else:
                db.add(ConfiguracaoSistema(chave="link_planilha_mestre", valor=novo_link.strip()))
            db.commit()
            carregar_planilha_observacao_atendimento.clear()
            st.success("Configuração salva.")
            st.rerun()
    st.divider()
    alunos = db.query(Aluno).filter_by(ativo=1).order_by(Aluno.nome).all()
    if not link_atual:
        st.info("Configure a planilha para consultar os indicadores.")
        return
    if not alunos:
        st.info("Cadastre alunos antes de consultar indicadores.")
        return
    mapa = {f"{a.id} — {a.nome}": a.nome for a in alunos}
    selecionado = st.selectbox("Aluno para análise", list(mapa.keys()))
    nome_aluno = mapa[selecionado]
    if st.button("🔄 Atualizar dados da planilha"):
        carregar_planilha_observacao_atendimento.clear()
    with st.spinner("Lendo a planilha mestre..."):
        df = carregar_planilha_observacao_atendimento(link_atual)
    if df is None:
        st.error("Não foi possível ler a planilha. Confira se o link está correto e se a planilha permite leitura pelo link.")
        st.caption("Se a planilha exigir login institucional, a importação CSV pública pode não funcionar; será necessário configurar autenticação compatível.")
        return
    if df.empty:
        st.warning("A aba foi lida, mas não contém registros.")
        return
    df_aluno, indicadores = filtrar_e_analisar_aluno(df, nome_aluno)
    if df_aluno.empty:
        col_nome = localizar_coluna(df, ("nome", "aluno")) or localizar_coluna(df, ("nome",))
        st.warning(f"Nenhum registro encontrado para {nome_aluno}. Confira a grafia do nome na coluna '{col_nome or 'Nome'}'.")
        with st.expander("Diagnóstico da importação"):
            st.write(f"Linhas importadas: {len(df)}")
            st.write("Colunas identificadas:")
            st.code("\n".join(str(c) for c in df.columns))
        return

    # Cards de resumo sem transformar classificações em notas numéricas.
    st.success(f"{len(df_aluno)} registro(s) encontrado(s) para {nome_aluno}.")
    col_data = localizar_coluna(df_aluno, ("data",), excluir=("carimbo",))
    col_compreensao = localizar_coluna(df_aluno, ("compreensão",)) or localizar_coluna(df_aluno, ("compreensao",))
    col_dificuldades = localizar_coluna(df_aluno, ("dificuldades",))
    col_conteudo = localizar_coluna(df_aluno, ("conteúdo trabalhado",)) or localizar_coluna(df_aluno, ("conteudo trabalhado",))
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros encontrados", len(df_aluno))
    if col_data:
        datas = pd.to_datetime(df_aluno[col_data], dayfirst=True, errors="coerce").dropna()
        c2.metric("Primeiro atendimento", datas.min().strftime("%d/%m/%Y") if not datas.empty else "—")
        c3.metric("Atendimento mais recente", datas.max().strftime("%d/%m/%Y") if not datas.empty else "—")
    else:
        c2.metric("Datas identificadas", "Não localizada")
        c3.metric("Indicadores", len(indicadores))

    with st.expander("📋 Registros importados do aluno", expanded=True):
        st.dataframe(preparar_datas_planilha(df_aluno), use_container_width=True, hide_index=True)
        csv_aluno = preparar_datas_planilha(df_aluno).to_csv(index=False).encode("utf-8-sig")
        st.download_button("Exportar registros deste aluno (CSV)", data=csv_aluno,
                           file_name="desempenho_aluno.csv", mime="text/csv")

    st.subheader("📊 Distribuição das classificações qualitativas")
    if indicadores:
        escolhas = [c for c in indicadores if df_aluno[c].astype(str).str.strip().ne("").any()]
        if escolhas:
            indicador_sel = st.selectbox("Indicador para analisar", escolhas, key="indicador_qualitativo")
            distribuicao = df_aluno[indicador_sel].astype(str).str.strip()
            distribuicao = distribuicao[~distribuicao.str.casefold().isin(["", "nan", "none", "-", "não informado", "nao informado"])]
            if not distribuicao.empty:
                contagem = distribuicao.value_counts().rename_axis("Classificação").reset_index(name="Quantidade")
                exibir_grafico_barras_fino(contagem, "Classificação", "Quantidade", f"Classificações — {indicador_sel}", "grafico_classificacoes")
                st.dataframe(contagem, use_container_width=True, hide_index=True)
            else:
                st.info("O indicador selecionado não possui respostas preenchidas.")
        else:
            st.info("As colunas F a M foram identificadas, mas não possuem respostas preenchidas para este aluno.")

        st.subheader("📈 Evolução por data de atendimento")
        if col_data:
            df_evolucao = df_aluno.copy()
            df_evolucao["Data do atendimento"] = pd.to_datetime(df_evolucao[col_data], dayfirst=True, errors="coerce")
            df_evolucao = df_evolucao.dropna(subset=["Data do atendimento"]).sort_values("Data do atendimento")
            if not df_evolucao.empty:
                # Exibe as classificações como registros qualitativos por atendimento, sem inventar escala numérica.
                colunas_evolucao = [c for c in indicadores if df_evolucao[c].astype(str).str.strip().ne("").any()]
                if colunas_evolucao:
                    tabela_evolucao = df_evolucao[["Data do atendimento"] + colunas_evolucao].copy()
                    tabela_evolucao["Data do atendimento"] = tabela_evolucao["Data do atendimento"].dt.strftime("%d/%m/%Y")
                    st.dataframe(tabela_evolucao, use_container_width=True, hide_index=True)
                    st.caption("A evolução é apresentada como histórico qualitativo. As classificações não são convertidas em notas nem em uma escala artificial.")
                else:
                    st.info("Não há indicadores preenchidos para mostrar a evolução.")
            else:
                st.info("Não foram reconhecidas datas válidas na coluna de data do atendimento.")
        else:
            st.info("Não foi identificada uma coluna de data de atendimento para ordenar a evolução.")
    else:
        st.warning("Não foi possível localizar as colunas de indicadores F a M. Confira a estrutura da aba de origem.")

    if col_compreensao:
        st.subheader("🧠 Compreensão do conteúdo")
        comp = df_aluno[col_compreensao].astype(str).str.strip()
        comp = comp[~comp.str.casefold().isin(["", "nan", "none", "-"])]
        if not comp.empty:
            comp_count = comp.value_counts().rename_axis("Resposta").reset_index(name="Quantidade")
            exibir_grafico_barras_fino(comp_count, "Resposta", "Quantidade", "Respostas sobre compreensão", "grafico_compreensao")
            st.dataframe(comp_count, use_container_width=True, hide_index=True)
        else:
            st.info("Não há respostas de compreensão preenchidas.")

    if col_dificuldades:
        st.subheader("🎯 Frequência das dificuldades relatadas")
        dificuldades = dividir_categorias(df_aluno[col_dificuldades])
        if not dificuldades.empty:
            df_dif = dificuldades.rename_axis("Dificuldade").reset_index(name="Ocorrências")
            exibir_grafico_barras_fino(df_dif, "Dificuldade", "Ocorrências", "Frequência das dificuldades relatadas", "grafico_dificuldades")
            st.dataframe(df_dif, use_container_width=True, hide_index=True)
            st.caption("As respostas com várias dificuldades separadas por vírgula ou ponto e vírgula são divididas em categorias para contabilização.")
        else:
            st.info("Não há dificuldades preenchidas para este aluno.")

    if col_conteudo:
        with st.expander("📚 Conteúdos trabalhados"):
            conteudos = df_aluno[col_conteudo].astype(str).str.strip()
            conteudos = conteudos[~conteudos.str.casefold().isin(["", "nan", "none", "-"])]
            for idx, conteudo in enumerate(conteudos, start=1):
                st.markdown(f"**Registro {idx}:** {conteudo}")
    st.info("O link da planilha mestre é compartilhado por todos os alunos. O filtro usa o nome completo normalizado. Os dados pedagógicos são apresentados qualitativamente, sem atribuir notas não definidas pela profissional.")


def tela_financeiro(db):
    st.title("Financeiro — lançamentos")
    alunos = db.query(Aluno).order_by(Aluno.nome).all()
    mapa = {"Sem vínculo com aluno": None}
    mapa.update({f"{a.id} — {a.nome}{'' if a.ativo else ' (inativo)'}": a.id for a in alunos})
    categorias = ["Mensalidade", "Atendimento", "Material", "Aluguel", "Serviços", "Impostos", "Transporte", "Outro"]
    status_opcoes = ["Pendente", "Pago", "Cancelado"]
    tab1, tab2 = st.tabs(["➕ Novo lançamento", "✏️ Consultar e editar lançamentos"])
    with tab1:
        with st.form("f_financeiro_novo", clear_on_submit=True):
            tipo = st.selectbox("Tipo", ["Receita", "Despesa"])
            descricao = st.text_input("Descrição *")
            categoria = st.selectbox("Categoria", categorias)
            valor = st.number_input("Valor (R$)", min_value=0.01, value=100.0, step=10.0)
            vencimento = st.date_input("Data de vencimento", value=date.today(), format="DD/MM/YYYY")
            aluno_label = st.selectbox("Aluno (opcional)", list(mapa))
            observacao = st.text_area("Observação")
            salvar = st.form_submit_button("Registrar lançamento", type="primary")
        if salvar:
            if not descricao.strip():
                st.error("Informe uma descrição.")
            else:
                try:
                    db.add(LancamentoFinanceiro(tipo=tipo, descricao=descricao.strip(), categoria=categoria,
                        valor=float(valor), data_vencimento=vencimento, aluno_id=mapa[aluno_label],
                        observacao=observacao.strip(), status="Pendente"))
                    db.commit()
                    st.success("Lançamento registrado.")
                    st.rerun()
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "cadastro do lançamento")
    with tab2:
        todos = db.query(LancamentoFinanceiro).order_by(LancamentoFinanceiro.data_vencimento.desc(), LancamentoFinanceiro.id.desc()).all()
        if not todos:
            st.info("Nenhum lançamento financeiro cadastrado.")
            return
        filtro = st.selectbox("Filtrar situação", ["Todas"] + status_opcoes, key="financeiro_filtro_status")
        filtrados = todos if filtro == "Todas" else [l for l in todos if l.status == filtro]
        st.dataframe(pd.DataFrame([{
            "ID": l.id, "Tipo": l.tipo, "Descrição": l.descricao, "Categoria": l.categoria,
            "Valor": moeda(l.valor), "Vencimento": para_str_br(l.data_vencimento),
            "Pagamento": para_str_br(l.data_pagamento), "Situação": l.status,
            "Aluno": l.aluno.nome if l.aluno else "-"
        } for l in filtrados]), use_container_width=True, hide_index=True)
        if filtrados:
            opcoes = {f"#{l.id} — {l.tipo} — {l.descricao} — {moeda(l.valor)} — {l.status}": l.id for l in filtrados}
            sel = st.selectbox("Selecione o lançamento para editar", list(opcoes), key="financeiro_editar_sel")
            lanc = db.get(LancamentoFinanceiro, opcoes[sel])
            atual_aluno = next((k for k, v in mapa.items() if v == lanc.aluno_id), "Sem vínculo com aluno")
            with st.form(f"f_editar_lancamento_{lanc.id}"):
                tipo_e = st.selectbox("Tipo", ["Receita", "Despesa"], index=["Receita", "Despesa"].index(lanc.tipo if lanc.tipo in ["Receita", "Despesa"] else "Receita"))
                descricao_e = st.text_input("Descrição", value=lanc.descricao)
                cat_atual = lanc.categoria if lanc.categoria in categorias else "Outro"
                categoria_e = st.selectbox("Categoria", categorias, index=categorias.index(cat_atual))
                valor_e = st.number_input("Valor (R$)", min_value=0.01, value=max(0.01, float(lanc.valor or 0)), step=10.0)
                venc_e = st.date_input("Data de vencimento", value=lanc.data_vencimento or date.today(), format="DD/MM/YYYY")
                aluno_e = st.selectbox("Aluno (opcional)", list(mapa), index=list(mapa).index(atual_aluno))
                obs_e = st.text_area("Observação", value=lanc.observacao or "")
                status_atual = lanc.status if lanc.status in status_opcoes else "Pendente"
                status_e = st.selectbox("Situação", status_opcoes, index=status_opcoes.index(status_atual))
                data_pag_e = st.date_input("Data de pagamento (se pago)", value=lanc.data_pagamento or date.today(), format="DD/MM/YYYY")
                salvar_e = st.form_submit_button("Salvar alterações", type="primary")
            if salvar_e:
                if not descricao_e.strip():
                    st.error("A descrição é obrigatória.")
                else:
                    lanc.tipo = tipo_e
                    lanc.descricao = descricao_e.strip()
                    lanc.categoria = categoria_e
                    lanc.valor = float(valor_e)
                    lanc.data_vencimento = venc_e
                    lanc.aluno_id = mapa[aluno_e]
                    lanc.observacao = obs_e.strip()
                    lanc.status = status_e
                    lanc.data_pagamento = data_pag_e if status_e == "Pago" else None
                    try:
                        db.commit()
                        st.success("Lançamento atualizado.")
                        st.rerun()
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "edição do lançamento financeiro")
            st.caption("Não exclua lançamentos pagos para preservar a trilha financeira. Se necessário, marque como Cancelado e registre a justificativa na observação.")
        csv = pd.DataFrame([{
            "ID": l.id, "Tipo": l.tipo, "Descrição": l.descricao, "Categoria": l.categoria,
            "Valor": l.valor, "Vencimento": para_str_br(l.data_vencimento),
            "Pagamento": para_str_br(l.data_pagamento), "Situação": l.status,
            "Aluno": l.aluno.nome if l.aluno else "", "Observação": l.observacao or ""
        } for l in todos]).to_csv(index=False).encode("utf-8-sig")
        st.download_button("Exportar financeiro (CSV)", data=csv, file_name="financeiro_espaco_dinamico.csv", mime="text/csv")

def tela_usuarios(db, perfil):
    st.title("Usuários e acessos")
    if perfil != "Admin":
        st.warning("Somente administradores podem gerenciar usuários.")
        return
    tab1, tab2 = st.tabs(["Cadastrar usuário", "Gerenciar usuários"])
    with tab1:
        with st.form("f_novo_usuario", clear_on_submit=True):
            nome = st.text_input("Nome completo *")
            cpf = st.text_input("CPF (somente números) *", max_chars=14)
            senha = st.text_input("Senha inicial *", type="password")
            perfil_novo = st.selectbox("Perfil", ["Admin", "Profissional", "Financeiro"])
            if st.form_submit_button("Cadastrar usuário", type="primary"):
                cpf_limpo = limpar_cpf(cpf)
                if not nome.strip() or len(cpf_limpo) != 11 or len(senha) < 8:
                    st.error("Informe o nome, CPF com 11 dígitos e senha com pelo menos 8 caracteres.")
                else:
                    try:
                        db.add(Usuario(nome=nome.strip(), cpf=cpf_limpo,
                            senha_hash=gerar_hash_senha(senha), perfil=perfil_novo, ativo=1))
                        db.commit()
                        st.success("Usuário cadastrado.")
                        st.rerun()
                    except IntegrityError:
                        db.rollback()
                        st.error("Já existe usuário cadastrado com esse CPF.")
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "cadastro de usuário")
    with tab2:
        usuarios = db.query(Usuario).order_by(Usuario.nome).all()
        if not usuarios:
            st.info("Nenhum usuário.")
            return
        mapa = {f"{u.id} — {u.nome} ({u.perfil})": u.id for u in usuarios}
        selecionado = st.selectbox("Usuário", list(mapa.keys()))
        usuario = db.get(Usuario, mapa[selecionado])
        with st.form("f_editar_usuario"):
            nome = st.text_input("Nome", value=usuario.nome)
            perfil_novo = st.selectbox("Perfil", ["Admin", "Profissional", "Financeiro"],
                index=["Admin", "Profissional", "Financeiro"].index(usuario.perfil if usuario.perfil in ["Admin","Profissional","Financeiro"] else "Admin"))
            ativo = st.checkbox("Usuário ativo", value=bool(usuario.ativo))
            nova_senha = st.text_input("Nova senha (deixe em branco para manter)", type="password")
            salvar = st.form_submit_button("Salvar usuário", type="primary")
        if salvar:
            if not nome.strip():
                st.error("Informe o nome.")
            elif nova_senha and len(nova_senha) < 8:
                st.error("A nova senha deve ter pelo menos 8 caracteres.")
            else:
                usuario.nome = nome.strip()
                usuario.perfil = perfil_novo
                usuario.ativo = 1 if ativo else 0
                if nova_senha:
                    usuario.senha_hash = gerar_hash_senha(nova_senha)
                db.commit()
                if usuario.id == st.session_state.get("usuario_id") and not usuario.ativo:
                    st.session_state.clear()
                st.success("Usuário atualizado.")
                st.rerun()


def tela_configuracoes(db):
    st.title("Configurações institucionais")
    with st.form("f_config_institucional"):
        nome_instituicao = st.text_input("Nome da instituição", value="Espaço Dinâmico")
        profissional = st.text_input("Profissional responsável", value="Larissa Lyrio")
        titulo = st.text_input("Título profissional", value="Neuropsicopedagoga")
        app_url = st.text_input("URL pública da aplicação (opcional)", value=os.getenv("APP_URL", ""))
        salvar = st.form_submit_button("Salvar configurações", type="primary")
    if salvar:
        valores = {
            "nome_instituicao": nome_instituicao.strip(),
            "profissional_responsavel": profissional.strip(),
            "titulo_profissional": titulo.strip(),
            "app_url": app_url.strip(),
        }
        for chave, valor in valores.items():
            item = db.query(ConfiguracaoSistema).filter_by(chave=chave).first()
            if item:
                item.valor = valor
            else:
                db.add(ConfiguracaoSistema(chave=chave, valor=valor))
        db.commit()
        st.success("Configurações salvas no banco.")
        st.rerun()
    st.caption("As configurações são armazenadas no banco de dados. A URL pública não cria, por si só, um portal autenticado.")


def main():
    criar_usuario_admin_padrao()
    logo = obter_logo()
    db = SessionLocal()
    try:
        # Portal legado: não expor dados de aluno somente pelo nome na URL.
        if st.query_params.get("aluno"):
            aplicar_estilo_global()
            st.title("Portal familiar")
            st.warning("O acesso por nome na URL foi desativado por segurança. Entre pelo sistema ou solicite a implementação de um link familiar individual protegido.")
            return

        usuario_id = st.session_state.get("usuario_id")
        usuario = db.get(Usuario, usuario_id) if usuario_id else None
        if not usuario or not usuario.ativo:
            st.session_state.pop("usuario_id", None)
            st.session_state.pop("usuario_logado", None)
            st.session_state.pop("perfil_usuario", None)
            renderizar_tela_login(db, logo)
            return

        st.session_state["usuario_logado"] = usuario.nome
        st.session_state["perfil_usuario"] = usuario.perfil
        aplicar_estilo_global()
        with st.sidebar:
            if logo:
                st.image(logo, width=145)
            st.markdown("## Espaço Dinâmico")
            st.caption("Larissa Lyrio · Neuropsicopedagoga")
            st.divider()
            pagina = st.radio("MENU PRINCIPAL", [
                "📊 Painel", "👥 Alunos e responsáveis", "📄 Contratos",
                "📂 Prontuários", "📁 Atividades", "💰 Financeiro",
                "📈 Desempenho", "👤 Usuários", "⚙️ Configurações",
            ], label_visibility="visible")
            st.divider()
            st.write(f"Conectado: **{usuario.nome}**")
            st.caption(f"Perfil: {usuario.perfil}")
            if st.button("🚪 Sair", use_container_width=True, key="sair_sistema"):
                for chave in ("usuario_id", "usuario_logado", "perfil_usuario"):
                    st.session_state.pop(chave, None)
                st.rerun()

        cabecalho(logo)
        if pagina == "📊 Painel":
            tela_painel(db)
        elif pagina == "👥 Alunos e responsáveis":
            tela_cadastros(db)
        elif pagina == "📄 Contratos":
            tela_contratos(db)
        elif pagina == "📂 Prontuários":
            tela_prontuario(db)
        elif pagina == "📁 Atividades":
            tela_atividades(db)
        elif pagina == "💰 Financeiro":
            tela_financeiro(db)
        elif pagina == "📈 Desempenho":
            tela_desempenho(db)
        elif pagina == "👤 Usuários":
            tela_usuarios(db, usuario.perfil)
        elif pagina == "⚙️ Configurações":
            tela_configuracoes(db)
    except SQLAlchemyError as exc:
        db.rollback()
        mensagem_erro(exc, "acesso ao banco de dados")
    finally:
        db.close()


if __name__ == "__main__":
    main()
