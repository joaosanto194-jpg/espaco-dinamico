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

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///espaco_dinamico.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
Base = declarative_base()


# --- MODELOS COMPLETOS ---
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
  prontuarios = relationship(
      "Prontuario", back_populates="aluno", cascade="all, delete-orphan"
  )
  contratos = relationship(
      "Contrato", back_populates="aluno", cascade="all, delete-orphan"
  )
  atividades = relationship(
      "AtividadeAluno", back_populates="aluno", cascade="all, delete-orphan"
  )


class Prontuario(Base):
  __tablename__ = "prontuarios"
  id = Column(Integer, primary_key=True)
  aluno_id = Column(Integer, ForeignKey("alunos.id"))
  data_registro = Column(Date, default=date.today)
  queixa_principal = Column(Text)
  hipotese_diagnostica = Column(Text)
  conduta = Column(Text)
  aluno = relationship("Aluno", back_populates="prontuarios")


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
  chave = Column(String(50), unique=True, nullable=False)
  valor = Column(Text, nullable=True)


Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


# --- UTILITÁRIOS ---
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


@st.cache_data(ttl=300)
def carregar_planilha_observacao_atendimento(url_sheets):
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


def filtrar_e_analisar_aluno(df_obs, nome_aluno):
  if df_obs is None or df_obs.empty:
    return pd.DataFrame(), []

  col_nome = next(
      (col for col in df_obs.columns if "nome" in col.lower()), None
  )
  if not col_nome:
    return pd.DataFrame(), []

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

  if df_aluno.empty:
    return pd.DataFrame(), []

  # Seleciona as colunas de F até M (índices 5 a 12 no DataFrame, se existirem)
  colunas_disponiveis = list(df_aluno.columns)
  if len(colunas_disponiveis) >= 13:
    colunas_indicadores = colunas_disponiveis[5:13]  # F até M
  else:
    colunas_indicadores = colunas_disponiveis[
        max(1, len(colunas_disponiveis) - 8) :
    ]

  return df_aluno, colunas_indicadores


# --- DESIGN SYSTEM ---
def aplicar_estilo_global():
  st.markdown(
      """
        <style>
            .stApp { background-color: #f8fafc; font-family: 'Inter', sans-serif; }
            div[data-testid="stMetric"] {
                background-color: #ffffff; padding: 18px; border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03); border: 1px solid #e2e8f0;
            }
            .stButton > button { border-radius: 8px; font-weight: 600; border: none; }
        </style>
    """,
      unsafe_allow_html=True,
  )


