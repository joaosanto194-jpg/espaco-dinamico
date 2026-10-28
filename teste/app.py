from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import hmac
import os
import re
import secrets
import urllib.parse
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import (
    Column, Date, DateTime, Float, ForeignKey, Integer, String, Text,
    create_engine, func,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# ============================================================
# ESPAÇO DINÂMICO | Gestão Neuropsicopedagógica
# Versão de evolução: preserva os nomes das tabelas já existentes.
# ============================================================
st.set_page_config(page_title="Espaço Dinâmico | Gestão", page_icon="🧩", layout="wide", initial_sidebar_state="expanded")

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = Path(os.getenv("LOGO_PATH", str(BASE_DIR / "logo_espaco_dinamico.png")))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'espaco_dinamico.db').as_posix()}")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
Base = declarative_base()

# -------------------- MODELOS EXISTENTES --------------------
class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    cpf = Column(String(14), unique=True, nullable=False)
    senha_hash = Column(String(256), nullable=False)
    perfil = Column(String(30), default="Admin")
    ativo = Column(Integer, default=1, nullable=False)

class Responsavel(Base):
    __tablename__ = "responsaveis"
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False, unique=True)
    telefone = Column(String(30))
    email = Column(String(150))
    observacoes = Column(Text)
    ativo = Column(Integer, default=1, nullable=False)
    alunos = relationship("Aluno", back_populates="responsavel")

class Aluno(Base):
    __tablename__ = "alunos"
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    data_nascimento = Column(Date, nullable=True)
    escolaridade = Column(String(100), nullable=True)
    responsavel_id = Column(Integer, ForeignKey("responsaveis.id"), nullable=True)
    status = Column(String(20), default="Ativo", nullable=False)
    observacoes = Column(Text)
    responsavel = relationship("Responsavel", back_populates="alunos")
    prontuarios = relationship("Prontuario", back_populates="aluno")
    contratos = relationship("Contrato", back_populates="aluno")
    atividades = relationship("AtividadeAluno", back_populates="aluno")

class Prontuario(Base):
    __tablename__ = "prontuarios"
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"))
    data_registro = Column(Date, default=date.today)
    queixa_principal = Column(Text)
    hipotese_diagnostica = Column(Text)
    conduta = Column(Text)
    autor = Column(String(100))
    aluno = relationship("Aluno", back_populates="prontuarios")

class Contrato(Base):
    __tablename__ = "contratos"
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"))
    descricao_servico = Column(String(150), default="Intervenção Neuropsicopedagógica")
    valor_mensalidade = Column(Float, nullable=False)
    dia_vencimento = Column(Integer, nullable=False)
    data_inicio = Column(Date)
    status = Column(String(20), default="Ativo")
    aluno = relationship("Aluno", back_populates="contratos")

class AtividadeAluno(Base):
    __tablename__ = "atividades_alunos"
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"))
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

# -------------------- NOVAS TABELAS --------------------
class SessaoLogin(Base):
    __tablename__ = "sessoes_login"
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    expira_em = Column(DateTime, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

class LancamentoFinanceiro(Base):
    __tablename__ = "lancamentos_financeiros"
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=True)
    tipo = Column(String(20), nullable=False)  # Receita / Despesa
    descricao = Column(String(180), nullable=False)
    categoria = Column(String(80), default="Geral")
    valor = Column(Float, nullable=False)
    data_competencia = Column(Date, nullable=False, default=date.today)
    data_pagamento = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="Pendente")
    forma_pagamento = Column(String(50))
    observacoes = Column(Text)
    criado_por = Column(String(100))
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

class Auditoria(Base):
    __tablename__ = "auditoria"
    id = Column(Integer, primary_key=True)
    usuario = Column(String(100), nullable=False)
    acao = Column(String(100), nullable=False)
    entidade = Column(String(80), nullable=False)
    registro_id = Column(Integer)
    detalhe = Column(Text)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# Migrations leves e não destrutivas para colunas novas em tabelas antigas.
def ensure_column(table: str, column: str, declaration: str):
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import inspect, text
    cols = {c["name"] for c in inspect(engine).get_columns(table)}
    if column not in cols:
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {declaration}'))

for _table, _column, _decl in [
    ("usuarios", "ativo", "INTEGER DEFAULT 1"),
    ("responsaveis", "email", "VARCHAR(150)"),
    ("responsaveis", "observacoes", "TEXT"),
    ("responsaveis", "ativo", "INTEGER DEFAULT 1"),
    ("alunos", "status", "VARCHAR(20) DEFAULT 'Ativo'"),
    ("alunos", "observacoes", "TEXT"),
    ("prontuarios", "autor", "VARCHAR(100)"),
]:
    try:
        ensure_column(_table, _column, _decl)
    except Exception:
        pass

# -------------------- SEGURANÇA / UTILITÁRIOS --------------------
def limpar_cpf(cpf: str) -> str:
    return re.sub(r"\D", "", cpf or "")

def hash_senha(senha: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), 310_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"

def verificar_senha(senha: str, armazenada: str) -> bool:
    if armazenada and armazenada.startswith("pbkdf2_sha256$"):
        try:
            _, salt, digest = armazenada.split("$", 2)
            atual = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), 310_000).hex()
            return hmac.compare_digest(atual, digest)
        except ValueError:
            return False
    # Compatibilidade com senhas SHA-256 da versão anterior; migra após login válido.
    return hmac.compare_digest(hashlib.sha256(senha.encode("utf-8")).hexdigest(), armazenada or "")

