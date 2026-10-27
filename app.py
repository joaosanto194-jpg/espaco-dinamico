import base64
from datetime import date, datetime
import hashlib
import os
import re
import urllib.parse
import pandas as pd
import streamlit as st
from sqlalchemy import (
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# --- CONFIGURAÇÃO DE AMBIENTE E BANCO DE DADOS ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///espaco_dinamico.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
Base = declarative_base()


# --- MODELOS DO BANCO DE DADOS ---
class Usuario(Base):
  __tablename__ = "usuarios"
  id = Column(Integer, primary_key=True)
  nome = Column(String(100), nullable=False)
  cpf = Column(String(14), unique=True, nullable=False)
  senha_hash = Column(String(128), nullable=False)
  perfil = Column(String(20), default="Admin")


class Responsavel(Base):
  __tablename__ = "responsaveis"
  id = Column(Integer, primary_key=True)
  nome = Column(String(100), nullable=False, unique=True)
  telefone = Column(String(20))
  alunos = relationship(
      "Aluno", back_populates="responsavel", cascade="all, delete-orphan"
  )


class Aluno(Base):
  __tablename__ = "alunos"
  id = Column(Integer, primary_key=True)
  nome = Column(String(100), nullable=False)
  data_nascimento = Column(Date, nullable=True)
  escolaridade = Column(String(100), nullable=True)
  responsavel_id = Column(Integer, ForeignKey("responsaveis.id"), nullable=True)

  responsavel = relationship("Responsavel", back_populates="alunos")
  avaliacoes = relationship(
      "AvaliacaoPedagogica", back_populates="aluno", cascade="all, delete-orphan"
  )
  contratos = relationship(
      "Contrato", back_populates="aluno", cascade="all, delete-orphan"
  )
  atividades = relationship(
      "AtividadeAluno", back_populates="aluno", cascade="all, delete-orphan"
  )
  desempenhos = relationship(
      "DesempenhoPais", back_populates="aluno", cascade="all, delete-orphan"
  )


class Contrato(Base):
  __tablename__ = "contratos"
  id = Column(Integer, primary_key=True)
  aluno_id = Column(Integer, ForeignKey("alunos.id"))
  descricao_servico = Column(String(150), default="Intervenção Pedagógica")
  valor_mensalidade = Column(Float, nullable=False)
  dia_vencimento = Column(Integer, nullable=False)
  data_inicio = Column(Date)
  status = Column(String(20), default="Ativo")

  aluno = relationship("Aluno", back_populates="contratos")
  mensalidades = relationship(
      "Mensalidade", back_populates="contrato", cascade="all, delete-orphan"
  )


class Mensalidade(Base):
  __tablename__ = "mensalidades"
  id = Column(Integer, primary_key=True)
  contrato_id = Column(Integer, ForeignKey("contratos.id"))
  data_vencimento = Column(Date, nullable=False)
  valor = Column(Float, nullable=False)
  status = Column(String(20), default="Pendente")
  data_pagamento = Column(Date, nullable=True)

  contrato = relationship("Contrato", back_populates="mensalidades")


class AvaliacaoPedagogica(Base):
  __tablename__ = "avaliacoes_pedagogicas"
  id = Column(Integer, primary_key=True)
  aluno_id = Column(Integer, ForeignKey("alunos.id"))
  data_sessao = Column(Date, default=date.today)
  objetivo_sessao = Column(String(200))
  relato_evolucao = Column(Text)
  link_google_form = Column(String(300), nullable=True)

  aluno = relationship("Aluno", back_populates="avaliacoes")


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


class DesempenhoPais(Base):
  __tablename__ = "desempenho_pais"
  id = Column(Integer, primary_key=True)
  aluno_id = Column(Integer, ForeignKey("alunos.id"))
  link_google_sheets = Column(String(400), nullable=True)
  resumo_apresentacao = Column(Text)

  aluno = relationship("Aluno", back_populates="desempenhos")


Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


# --- FUNÇÕES DE SEGURANÇA E UTILITÁRIOS ---
def gerar_hash_senha(senha: str) -> str:
  return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def limpar_cpf(cpf: str) -> str:
  return re.sub(r"\D", "", cpf)


def criar_usuario_admin_padrao():
  db = SessionLocal()
  try:
    if db.query(Usuario).count() == 0:
      admin = Usuario(
          nome="Administrador Espaço Dinâmico",
          cpf="00000000000",
          senha_hash=gerar_hash_senha("admin123"),
          perfil="Admin",
      )
      db.add(admin)
      db.commit()
  finally:
    db.close()


def para_str_br(d):
  if isinstance(d, (date, datetime)):
    return d.strftime("%d/%m/%Y")
  return str(d) if d else "-"


def calcular_idade(data_nasc):
  if not data_nasc:
    return "-"
  hoje = date.today()
  return (
      f"{hoje.year - data_nasc.year - ((hoje.month, hoje.day) < (data_nasc.month, data_nasc.day))} anos"
  )


def para_date_obj(data_str):
  try:
    return datetime.strptime(data_str.strip(), "%d/%m/%Y").date()
  except (ValueError, AttributeError):
    return date.today()


def get_img_as_base64(file):
  if os.path.exists(file):
    with open(file, "rb") as f:
      return base64.b64encode(f.read()).decode()
  return ""


@st.cache_data(ttl=600)
def carregar_aba_observacao_atendimento(url_sheets):
  try:
    if not url_sheets or "/d/" not in url_sheets:
      return None
    sheet_id = url_sheets.split("/d/")[1].split("/")[0]
    aba_nome = urllib.parse.quote("OBSERVAÇÃO DO ATENDIMENTO")
    csv_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={aba_nome}"
    )
    return pd.read_csv(csv_url)
  except Exception:
    return None