# --- LOGIN ---
def renderizar_tela_login(session_db, logo_path):
  aplicar_estilo_global()
  _, col_centro, _ = st.columns([1, 1.3, 1])
  with col_centro:
    st.markdown("<div style='height: 60px;'></div>", unsafe_allow_html=True)
    c_img, c_txt = st.columns([1, 3])
    with c_img:
      if os.path.exists(logo_path):
        st.image(logo_path, width=90)
    with c_txt:
      st.markdown(
          "<h2 style='color: #0284c7; font-weight: 800; margin: 0; padding-top:"
          " 10px;'>Espaço Dinâmico</h2><p style='color: #64748b; font-size: 14px;"
          " margin: 0;'>Gestão Neuropsicopedagógica</p>",
          unsafe_allow_html=True,
      )

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    with st.form("form_login"):
      st.markdown(
          "<h4 style='color: #1e293b; margin-bottom: 15px;'>🔐 Acesso"
          " Restrito</h4>",
          unsafe_allow_html=True,
      )
      cpf_input = st.text_input("CPF (Apenas números)", max_chars=14)
      senha_input = st.text_input("Senha", type="password")
      if st.form_submit_button("Entrar no Sistema", use_container_width=True):
        cpf_limpo = limpar_cpf(cpf_input)
        usuario = (
            session_db.query(Usuario)
            .filter(Usuario.cpf == cpf_limpo)
            .first()
        )
        if usuario and usuario.senha_hash == gerar_hash_senha(senha_input):
          st.session_state["usuario_logado"] = usuario.nome
          st.session_state["perfil_usuario"] = usuario.perfil
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
    # PORTAL DOS PAIS (Via Link Público)
    aluno_url = st.query_params.get("aluno", None)
    if aluno_url:
      aplicar_estilo_global()
      st.markdown(
          f"### 🌟 Relatório de Desempenho Familiar: **{aluno_url}**"
      )
      cfg_sheet = (
          session_db.query(ConfiguracaoSistema)
          .filter_by(chave="link_planilha_mestre")
          .first()
      )
      if cfg_sheet and cfg_sheet.valor:
        df_obs = carregar_planilha_observacao_atendimento(cfg_sheet.valor)
        df_aluno, cols_ind = filtrar_e_analisar_aluno(df_obs, aluno_url)
        if not df_aluno.empty:
          st.dataframe(df_aluno, use_container_width=True)
          if cols_ind:
            st.markdown(
                "#### 📊 Gráfico de Indicadores de Avaliação (Colunas F a M)"
            )
            df_grafico = df_aluno[cols_ind].apply(
                pd.to_numeric, errors="coerce"
            )
            if not df_grafico.empty:
              st.line_chart(df_grafico)
        else:
          st.info("Nenhum registro encontrado na aba OBSERVAÇÃO DO ATENDIMENTO.")
      else:
        st.warning("Planilha mestre não configurada.")
      return

    if "usuario_logado" not in st.session_state:
      renderizar_tela_login(session_db, logo_path)
      return

    aplicar_estilo_global()

    # HEADER
    col_l, col_t, col_u = st.columns([0.8, 11.2, 4])
    with col_l:
      if os.path.exists(logo_path):
        st.image(logo_path, width=65)
    with col_t:
      st.markdown(
          "<h1 style='margin:0; color:#0f172a; font-size:24px;'>Espaço"
          " Dinâmico</h1><p style='margin:0; color:#64748b; font-size:13px;'>Sistema"
          " Integrado de Alta Performance</p>",
          unsafe_allow_html=True,
      )
    with col_u:
      st.markdown(
          f"<div style='text-align: right;'>👤"
          f" <b>{st.session_state['usuario_logado']}</b></div>",
          unsafe_allow_html=True,
      )
      if st.button("🚪 Sair", use_container_width=True):
        del st.session_state["usuario_logado"]
        st.rerun()

    st.markdown("---")

    menu_opcao = st.radio(
        "Navegação",
        [
            "📊 Painel",
            "👥 Cadastros",
            "📄 Contratos",
            "📂 Prontuário",
            "📁 Atividades",
            "📈 Desempenho & Planilha Mestre",
            "🔐 Gerenciar Usuários",
        ],
        horizontal=True,
    )
    st.markdown("---")

    # 1. PAINEL
    if menu_opcao == "📊 Painel":
      st.header("📊 Visão Geral do Sistema")
      c1, c2, c3, c4 = st.columns(4)
      c1.metric("Alunos", session_db.query(Aluno).count())
      c2.metric("Responsáveis", session_db.query(Responsavel).count())
      c3.metric(
          "Contratos Ativos",
          session_db.query(Contrato).filter_by(status="Ativo").count(),
      )
      c4.metric("Prontuários", session_db.query(Prontuario).count())

      st.markdown("### 📋 Alunos Cadastrados")
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
      else:
        st.info("Nenhum aluno cadastrado no momento.")

    # 2. CADASTROS
    elif menu_opcao == "👥 Cadastros":
      st.header("👥 Gestão de Cadastros (Alunos e Responsáveis)")
      tab1, tab2 = st.tabs(["Cadastrar", "Gerenciar Base"])

      with tab1:
        c_r, c_a = st.columns(2)
        with c_r:
          with st.form("f_resp"):
            st.subheader("Novo Responsável")
            nome_r = st.text_input("Nome do Responsável *")
            tel_r = st.text_input("Telefone / WhatsApp *")
            if st.form_submit_button("Salvar Responsável") and nome_r:
              session_db.add(Responsavel(nome=nome_r.strip(), telefone=tel_r))
              session_db.commit()
              st.success("Responsável cadastrado!")
              st.rerun()

        with c_a:
          resps = session_db.query(Responsavel).all()
          resp_map = {f"{r.id} - {r.nome}": r.id for r in resps}
          with st.form("f_aluno"):
            st.subheader("Novo Aluno")
            nome_a = st.text_input("Nome Completo do Aluno *")
            nasc_a = st.text_input(
                "Data de Nascimento (DD/MM/AAAA)",
                value=date.today().strftime("%d/%m/%Y"),
            )
            esc_a = st.text_input("Escolaridade")
            r_sel = (
                st.selectbox("Responsável", list(resp_map.keys()))
                if resp_map
                else None
            )
            if st.form_submit_button("Salvar Aluno") and nome_a:
              novo = Aluno(
                  nome=nome_a.strip(),
                  data_nascimento=para_date_obj(nasc_a),
                  escolaridade=esc_a,
                  responsavel_id=resp_map[r_sel] if r_sel else None,
              )
              session_db.add(novo)
              session_db.commit()
              st.success("Aluno cadastrado com sucesso!")
              st.rerun()

      with tab2:
        alunos = session_db.query(Aluno).all()
        if alunos:
          a_dict = {f"{a.id} - {a.nome}": a for a in alunos}
          sel_edit = st.selectbox("Selecione o Aluno", list(a_dict.keys()))
          aluno_sel = a_dict[sel_edit]
          with st.form("f_edt_aluno"):
            n_nome = st.text_input("Nome", value=aluno_sel.nome)
            if st.form_submit_button("Atualizar Aluno"):
              aluno_sel.nome = n_nome.strip()
              session_db.commit()
              st.success("Atualizado!")
              st.rerun()
            if st.form_submit_button("Excluir Aluno"):
              session_db.delete(aluno_sel)
              session_db.commit()
              st.warning("Removido!")
              st.rerun()

    # 3. CONTRATOS
    elif menu_opcao == "📄 Contratos":
      st.header("📄 Gestão de Contratos e Mensalidades")
      alunos = session_db.query(Aluno).all()
      if alunos:
        a_map = {f"{a.id} - {a.nome}": a.id for a in alunos}
        with st.form("f_contrato"):
          aluno_sel = st.selectbox("Aluno", list(a_map.keys()))
          servico = st.text_input(
              "Descrição do Serviço", value="Intervenção Pedagógica"
          )
          valor = st.number_input("Valor da Mensalidade (R$)", value=350.0)
          venc = st.number_input(
              "Dia de Vencimento", min_value=1, max_value=31, value=10
          )
          if st.form_submit_button("Criar Contrato"):
            session_db.add(
                Contrato(
                    aluno_id=a_map[aluno_sel],
                    descricao_servico=servico,
                    valor_mensalidade=valor,
                    dia_vencimento=int(venc),
                    data_inicio=date.today(),
                )
            )
            session_db.commit()
            st.success("Contrato registrado!")
            st.rerun()
      contratos = session_db.query(Contrato).all()
      if contratos:
        df_c = pd.DataFrame([
            {
                "ID": c.id,
                "Aluno": c.aluno.nome if c.aluno else "-",
                "Serviço": c.descricao_servico,
                "Valor": f"R$ {c.valor_mensalidade:.2f}",
                "Vencimento": f"Dia {c.dia_vencimento}",
                "Status": c.status,
            }
            for c in contratos
        ])
        st.dataframe(df_c, use_container_width=True)

    # 4. PRONTUÁRIO
    elif menu_opcao == "📂 Prontuário":
      st.header("📂 Prontuário e Evolução Clínica")
      alunos = session_db.query(Aluno).all()
      if alunos:
        a_map = {f"{a.id} - {a.nome}": a.id for a in alunos}
        sel_a = st.selectbox("Selecione o Aluno", list(a_map.keys()))
        aluno_id = a_map[sel_a]

        with st.form("f_prontuario"):
          queixa = st.text_area("Queixa Principal / Anamnese")
          hipotese = st.text_area("Hipótese Diagnóstica")
          conduta = st.text_area("Conduta Terapêutica / Intervenção")
          if st.form_submit_button("Salvar Prontuário"):
            session_db.add(
                Prontuario(
                    aluno_id=aluno_id,
                    queixa_principal=queixa,
                    hipotese_diagnostica=hipotese,
                    conduta=conduta,
                )
            )
            session_db.commit()
            st.success("Prontuário atualizado!")
            st.rerun()

        prontuarios = (
            session_db.query(Prontuario).filter_by(aluno_id=aluno_id).all()
        )
        for p in prontuarios:
          with st.expander(f"Registro em: {para_str_br(p.data_registro)}"):
            st.write(f"**Queixa:** {p.queixa_principal}")
            st.write(f"**Hipótese:** {p.hipotese_diagnostica}")
            st.write(f"**Conduta:** {p.conduta}")

    # 5. ATIVIDADES
    elif menu_opcao == "📁 Atividades":
      st.header("📁 Registro de Atividades Pedagógicas")
      alunos = session_db.query(Aluno).all()
      if alunos:
        a_map = {f"{a.id} - {a.nome}": a.id for a in alunos}
        with st.form("f_atividade"):
          aluno_sel = st.selectbox("Aluno", list(a_map.keys()))
          titulo = st.text_input("Título da Atividade *")
          desc = st.text_area("Descrição detalhada da atividade realizada")
          if st.form_submit_button("Salvar Atividade") and titulo:
            session_db.add(
                AtividadeAluno(
                    aluno_id=a_map[aluno_sel], titulo=titulo, descricao=desc
                )
            )
            session_db.commit()
            st.success("Atividade salva!")
            st.rerun()

    # 6. DESEMPENHO E PLANILHA MESTRE (COM FILTRO F-M E GRÁFICO)
    elif menu_opcao == "📈 Desempenho & Planilha Mestre":
      st.header(
          "📈 Planilha Mestre (OBSERVAÇÃO DO ATENDIMENTO) & Gráfico de"
          " Desempenho"
      )

      cfg = (
          session_db.query(ConfiguracaoSistema)
          .filter_by(chave="link_planilha_mestre")
          .first()
      )
      link_atual = cfg.valor if cfg else ""

      with st.form("f_mestre"):
        st.subheader("Configurar Link Único da Planilha Mestre (Google Sheets)")
        novo_link = st.text_input(
            "Cole o link público da Planilha Mestre", value=link_atual
        )
        if st.form_submit_button("Salvar Link Mestre"):
          if cfg:
            cfg.valor = novo_link
          else:
            session_db.add(
                ConfiguracaoSistema(
                    chave="link_planilha_mestre", valor=novo_link
                )
            )
          session_db.commit()
          st.success("Link mestre salvo com sucesso!")
          st.rerun()

      st.markdown("---")
      st.subheader("🔍 Indicadores e Gráfico de Desempenho por Aluno")
      alunos = session_db.query(Aluno).all()
      if alunos and link_atual:
        a_dict = {f"{a.id} - {a.nome}": a.nome for a in alunos}
        sel_aluno = st.selectbox(
            "Selecione o Aluno para análise", list(a_dict.keys())
        )
        nome_aluno_pesquisa = a_dict[sel_aluno]

        df_mestre = carregar_planilha_observacao_atendimento(link_atual)
        df_filtrado, cols_indicadores = filtrar_emprego_aluno_analitico = (
            filtrar_e_analisar_aluno(df_mestre, nome_aluno_pesquisa)
        )

        if not df_filtrado.empty:
          st.success(
              f"Registros encontrados na aba OBSERVAÇÃO DO ATENDIMENTO para"
              f" {nome_aluno_pesquisa}: {len(df_filtrado)}"
          )
          st.dataframe(df_filtrado, use_container_width=True)

          if cols_indicadores:
            st.markdown(
                "### 📊 Gráfico de Evolução (Indicadores das Colunas F a M)"
            )
            df_grafico = df_filtrado[cols_indicadores].apply(
                pd.to_numeric, errors="coerce"
            )
            if not df_grafico.empty:
              st.line_chart(df_grafico)
            else:
              st.info(
                  "Os indicadores selecionados (Colunas F a M) não possuem"
                  " valores numéricos para plotagem no gráfico."
              )
        else:
          st.info(
              "Nenhum registro encontrado para este aluno na aba OBSERVAÇÃO DO"
              " ATENDIMENTO."
          )

        st.markdown("---")
        st.subheader("🔗 Link de Acesso Exclusivo para os Pais")
        host_url = os.getenv("APP_URL", "http://localhost:8501")
        link_familia = (
            f"{host_url}/?aluno={urllib.parse.quote(nome_aluno_pesquisa)}"
        )
        st.code(link_familia, language="text")

    # 7. GERENCIAR USUÁRIOS
    elif menu_opcao == "🔐 Gerenciar Usuários":
      st.header("🔐 Controle de Acessos")
      with st.form("f_cad_usr"):
        nome_u = st.text_input("Nome Completo")
        cpf_u = st.text_input("CPF (Apenas números)", max_chars=14)
        senha_u = st.text_input("Senha", type="password")
        if st.form_submit_button("Cadastrar Usuário"):
          cpf_limpo = limpar_cpf(cpf_u)
          if nome_u and cpf_limpo and senha_u:
            session_db.add(
                Usuario(
                    nome=nome_u,
                    cpf=cpf_limpo,
                    senha_hash=gerar_hash_senha(senha_u),
                )
            )
            session_db.commit()
            st.success("Usuário cadastrado!")
            st.rerun()

  finally:
    session_db.close()


if __name__ == "__main__":
  main()