def para_str_br(d):
    return d.strftime("%d/%m/%Y") if isinstance(d, (date, datetime)) else (str(d) if d else "—")

def moeda(v):
    return f"R$ {float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def auditar(db, usuario, acao, entidade, registro_id=None, detalhe=""):
    db.add(Auditoria(usuario=usuario or "Sistema", acao=acao, entidade=entidade, registro_id=registro_id, detalhe=detalhe))

def get_config(db, chave, padrao=""):
    item = db.query(ConfiguracaoSistema).filter_by(chave=chave).first()
    return item.valor if item and item.valor is not None else padrao

def set_config(db, chave, valor):
    item = db.query(ConfiguracaoSistema).filter_by(chave=chave).first()
    if item:
        item.valor = valor
    else:
        db.add(ConfiguracaoSistema(chave=chave, valor=valor))

def garantir_admin(db):
    if db.query(Usuario).count() == 0:
        cpf = limpar_cpf(os.getenv("ADMIN_CPF", "00000000000"))
        senha = os.getenv("ADMIN_PASSWORD", "admin123")
        db.add(Usuario(nome="Administrador Espaço Dinâmico", cpf=cpf, senha_hash=hash_senha(senha), perfil="Admin", ativo=1))
        db.commit()
        return True
    return False

def aluno_label(a):
    return f"{a.id} · {a.nome}"

def lista_alunos(db, ativos_only=False):
    q = db.query(Aluno).order_by(Aluno.nome)
    if ativos_only:
        q = q.filter(Aluno.status == "Ativo")
    return q.all()