def filtrar_aluno_planilha(df_obs, nome_aluno):
  if df_obs is None or df_obs.empty:
    return pd.DataFrame()
  col_nome = next(
      (col for col in df_obs.columns if "nome" in col.lower()), None
  )
  if not col_nome:
    return pd.DataFrame()
  termo = nome_aluno.strip().lower()
  df_aluno = df_obs[
      df_obs[col_nome].astype(str).str.strip().str.lower() == termo
  ]
  if df_aluno.empty:
    df_aluno = df_obs[
        df_obs[col_nome]
        .astype(str)
        .str.strip()
        .str.lower()
        .str.contains(termo.split()[0], na=False)
    ]
  return df_aluno


# --- TELA DE LOGIN ELEGANTE ---
def renderizar_tela_login(session_db, logo_path):
  logo_base64 = get_img_as_base64(logo_path)

  st.markdown(
      f"""
        <style>
            .stApp {{
                background-image: linear-gradient(rgba(255, 255, 255, 0.93), rgba(255, 255, 255, 0.93)), url("data:image/png;base64,{logo_base64}");
                background-size: 350px;
                background-position: center;
                background-repeat: no-repeat;
                background-attachment: fixed;
            }}
            .login-card {{
                background: rgba(255, 255, 255, 0.98);
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 10px 25px rgba(0,0,0,0.08);
                border: 1px solid #e2e8f0;
            }}
        </style>
    """,
      unsafe_allow_html=True,
  )

  _, col_centro, _ = st.columns([1, 1.2, 1])
  with col_centro:
    st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
    if os.path.exists(logo_path):
      st.image(logo_path, width=120)

    st.markdown(
        """
            <h2 style='color: #0284c7; font-weight: 700; margin-bottom: 0px;'>Espaço Dinâmico</h2>
            <p style='color: #64748b; font-size: 15px; margin-bottom: 25px;'>Sistema de Gestão Integrada</p>
        """,
        unsafe_allow_html=True,
    )

    with st.form("form_login"):
      cpf_input = st.text_input("CPF (Apenas números)", max_chars=14)
      senha_input = st.text_input("Senha", type="password")
      btn_login = st.form_submit_button(
          "Entrar no Sistema", use_container_width=True
      )

      if btn_login:
        cpf_limpo = limpar_cpf(cpf_input)
        if not cpf_limpo or not senha_input:
          st.error("Preencha o CPF e a Senha.")
        else:
          hash_senha = gerar_hash_senha(senha_input)
          usuario = (
              session_db.query(Usuario)
              .filter(Usuario.cpf == cpf_limpo)
              .first()
          )

          if usuario and usuario.senha_hash == hash_senha:
            st.session_state["usuario_logado"] = usuario.nome
            st.session_state["perfil_usuario"] = usuario.perfil
            st.success(f"Bem-vindo(a), {usuario.nome}!")
            st.rerun()
          else:
            st.error("CPF ou Senha incorretos.")