# -------------------- DESIGN SYSTEM --------------------
def aplicar_estilo():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    :root { --navy:#17324D; --blue:#2878B5; --teal:#2BAE9A; --ink:#243447; --muted:#718096; --line:#E5EAF0; }
    .stApp { background:linear-gradient(180deg,#F5F8FC 0%,#F8FAFC 100%); color:var(--ink); font-family:'Inter',sans-serif; }
    [data-testid="stSidebar"] { background:#12283F; border-right:1px solid #203B55; }
    [data-testid="stSidebar"] * { color:#F2F7FB !important; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label { padding:7px 10px; border-radius:9px; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background:#203B55; }
    h1,h2,h3 { color:var(--navy); letter-spacing:-.025em; }
    .brand-kicker { color:#718096; text-transform:uppercase; font-size:.72rem; letter-spacing:.12em; font-weight:800; }
    .hero { padding:22px 24px; background:linear-gradient(120deg,#17324D,#245B7A); color:white; border-radius:18px; margin:4px 0 20px; box-shadow:0 12px 28px rgba(23,50,77,.13); }
    .hero h1 { color:white; margin:0; font-size:1.7rem; }
    .hero p { color:#D9E8F3; margin:.4rem 0 0; }
    div[data-testid="stMetric"] { background:white; border:1px solid var(--line); padding:17px 19px; border-radius:15px; box-shadow:0 5px 18px rgba(25,50,75,.045); }
    div[data-testid="stMetricLabel"] { color:#718096; }
    div[data-testid="stMetricValue"] { color:var(--navy); font-weight:800; }
    .block-container { padding-top:1.5rem; padding-bottom:3rem; max-width:1500px; }
    .stButton>button, .stDownloadButton>button { border-radius:9px; min-height:2.55rem; font-weight:650; border:1px solid #D7E0E9; }
    .stButton>button[kind="primary"] { background:#2878B5; border-color:#2878B5; }
    div[data-testid="stForm"] { background:white; border:1px solid var(--line); border-radius:14px; padding:18px; }
    div[data-testid="stTabs"] button { font-weight:650; }
    .small-muted { color:#718096; font-size:.88rem; }
    footer {visibility:hidden;}
    </style>
    """, unsafe_allow_html=True)

def header(db, usuario):
    c1, c2 = st.columns([1, 5])
    with c1:
        if LOGO_PATH.exists(): st.image(str(LOGO_PATH), width=112)
        else: st.markdown("## 🧩 Espaço Dinâmico")
    with c2:
        st.markdown('<div class="brand-kicker">Gestão neuropsicopedagógica</div>', unsafe_allow_html=True)
        st.markdown("## Espaço Dinâmico")
        st.caption(f"Profissional: {get_config(db, 'profissional_nome', 'Larissa Lyrio')} · {get_config(db, 'profissional_titulo', 'Neuropsicopedagoga')}")
    st.divider()

# -------------------- AUTENTICAÇÃO COM COOKIE --------------------
def cookie_manager():
    try:
        import extra_streamlit_components as stx
        return stx.CookieManager(key="ed_cookie_manager")
    except Exception:
        return None

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def usuario_da_sessao(db, cookies):
    token = None
    if cookies:
        try: token = cookies.get("ed_session")
        except Exception: token = None
    if not token: token = st.session_state.get("ed_session_token")
    if not token: return None
    sess = db.query(SessaoLogin).filter_by(token_hash=token_hash(token)).first()
    if not sess or sess.expira_em < datetime.utcnow():
        if sess:
            db.delete(sess); db.commit()
        return None
    user = db.query(Usuario).filter_by(id=sess.usuario_id, ativo=1).first()
    if not user:
        db.delete(sess); db.commit(); return None
    return user

def criar_sessao(db, user, cookies):
    token = secrets.token_urlsafe(40)
    duracao = int(os.getenv("SESSION_DAYS", "7"))
    db.add(SessaoLogin(usuario_id=user.id, token_hash=token_hash(token), expira_em=datetime.utcnow()+timedelta(days=duracao)))
    # Remove sessões expiradas.
    db.query(SessaoLogin).filter(SessaoLogin.expira_em < datetime.utcnow()).delete(synchronize_session=False)
    db.commit()
    st.session_state["ed_session_token"] = token
    if cookies:
        try: cookies.set("ed_session", token, expires_at=datetime.now()+timedelta(days=duracao), key="ed_set_cookie")
        except Exception: pass

def encerrar_sessao(db, cookies):
    token = st.session_state.pop("ed_session_token", None)
    if cookies:
        try: token = cookies.get("ed_session") or token
        except Exception: pass
    if token:
        db.query(SessaoLogin).filter_by(token_hash=token_hash(token)).delete(synchronize_session=False)
        db.commit()
    if cookies:
        try: cookies.delete("ed_session", key="ed_delete_cookie")
        except Exception: pass
    st.rerun()

def tela_login(db, cookies):
    st.markdown("<div style='height:5vh'></div>", unsafe_allow_html=True)
    left, center, right = st.columns([1, 1.1, 1])
    with center:
        with st.container(border=True):
            if LOGO_PATH.exists(): st.image(str(LOGO_PATH), width=150)
            st.markdown("# Espaço Dinâmico")
            st.markdown("**Gestão Neuropsicopedagógica**")
            st.caption("Acesso seguro à plataforma institucional")
            st.divider()
            with st.form("login_form", clear_on_submit=False):
                cpf = st.text_input("CPF", placeholder="Digite somente os números", max_chars=14)
                senha = st.text_input("Senha", type="password")
                entrar = st.form_submit_button("Entrar na plataforma", type="primary", use_container_width=True)
            if entrar:
                user = db.query(Usuario).filter_by(cpf=limpar_cpf(cpf), ativo=1).first()
                if user and verificar_senha(senha, user.senha_hash):
                    if not user.senha_hash.startswith("pbkdf2_sha256$"):
                        user.senha_hash = hash_senha(senha)
                    criar_sessao(db, user, cookies)
                    auditar(db, user.nome, "Login", "Usuario", user.id)
                    db.commit(); st.rerun()
                st.error("CPF ou senha inválidos, ou usuário inativo.")
            st.caption("A sessão é mantida por cookie protegido até expirar ou você sair.")

def somente_admin(user):
    return (user.perfil or "").lower() in ("admin", "administrador")

def guardar(db, user, mensagem, acao, entidade, registro_id=None, detalhe=""):
    auditar(db, user.nome, acao, entidade, registro_id, detalhe)
    db.commit()
    st.success(mensagem)
    st.rerun()

# -------------------- PÁGINAS --------------------
def pagina_painel(db):
    st.markdown('<div class="hero"><h1>Olá! Bem-vinda ao Espaço Dinâmico 👋</h1><p>Uma visão clara da operação, dos atendimentos e da saúde financeira.</p></div>', unsafe_allow_html=True)
    hoje = date.today(); primeiro = hoje.replace(day=1)
    alunos = db.query(Aluno).filter_by(status="Ativo").count()
    responsaveis = db.query(Responsavel).filter_by(ativo=1).count()
    contratos = db.query(Contrato).filter_by(status="Ativo").count()
    prontuarios_mes = db.query(Prontuario).filter(Prontuario.data_registro >= primeiro).count()
    receitas_pendentes = db.query(func.sum(LancamentoFinanceiro.valor)).filter_by(tipo="Receita", status="Pendente").scalar() or 0
    recebidas_mes = db.query(func.sum(LancamentoFinanceiro.valor)).filter(LancamentoFinanceiro.tipo=="Receita", LancamentoFinanceiro.status=="Pago", LancamentoFinanceiro.data_pagamento>=primeiro).scalar() or 0
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Alunos ativos", alunos, help="Alunos com status ativo")
    c2.metric("Responsáveis ativos", responsaveis)
    c3.metric("Contratos ativos", contratos)
    c4.metric("Prontuários no mês", prontuarios_mes)
    c5,c6 = st.columns(2)
    c5.metric("Recebido no mês", moeda(recebidas_mes))
    c6.metric("Receitas pendentes", moeda(receitas_pendentes))
    st.subheader("Atividade recente")
    logs = db.query(Auditoria).order_by(Auditoria.criado_em.desc()).limit(8).all()
    if logs:
        st.dataframe(pd.DataFrame([{"Data/hora":x.criado_em.strftime("%d/%m/%Y %H:%M") if x.criado_em else "—", "Usuário":x.usuario, "Ação":x.acao, "Módulo":x.entidade, "Detalhe":x.detalhe or ""} for x in logs]), use_container_width=True, hide_index=True)
    else: st.info("As operações importantes aparecerão aqui conforme o uso do sistema.")

def pagina_cadastros(db, user):
    st.title("👥 Alunos e responsáveis")
    t1,t2,t3 = st.tabs(["Cadastrar", "Consultar / editar", "Responsáveis"])
    with t1:
        with st.form("novo_aluno", clear_on_submit=True):
            st.subheader("Novo aluno")
            nome=st.text_input("Nome completo *")
            c1,c2=st.columns(2)
            nasc=c1.date_input("Data de nascimento", value=None, min_value=date(1900,1,1), max_value=date.today())
            escolaridade=c2.text_input("Escolaridade")
            responsaveis=db.query(Responsavel).filter_by(ativo=1).order_by(Responsavel.nome).all()
            opcoes={"Sem responsável vinculado":None, **{f"{r.id} · {r.nome}":r.id for r in responsaveis}}
            resp=st.selectbox("Responsável", list(opcoes.keys()))
            obs=st.text_area("Observações administrativas (não clínicas)")
            if st.form_submit_button("Salvar aluno", type="primary"):
                if not nome.strip(): st.error("Informe o nome do aluno.")
                else:
                    a=Aluno(nome=nome.strip(), data_nascimento=nasc, escolaridade=escolaridade.strip(), responsavel_id=opcoes[resp], observacoes=obs, status="Ativo")
                    db.add(a); db.flush(); guardar(db,user,"Aluno cadastrado.","Cadastro","Aluno",a.id,a.nome)
    with t2:
        alunos=db.query(Aluno).order_by(Aluno.nome).all()
        busca=st.text_input("Pesquisar aluno", key="busca_aluno")
        alunos=[a for a in alunos if busca.lower() in a.nome.lower()] if busca else alunos
        if alunos:
            op={aluno_label(a):a.id for a in alunos}; selecionado=st.selectbox("Selecione o aluno",list(op.keys()),key="ed_aluno_sel")
            a=db.get(Aluno,op[selecionado])
            with st.form("editar_aluno"):
                nome=st.text_input("Nome",value=a.nome)
                c1,c2=st.columns(2)
                nasc=c1.date_input("Nascimento",value=a.data_nascimento or date(2015,1,1),min_value=date(1900,1,1),max_value=date.today())
                esc=c2.text_input("Escolaridade",value=a.escolaridade or "")
                resps=db.query(Responsavel).filter_by(ativo=1).order_by(Responsavel.nome).all()
                opresp={"Sem responsável":None,**{f"{r.id} · {r.nome}":r.id for r in resps}}
                chave_resp=next((k for k,v in opresp.items() if v==a.responsavel_id),"Sem responsável")
                resp=st.selectbox("Responsável",list(opresp.keys()),index=list(opresp.keys()).index(chave_resp))
                status=st.selectbox("Situação",["Ativo","Inativo"],index=0 if a.status=="Ativo" else 1)
                obs=st.text_area("Observações administrativas",value=a.observacoes or "")
                if st.form_submit_button("Salvar alterações",type="primary"):
                    if not nome.strip(): st.error("Nome é obrigatório.")
                    else:
                        a.nome=nome.strip(); a.data_nascimento=nasc; a.escolaridade=esc.strip(); a.responsavel_id=opresp[resp]; a.status=status; a.observacoes=obs
                        guardar(db,user,"Cadastro atualizado.","Edição","Aluno",a.id,a.nome)
            st.caption("Por segurança, o cadastro é inativado em vez de apagar o histórico associado.")
        else: st.info("Nenhum aluno encontrado.")
    with t3:
        with st.form("novo_resp",clear_on_submit=True):
            st.subheader("Cadastrar responsável")
            n=st.text_input("Nome completo *"); tel=st.text_input("Telefone / WhatsApp"); email=st.text_input("E-mail"); obs=st.text_area("Observações")
            if st.form_submit_button("Salvar responsável",type="primary"):
                if not n.strip(): st.error("Nome obrigatório.")
                elif db.query(Responsavel).filter(func.lower(Responsavel.nome)==n.strip().lower()).first(): st.error("Já existe um responsável com esse nome.")
                else:
                    r=Responsavel(nome=n.strip(),telefone=tel.strip(),email=email.strip(),observacoes=obs,ativo=1); db.add(r); db.flush(); guardar(db,user,"Responsável cadastrado.","Cadastro","Responsável",r.id,r.nome)
        resps=db.query(Responsavel).order_by(Responsavel.nome).all()
        if resps:
            st.subheader("Base de responsáveis")
            st.dataframe(pd.DataFrame([{"ID":r.id,"Nome":r.nome,"Telefone":r.telefone or "—","E-mail":r.email or "—","Situação":"Ativo" if r.ativo else "Inativo","Alunos vinculados":", ".join(a.nome for a in r.alunos) or "—"} for r in resps]),use_container_width=True,hide_index=True)
            with st.form("editar_resp"):
                rr=st.selectbox("Editar responsável",resps,format_func=lambda r:f"{r.id} · {r.nome}")
                tel2=st.text_input("Telefone",value=rr.telefone or ""); email2=st.text_input("E-mail",value=rr.email or ""); ativo=st.selectbox("Situação",["Ativo","Inativo"],index=0 if rr.ativo else 1)
                if st.form_submit_button("Atualizar responsável"):
                    rr.telefone=tel2; rr.email=email2; rr.ativo=1 if ativo=="Ativo" else 0; guardar(db,user,"Responsável atualizado.","Edição","Responsável",rr.id,rr.nome)

def pagina_contratos(db,user):
    st.title("📄 Contratos e mensalidades")
    alunos=lista_alunos(db,True)
    if not alunos: st.info("Cadastre um aluno ativo antes de criar um contrato."); return
    with st.expander("＋ Criar contrato",expanded=True):
        with st.form("novo_contrato"):
            a=st.selectbox("Aluno",alunos,format_func=aluno_label)
            serv=st.text_input("Serviço",value="Intervenção Neuropsicopedagógica")
            c1,c2,c3=st.columns(3); valor=c1.number_input("Mensalidade (R$)",min_value=0.0,value=350.0,step=25.0); venc=c2.number_input("Dia de vencimento",1,31,10); inicio=c3.date_input("Início",value=date.today())
            if st.form_submit_button("Registrar contrato",type="primary"):
                if valor<=0: st.error("Informe um valor maior que zero.")
                else:
                    x=Contrato(aluno_id=a.id,descricao_servico=serv.strip(),valor_mensalidade=valor,dia_vencimento=int(venc),data_inicio=inicio,status="Ativo"); db.add(x); db.flush(); guardar(db,user,"Contrato registrado.","Cadastro","Contrato",x.id,a.nome)
    contratos=db.query(Contrato).order_by(Contrato.id.desc()).all()
    if contratos:
        st.subheader("Contratos cadastrados")
        st.dataframe(pd.DataFrame([{"ID":c.id,"Aluno":c.aluno.nome if c.aluno else "—","Serviço":c.descricao_servico,"Mensalidade":moeda(c.valor_mensalidade),"Vencimento":c.dia_vencimento,"Início":para_str_br(c.data_inicio),"Status":c.status} for c in contratos]),use_container_width=True,hide_index=True)
        with st.form("editar_contrato"):
            c=st.selectbox("Contrato para gerenciar",contratos,format_func=lambda x:f"#{x.id} · {x.aluno.nome if x.aluno else 'Aluno removido'} · {moeda(x.valor_mensalidade)}")
            serv2=st.text_input("Descrição",value=c.descricao_servico or ""); val2=st.number_input("Valor (R$)",min_value=0.0,value=float(c.valor_mensalidade),step=25.0); venc2=st.number_input("Dia de vencimento",1,31,int(c.dia_vencimento)); status=st.selectbox("Situação",["Ativo","Suspenso","Cancelado"],index=["Ativo","Suspenso","Cancelado"].index(c.status if c.status in ["Ativo","Suspenso","Cancelado"] else "Ativo"))
            if st.form_submit_button("Salvar contrato"):
                c.descricao_servico=serv2; c.valor_mensalidade=val2; c.dia_vencimento=int(venc2); c.status=status; guardar(db,user,"Contrato atualizado.","Edição","Contrato",c.id,status)

def pagina_prontuarios(db,user):
    st.title("📂 Prontuários e evolução")
    st.warning("Área confidencial. Registre somente informações necessárias ao acompanhamento profissional. O acesso deve ser restrito por perfil.")
    alunos=lista_alunos(db,True)
    if not alunos: st.info("Cadastre um aluno ativo primeiro."); return
    aluno=st.selectbox("Aluno",alunos,format_func=aluno_label,key="pront_aluno")
    with st.form("novo_prontuario"):
        data_reg=st.date_input("Data do registro",value=date.today()); queixa=st.text_area("Queixa principal / observações relevantes"); hipotese=st.text_area("Hipótese / avaliação profissional"); conduta=st.text_area("Conduta / plano de intervenção")
        if st.form_submit_button("Salvar evolução",type="primary"):
            p=Prontuario(aluno_id=aluno.id,data_registro=data_reg,queixa_principal=queixa,hipotese_diagnostica=hipotese,conduta=conduta,autor=user.nome); db.add(p); db.flush(); guardar(db,user,"Evolução registrada.","Cadastro","Prontuário",p.id,aluno.nome)
    st.subheader("Histórico do aluno")
    registros=db.query(Prontuario).filter_by(aluno_id=aluno.id).order_by(Prontuario.data_registro.desc(),Prontuario.id.desc()).all()
    if registros:
        for p in registros:
            with st.expander(f"{para_str_br(p.data_registro)} · Registro #{p.id} · {p.autor or 'Profissional'}"):
                st.markdown("**Queixa / observações**"); st.write(p.queixa_principal or "—")
                st.markdown("**Hipótese / avaliação**"); st.write(p.hipotese_diagnostica or "—")
                st.markdown("**Conduta / plano**"); st.write(p.conduta or "—")
                st.caption("Registros são preservados no histórico. Correções devem ser rastreáveis.")
    else: st.info("Ainda não há registros para este aluno.")

def pagina_atividades(db,user):
    st.title("📁 Atividades e intervenções")
    alunos=lista_alunos(db,True)
    if not alunos: st.info("Cadastre um aluno ativo primeiro."); return
    with st.form("nova_atividade"):
        aluno=st.selectbox("Aluno",alunos,format_func=aluno_label); c1,c2=st.columns(2); data_at=c1.date_input("Data",value=date.today()); cat=c2.selectbox("Categoria",["Intervenção","Avaliação","Orientação familiar","Reunião","Outro"]); titulo=st.text_input("Título *"); desc=st.text_area("Descrição / objetivo"); status=st.selectbox("Situação",["Planejada","Em andamento","Realizada","Cancelada"])
        if st.form_submit_button("Salvar atividade",type="primary"):
            if not titulo.strip(): st.error("Informe o título.")
            else:
                x=AtividadeAluno(aluno_id=aluno.id,categoria=cat,data_atividade=data_at,titulo=titulo.strip(),descricao=desc,status=status); db.add(x); db.flush(); guardar(db,user,"Atividade registrada.","Cadastro","Atividade",x.id,titulo)
    st.subheader("Atividades registradas")
    itens=db.query(AtividadeAluno).order_by(AtividadeAluno.data_atividade.desc()).all()
    if itens:
        df=pd.DataFrame([{"ID":x.id,"Data":para_str_br(x.data_atividade),"Aluno":x.aluno.nome if x.aluno else "—","Categoria":x.categoria,"Título":x.titulo,"Situação":x.status,"Descrição":x.descricao or ""} for x in itens])
        filtro=st.multiselect("Filtrar situação",sorted(df["Situação"].dropna().unique()),default=[])
        if filtro: df=df[df["Situação"].isin(filtro)]
        st.dataframe(df,use_container_width=True,hide_index=True)
        with st.form("editar_atividade"):
            x=st.selectbox("Editar atividade",itens,format_func=lambda x:f"#{x.id} · {para_str_br(x.data_atividade)} · {x.titulo}")
            titulo2=st.text_input("Título",value=x.titulo); desc2=st.text_area("Descrição",value=x.descricao or ""); status2=st.selectbox("Situação",["Planejada","Em andamento","Realizada","Cancelada"],index=["Planejada","Em andamento","Realizada","Cancelada"].index(x.status if x.status in ["Planejada","Em andamento","Realizada","Cancelada"] else "Realizada"))
            if st.form_submit_button("Atualizar atividade"):
                x.titulo=titulo2.strip(); x.descricao=desc2; x.status=status2; guardar(db,user,"Atividade atualizada.","Edição","Atividade",x.id,x.titulo)

def pagina_financeiro(db,user):
    st.title("💰 Financeiro")
    st.caption("Controle operacional de receitas, despesas e recebimentos. Não substitui a escrituração contábil.")
    with st.expander("＋ Novo lançamento",expanded=True):
        with st.form("novo_lancamento",clear_on_submit=True):
            c1,c2=st.columns(2); tipo=c1.selectbox("Tipo",["Receita","Despesa"]); desc=c2.text_input("Descrição *")
            c1,c2,c3=st.columns(3); valor=c1.number_input("Valor (R$)",min_value=0.01,value=100.0,step=10.0); competencia=c2.date_input("Data de competência",value=date.today()); categoria=c3.selectbox("Categoria",["Mensalidade","Avaliação","Atendimento avulso","Aluguel","Materiais","Pessoal","Serviços","Impostos","Geral"])
            alunos=lista_alunos(db); aluno_opts={"Não vinculado":None,**{aluno_label(a):a.id for a in alunos}}; aluno_sel=st.selectbox("Aluno (opcional)",list(aluno_opts.keys()))
            status=st.selectbox("Situação",["Pendente","Pago"]); forma=st.selectbox("Forma de pagamento",["Não informado","Pix","Dinheiro","Cartão","Transferência","Boleto","Outro"]); data_pag=st.date_input("Data do pagamento (se pago)",value=date.today()) if status=="Pago" else None; obs=st.text_area("Observações")
            if st.form_submit_button("Salvar lançamento",type="primary"):
                if not desc.strip(): st.error("Descrição obrigatória.")
                else:
                    x=LancamentoFinanceiro(aluno_id=aluno_opts[aluno_sel],tipo=tipo,descricao=desc.strip(),categoria=categoria,valor=float(valor),data_competencia=competencia,data_pagamento=data_pag,status=status,forma_pagamento=None if forma=="Não informado" else forma,observacoes=obs,criado_por=user.nome); db.add(x); db.flush(); guardar(db,user,"Lançamento salvo.","Cadastro","Financeiro",x.id,desc)
    lanc=db.query(LancamentoFinanceiro).order_by(LancamentoFinanceiro.data_competencia.desc(),LancamentoFinanceiro.id.desc()).all()
    receitas=sum(x.valor for x in lanc if x.tipo=="Receita" and x.status=="Pago")
    despesas=sum(x.valor for x in lanc if x.tipo=="Despesa" and x.status=="Pago")
    pend=sum(x.valor for x in lanc if x.tipo=="Receita" and x.status=="Pendente")
    a,b,c=st.columns(3); a.metric("Receitas recebidas",moeda(receitas)); b.metric("Despesas pagas",moeda(despesas)); c.metric("A receber",moeda(pend))
    st.subheader("Movimentações")
    if lanc:
        df=pd.DataFrame([{"ID":x.id,"Competência":para_str_br(x.data_competencia),"Pagamento":para_str_br(x.data_pagamento),"Tipo":x.tipo,"Descrição":x.descricao,"Categoria":x.categoria,"Aluno":x.aluno.nome if x.aluno else "—","Valor":moeda(x.valor),"Situação":x.status,"Forma":x.forma_pagamento or "—"} for x in lanc])
        tipos=st.multiselect("Filtrar tipo",["Receita","Despesa"],default=["Receita","Despesa"]); situacoes=st.multiselect("Filtrar situação",["Pendente","Pago"],default=["Pendente","Pago"])
        df=df[df["Tipo"].isin(tipos)&df["Situação"].isin(situacoes)]
        st.dataframe(df,use_container_width=True,hide_index=True)
        csv=df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Exportar CSV",csv,"financeiro_espaco_dinamico.csv","text/csv")
        with st.form("editar_lancamento"):
            x=st.selectbox("Atualizar lançamento",lanc,format_func=lambda x:f"#{x.id} · {x.tipo} · {x.descricao} · {moeda(x.valor)}")
            novo_status=st.selectbox("Nova situação",["Pendente","Pago"],index=0 if x.status=="Pendente" else 1); data_nova=st.date_input("Data de pagamento",value=x.data_pagamento or date.today()) if novo_status=="Pago" else None
            if st.form_submit_button("Atualizar situação"):
                x.status=novo_status; x.data_pagamento=data_nova; guardar(db,user,"Situação financeira atualizada.","Edição","Financeiro",x.id,x.descricao)
    else: st.info("Nenhum lançamento financeiro cadastrado.")

def pagina_desempenho(db):
    st.title("📈 Desempenho e Planilha Mestre")
    link=get_config(db,"link_planilha_mestre","")
    with st.form("config_planilha"):
        st.write("Conecte a planilha mestre publicada com permissão de leitura adequada.")
        novo=st.text_input("Link Google Sheets",value=link,placeholder="https://docs.google.com/spreadsheets/d/...")
        if st.form_submit_button("Salvar link",type="primary"):
            set_config(db,"link_planilha_mestre",novo.strip()); db.commit(); st.cache_data.clear(); st.success("Link salvo."); st.rerun()
    if not link: st.info("Configure o link da planilha para consultar os indicadores."); return
    if st.button("Atualizar dados da planilha"): st.cache_data.clear()
    try:
        sid=link.split("/d/")[1].split("/")[0]; sheet=urllib.parse.quote("OBSERVAÇÃO DO ATENDIMENTO")
        url=f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq?tqx=out:csv&sheet={sheet}"
        df=pd.read_csv(url)
        st.success(f"Planilha carregada: {len(df)} registros.")
        st.dataframe(df,use_container_width=True,hide_index=True)
        nomes=[c for c in df.columns if "nome" in c.lower()]
        if nomes:
            termo=st.selectbox("Filtrar aluno",sorted(df[nomes[0]].dropna().astype(str).unique()))
            df_a=df[df[nomes[0]].astype(str).str.strip().str.lower()==termo.strip().lower()]
            st.dataframe(df_a,use_container_width=True,hide_index=True)
            cols=list(df.columns[5:13])
            if not df_a.empty and cols:
                graf=df_a[cols].apply(pd.to_numeric,errors="coerce").dropna(axis=1,how="all")
                if not graf.empty: st.bar_chart(graf.T)
    except Exception as e: st.error("Não foi possível ler a planilha. Verifique se ela está acessível para leitura e se o nome da aba está correto."); st.caption(str(e))

def pagina_usuarios(db,user):
    st.title("🔐 Usuários e permissões")
    if not somente_admin(user): st.error("Somente administradores podem gerenciar usuários."); return
    with st.form("criar_usuario",clear_on_submit=True):
        nome=st.text_input("Nome completo *"); cpf=st.text_input("CPF (somente números) *",max_chars=14); senha=st.text_input("Senha inicial *",type="password"); perfil=st.selectbox("Perfil",["Profissional","Financeiro","Admin"])
        if st.form_submit_button("Cadastrar usuário",type="primary"):
            cpf_limpo=limpar_cpf(cpf)
            if not nome.strip() or len(cpf_limpo)!=11 or len(senha)<10: st.error("Informe nome, CPF com 11 dígitos e senha com pelo menos 10 caracteres.")
            elif db.query(Usuario).filter_by(cpf=cpf_limpo).first(): st.error("Já existe usuário com esse CPF.")
            else:
                x=Usuario(nome=nome.strip(),cpf=cpf_limpo,senha_hash=hash_senha(senha),perfil=perfil,ativo=1); db.add(x); db.flush(); guardar(db,user,"Usuário cadastrado.","Cadastro","Usuário",x.id,x.nome)
    users=db.query(Usuario).order_by(Usuario.nome).all()
    st.dataframe(pd.DataFrame([{"ID":x.id,"Nome":x.nome,"CPF":"••••••"+x.cpf[-4:],"Perfil":x.perfil,"Situação":"Ativo" if x.ativo else "Bloqueado"} for x in users]),use_container_width=True,hide_index=True)
    with st.form("gerenciar_usuario"):
        x=st.selectbox("Usuário para gerenciar",users,format_func=lambda x:f"{x.nome} · {x.perfil}")
        nome2=st.text_input("Nome",value=x.nome); perfil2=st.selectbox("Perfil",["Profissional","Financeiro","Admin"],index=["Profissional","Financeiro","Admin"].index(x.perfil if x.perfil in ["Profissional","Financeiro","Admin"] else "Admin")); ativo=st.selectbox("Acesso",["Ativo","Bloqueado"],index=0 if x.ativo else 1); senha2=st.text_input("Nova senha (opcional; mínimo 10 caracteres)",type="password")
        if st.form_submit_button("Salvar usuário"):
            if x.id==user.id and ativo=="Bloqueado": st.error("Não é permitido bloquear a própria conta nesta tela.")
            elif senha2 and len(senha2)<10: st.error("A nova senha precisa ter pelo menos 10 caracteres.")
            else:
                x.nome=nome2.strip(); x.perfil=perfil2; x.ativo=1 if ativo=="Ativo" else 0
                if senha2: x.senha_hash=hash_senha(senha2); db.query(SessaoLogin).filter_by(usuario_id=x.id).delete(synchronize_session=False)
                guardar(db,user,"Usuário atualizado.","Edição","Usuário",x.id,x.nome)

def pagina_configuracoes(db,user):
    st.title("⚙️ Configurações institucionais")
    with st.form("config_institucional"):
        nome=st.text_input("Nome da instituição",value=get_config(db,"instituicao_nome","Espaço Dinâmico"))
        prof=st.text_input("Profissional",value=get_config(db,"profissional_nome","Larissa Lyrio"))
        titulo=st.text_input("Título profissional",value=get_config(db,"profissional_titulo","Neuropsicopedagoga"))
        contato=st.text_input("Telefone institucional",value=get_config(db,"telefone_institucional",""))
        email=st.text_input("E-mail institucional",value=get_config(db,"email_institucional",""))
        if st.form_submit_button("Salvar configurações",type="primary"):
            set_config(db,"instituicao_nome",nome.strip()); set_config(db,"profissional_nome",prof.strip()); set_config(db,"profissional_titulo",titulo.strip()); set_config(db,"telefone_institucional",contato.strip()); set_config(db,"email_institucional",email.strip()); guardar(db,user,"Configurações salvas.","Edição","Configurações")
    st.subheader("Banco de dados")
    st.info("O aplicativo grava os registros no banco configurado. Em produção, mantenha o banco em armazenamento persistente e faça backups testados antes de atualizar a aplicação.")
    st.code("DATABASE_URL=" + ("configurado por variável de ambiente" if os.getenv("DATABASE_URL") else "SQLite local: espaco_dinamico.db"))

def pagina_auditoria(db,user):
    st.title("🛡️ Auditoria do sistema")
    if not somente_admin(user): st.error("Acesso restrito a administradores."); return
    logs=db.query(Auditoria).order_by(Auditoria.criado_em.desc()).limit(500).all()
    if logs: st.dataframe(pd.DataFrame([{"Data/hora":x.criado_em.strftime("%d/%m/%Y %H:%M:%S") if x.criado_em else "—","Usuário":x.usuario,"Ação":x.acao,"Entidade":x.entidade,"Registro":x.registro_id,"Detalhe":x.detalhe or ""} for x in logs]),use_container_width=True,hide_index=True)
    else: st.info("Nenhuma operação registrada ainda.")

# -------------------- EXECUÇÃO --------------------
def main():
    aplicar_estilo()
    db=SessionLocal()
    cookies=cookie_manager()
    try:
        created=garantir_admin(db)
        if created:
            st.warning("Primeiro acesso: configure ADMIN_CPF e ADMIN_PASSWORD no ambiente antes de publicar. Para teste local, o acesso inicial padrão é CPF 00000000000 e senha admin123. Troque a senha imediatamente em Usuários.")
        # Link do portal: token público ainda não habilitado nesta versão, por segurança.
        if st.query_params.get("aluno"):
            st.title("🔒 Portal da família")
            st.warning("O acesso por nome na URL foi desativado por segurança. O portal deve usar convite individual com token revogável antes de ser publicado.")
            st.stop()
        user=usuario_da_sessao(db,cookies)
        if not user:
            tela_login(db,cookies)
            return
        # Perfil autenticado
        with st.sidebar:
            if LOGO_PATH.exists(): st.image(str(LOGO_PATH),width=130)
            st.markdown("### Espaço Dinâmico")
            st.caption(f"Conectado como **{user.nome}**")
            st.caption(f"Perfil: {user.perfil}")
            st.divider()
            menu=["📊 Painel","👥 Alunos e responsáveis","📄 Contratos","📂 Prontuários","📁 Atividades","💰 Financeiro","📈 Desempenho","⚙️ Configurações"]
            if somente_admin(user): menu += ["🔐 Usuários","🛡️ Auditoria"]
            pagina=st.radio("NAVEGAÇÃO",menu,label_visibility="visible")
            st.divider()
            st.caption("Espaço Dinâmico · Gestão integrada")
            if st.button("Sair da conta",use_container_width=True): encerrar_sessao(db,cookies)
        header(db,user)
        if pagina=="📊 Painel": pagina_painel(db)
        elif pagina=="👥 Alunos e responsáveis": pagina_cadastros(db,user)
        elif pagina=="📄 Contratos": pagina_contratos(db,user)
        elif pagina=="📂 Prontuários":
            if user.perfil in ("Financeiro",): st.error("Seu perfil não possui acesso a prontuários.")
            else: pagina_prontuarios(db,user)
        elif pagina=="📁 Atividades": pagina_atividades(db,user)
        elif pagina=="💰 Financeiro":
            if user.perfil=="Profissional": st.error("Seu perfil não possui acesso ao módulo financeiro.")
            else: pagina_financeiro(db,user)
        elif pagina=="📈 Desempenho": pagina_desempenho(db)
        elif pagina=="⚙️ Configurações": pagina_configuracoes(db,user)
        elif pagina=="🔐 Usuários": pagina_usuarios(db,user)
        elif pagina=="🛡️ Auditoria": pagina_auditoria(db,user)
        st.markdown("<br><div class='small-muted'>Espaço Dinâmico · Larissa Lyrio · Neuropsicopedagoga</div>",unsafe_allow_html=True)
    finally:
        db.close()

if __name__ == "__main__":
    main()