# --- APLICAÇÃO PRINCIPAL ---
def main():
  st.set_page_config(
      page_title="Espaço Dinâmico - Gestão", page_icon="🧩", layout="wide"
  )
  criar_usuario_admin_padrao()

  logo_path = "ABC DINÂMICO.png"
  session_db = SessionLocal()

  try:
    # --- PORTAL DOS PAIS ---
    aluno_url = st.query_params.get("aluno", None)
    if aluno_url:
      c_l, c_t = st.columns([1, 15])
      with c_l:
        if os.path.exists(logo_path):
          st.image(logo_path, width=75)
      with c_t:
        st.markdown(
            "<h1 style='margin:0; color:#0284c7; font-size:26px;'>Espaço"
            " Dinâmico</h1><h3 style='margin:0; color:#475569;'><span"
            " style='font-size:16px;'>Portal de Acompanhamento</span></h3>",
            unsafe_allow_html=True,
        )

      st.markdown("---")
      st.markdown(f"### 🌟 Relatório de Desenvolvimento: **{aluno_url}**")
      aluno_db = (
          session_db.query(Aluno)
          .filter(Aluno.nome.ilike(f"%{aluno_url}%"))
          .first()
      )

      if aluno_db and aluno_db.desempenhos and aluno_db.desempenhos[0].link_google_sheets:
        df_obs = carregar_aba_observacao_atendimento(
            aluno_db.desempenhos[0].link_google_sheets
        )
        df_aluno = filtrar_aluno_planilha(df_obs, aluno_url)
        if not df_aluno.empty:
          m1, m2 = st.columns(2)
          m1.metric("Atendimentos", len(df_aluno))
          m2.metric(
              "Último Atendimento",
              df_aluno.iloc[-1].get("Nº do atendimento", "-"),
          )
          st.markdown("---")
          st.dataframe(df_aluno, use_container_width=True)
        else:
          st.info("Nenhum registro publicado até o momento.")
      else:
        st.info("Acompanhamento não configurado para este aluno.")
      return

    # --- VERIFICAÇÃO DE LOGIN ---
    if "usuario_logado" not in st.session_state:
      renderizar_tela_login(session_db, logo_path)
      return

    # --- HEADER DO SISTEMA ---
    col_l, col_t, col_u = st.columns([1, 11, 4])
    with col_l:
      if os.path.exists(logo_path):
        st.image(logo_path, width=70)
    with col_t:
      st.markdown(
          "<h1 style='margin:0; color:#1e293b; font-size:26px;'>Espaço"
          " Dinâmico</h1><p style='margin:0; color:#64748b; font-size:13px;'>Sistema"
          " Integrado de Gestão Neuropsicopedagógica</p>",
          unsafe_allow_html=True,
      )
    with col_u:
      st.markdown(
          f"<div style='text-align: right;'>👤 <b>{st.session_state['usuario_logado']}</b></div>",
          unsafe_allow_html=True,
      )
      if st.button("🚪 Sair do Sistema", use_container_width=True):
        del st.session_state["usuario_logado"]
        st.rerun()

    st.markdown("---")

    menu_opcao = st.radio(
        "Navegação",
        [
            "📊 Painel",
            "👥 Cadastros",
            "📄 Contratos",
            "💰 Financeiro",
            "📂 Prontuário",
            "📁 Atividades",
            "📈 Desempenho & Sheets",
            "🔐 Gerenciar Usuários",
        ],
        horizontal=True,
    )
    st.markdown("---")

    # --- PAINEL ---
    if menu_opcao == "📊 Painel":
      st.header("📊 Visão Geral")
      c1, c2, c3, c4 = st.columns(4)
      c1.metric("Alunos", session_db.query(Aluno).count())
      c2.metric("Responsáveis", session_db.query(Responsavel).count())
      c3.metric(
          "Contratos Ativos",
          session_db.query(Contrato).filter_by(status="Ativo").count(),
      )
      c4.metric(
          "Mensalidades Pendentes",
          session_db.query(Mensalidade).filter_by(status="Pendente").count(),
      )

      st.markdown("### 📋 Resumo dos Alunos")
      alunos = session_db.query(Aluno).all()
      if alunos:
        dados = [
            {
                "ID": a.id,
                "Aluno": a.nome,
                "Nascimento": para_str_br(a.data_nascimento),
                "Idade": calcular_idade(a.data_nascimento),
                "Escolaridade": a.escolaridade or "-",
                "Responsável": (
                    a.responsavel.nome if a.responsavel else "-"
                ),
            }
            for a in alunos
        ]
        st.dataframe(pd.DataFrame(dados), use_container_width=True)

    # --- CADASTROS ---
    elif menu_opcao == "👥 Cadastros":
      st.header("👥 Gestão de Cadastros")
      tab1, tab2 = st.tabs(["Novo Cadastro", "Gerenciar Alunos"])

      with tab1:
        col_r, col_a = st.columns(2)
        with col_r:
          with st.form("f_resp"):
            st.subheader("Novo Responsável")
            nome_r = st.text_input("Nome Completo *")
            tel_r = st.text_input("WhatsApp / Telefone *")
            if st.form_submit_button("Salvar Responsável") and nome_r:
              session_db.add(Responsavel(nome=nome_r.strip(), telefone=tel_r))
              session_db.commit()
              st.toast("Responsável salvo com sucesso!", icon="✅")
              st.rerun()

        with col_a:
          responsaveis = session_db.query(Responsavel).all()
          resp_dict = {f"{r.id} - {r.nome}": r.id for r in responsaveis}
          with st.form("f_aluno"):
            st.subheader("Novo Aluno")
            nome_a = st.text_input("Nome do Aluno *")
            nasc_a = st.text_input(
                "Data Nasc. (DD/MM/AAAA)", value=date.today().strftime("%d/%m/%Y")
            )
            esc_a = st.text_input("Escolaridade")
            r_sel = (
                st.selectbox("Responsável", list(resp_dict.keys()))
                if resp_dict
                else None
            )
            r_id = resp_dict[r_sel] if r_sel else None

            if st.form_submit_button("Salvar Aluno") and nome_a:
              novo_a = Aluno(
                  nome=nome_a.strip(),
                  data_nascimento=para_date_obj(nasc_a),
                  escolaridade=esc_a,
                  responsavel_id=r_id,
              )
              session_db.add(novo_a)
              session_db.commit()
              st.toast("Aluno cadastrado!", icon="✅")
              st.rerun()

      with tab2:
        alunos = session_db.query(Aluno).all()
        if alunos:
          a_dict = {f"{a.id} - {a.nome}": a for a in alunos}
          sel = st.selectbox(
              "Selecione o Aluno para Editar", list(a_dict.keys())
          )
          aluno_edit = a_dict[sel]

          with st.form("f_edit_a"):
            novo_nome = st.text_input("Nome", value=aluno_edit.nome)
            nova_nasc = st.text_input(
                "Nascimento",
                value=(
                    aluno_edit.data_nascimento.strftime("%d/%m/%Y")
                    if aluno_edit.data_nascimento
                    else ""
                ),
            )
            nova_esc = st.text_input(
                "Escolaridade", value=aluno_edit.escolaridade or ""
            )

            col_b1, col_b2 = st.columns(2)
            if col_b1.form_submit_button("Atualizar"):
              aluno_edit.nome = novo_nome.strip()
              aluno_edit.data_nascimento = para_date_obj(nova_nasc)
              aluno_edit.escolaridade = nova_esc
              session_db.commit()
              st.toast("Atualizado com sucesso!")
              st.rerun()
            if col_b2.form_submit_button("Excluir Aluno"):
              session_db.delete(aluno_edit)
              session_db.commit()
              st.toast("Aluno removido!")
              st.rerun()

    # --- GERENCIAR USUÁRIOS (COM ALTERAÇÃO DE SENHA E EXCLUSÃO) ---
    elif menu_opcao == "🔐 Gerenciar Usuários":
      st.header("🔐 Controle de Usuários e Acessos")
      t_novo, t_gerenciar = st.tabs(
          ["Cadastrar Novo Usuário", "Editar / Excluir Usuários"]
      )

      with t_novo:
        with st.form("f_novo_usuario"):
          nome_u = st.text_input("Nome Completo *")
          cpf_u = st.text_input("CPF (Apenas números) *", max_chars=14)
          senha_u = st.text_input("Senha *", type="password")
          perfil_u = st.selectbox("Perfil", ["Admin", "Atendente"])

          if st.form_submit_button("Cadastrar Usuário"):
            cpf_limpo = limpar_cpf(cpf_u)
            if not nome_u or not cpf_limpo or not senha_u:
              st.error("Preencha todos os campos obrigatórios.")
            elif (
                session_db.query(Usuario)
                .filter(Usuario.cpf == cpf_limpo)
                .first()
            ):
              st.error("Já existe usuário cadastrado com este CPF.")
            else:
              session_db.add(
                  Usuario(
                      nome=nome_u.strip(),
                      cpf=cpf_limpo,
                      senha_hash=gerar_hash_senha(senha_u),
                      perfil=perfil_u,
                  )
              )
              session_db.commit()
              st.success("Usuário cadastrado com sucesso!")
              st.rerun()

      with t_gerenciar:
        users = session_db.query(Usuario).all()
        if users:
          u_dict = {f"{u.nome} (CPF: {u.cpf})": u for u in users}
          sel_u = st.selectbox("Selecione o Usuário", list(u_dict.keys()))
          usr_obj = u_dict[sel_u]

          with st.form("f_alt_usuario"):
            st.subheader(f"Gerenciar: {usr_obj.nome}")
            nova_senha = st.text_input(
                "Nova Senha (deixe em branco para não alterar)", type="password"
            )

            c_btn1, c_btn2 = st.columns(2)
            if c_btn1.form_submit_button("Salvar Alteração de Senha"):
              if nova_senha:
                usr_obj.senha_hash = gerar_hash_senha(nova_senha)
                session_db.commit()
                st.success("Senha atualizada com sucesso!")
                st.rerun()
              else:
                st.warning("Informe a nova senha.")

            if c_btn2.form_submit_button("Excluir Usuário"):
              if usr_obj.cpf == "00000000000":
                st.error("Não é permitido excluir o Administrador padrão.")
              else:
                session_db.delete(usr_obj)
                session_db.commit()
                st.success("Usuário excluído com sucesso!")
                st.rerun()

    # --- DESEMPENHO E SHEETS ---
    elif menu_opcao == "📈 Desempenho & Sheets":
      st.header("📈 Módulo de Desempenho e Portal dos Pais")
      alunos = session_db.query(Aluno).all()
      if alunos:
        a_dict = {f"{a.id} - {a.nome}": a for a in alunos}
        sel_a = st.selectbox("Selecione o Aluno", list(a_dict.keys()))
        aluno_obj = a_dict[sel_a]

        config = (
            session_db.query(DesempenhoPais)
            .filter_by(aluno_id=aluno_obj.id)
            .first()
        )
        link_atual = config.link_google_sheets if config else ""

        with st.form("f_sheets"):
          url_in = st.text_input(
              "Link da Planilha Mestre (Google Sheets)", value=link_atual
          )
          if st.form_submit_button("Salvar Planilha"):
            if config:
              config.link_google_sheets = url_in
            else:
              session_db.add(
                  DesempenhoPais(
                      aluno_id=aluno_obj.id, link_google_sheets=url_in
                  )
              )
            session_db.commit()
            st.toast("Link salvo com sucesso!")
            st.rerun()

        st.markdown("---")
        st.subheader("🔗 Link de Acesso Exclusivo para os Pais")
        nome_enc = urllib.parse.quote(aluno_obj.nome)
        host_url = os.getenv("APP_URL", "http://localhost:8501")
        st.code(f"{host_url}/?aluno={nome_enc}", language="text")

  finally:
    session_db.close()


if __name__ == "__main__":
  main()