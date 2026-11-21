from datetime import date, datetime, timedelta
import calendar
import hashlib
import html
import json
import time
import os
import re
import secrets
import shutil
import sqlite3
import urllib.parse
import urllib.request
import urllib.error
import textwrap
import uuid
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from sqlalchemy import (
    Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
    create_engine, func, inspect, or_, text as sql_text
)
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import (
    declarative_base,
    joinedload,
    relationship,
    sessionmaker
)
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


# ============================================================
# CONFIGURAÇÃO DO BANCO DE DADOS
# ESPAÇO DINÂMICO - SUPABASE POSTGRESQL
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

# Banco SQLite local - preservado como alternativa
DB_IN_APP = BASE_DIR / "espaco_dinamico.db"
DB_IN_CWD = Path.cwd() / "espaco_dinamico.db"


def obter_database_url():

    # 1. Verifica variável de ambiente
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        return database_url

    # 2. Verifica Secrets do Streamlit Cloud
    try:
        cfg = st.secrets.get("database")
    except Exception:
        cfg = None

    if cfg:

        campos_obrigatorios = ["host", "user", "password"]

        faltantes = [
            campo for campo in campos_obrigatorios
            if not cfg.get(campo)
        ]

        if faltantes:
            raise RuntimeError(
                "Configuração PostgreSQL incompleta. "
                f"Campos ausentes: {', '.join(faltantes)}"
            )

        return URL.create(
            drivername="postgresql+psycopg",
            username=str(cfg["user"]),
            password=str(cfg["password"]),
            host=str(cfg["host"]),
            port=int(cfg.get("port", 5432)),
            database=str(cfg.get("name", "postgres")),
            query={
                "sslmode": str(cfg.get("sslmode", "require"))
            }
        )

    # 3. Alternativa: SQLite local
    if DB_IN_APP.exists():
        DB_PATH = DB_IN_APP
    elif DB_IN_CWD.exists():
        DB_PATH = DB_IN_CWD
    else:
        DB_PATH = DB_IN_APP

    return f"sqlite:///{DB_PATH.as_posix()}"


# Obtém a conexão configurada
DATABASE_URL = obter_database_url()

# Identifica o banco utilizado
USANDO_SQLITE = str(DATABASE_URL).startswith("sqlite")


@st.cache_resource(show_spinner=False)
def criar_engine():
    """Cria UM pool de conexões por processo.

    O Streamlit reexecuta o script inteiro a cada clique; antes, um novo
    engine (e um novo pool de conexões com o Supabase) era criado em toda
    interação, deixando o sistema lento e consumindo conexões.
    """
    url = obter_database_url()
    sqlite = str(url).startswith("sqlite")
    return create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30} if sqlite else {},
        pool_pre_ping=True,
        pool_recycle=1800,
    )


engine = criar_engine()

# Base dos modelos
Base = declarative_base()

# Sessões do banco
SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False
)

# ============================================================
# FIM DA CONFIGURAÇÃO DO BANCO DE DADOS
# ============================================================


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
    status = Column(String(30), default="Realizada")
    # Campos novos são adicionados por migração aditiva e preservam registros legados.
    area = Column(String(100), nullable=True)
    objetivo = Column(Text, nullable=True)
    data_prazo = Column(Date, nullable=True)
    resultado = Column(Text, nullable=True)
    observacoes = Column(Text, nullable=True)
    aluno = relationship("Aluno", back_populates="atividades")


class DocumentoAluno(Base):
    __tablename__ = "documentos_alunos"
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    titulo = Column(String(180), nullable=False)
    categoria = Column(String(80), nullable=False)
    descricao = Column(Text, nullable=True)
    nome_original = Column(String(255), nullable=False)
    caminho_storage = Column(String(500), nullable=False, unique=True)
    mime_type = Column(String(100), nullable=False, default="application/pdf")
    tamanho_bytes = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="Ativo")
    criado_em = Column(Date, nullable=False, default=date.today)
    criado_por = Column(String(100), nullable=True)
    # Caderno Digital (migração aditiva). Só aparece no portal com visivel_familia = 1.
    visivel_familia = Column(Integer, nullable=False, default=0, server_default="0")
    mensagem_familia = Column(Text, nullable=True)  # texto para os pais; a "descricao" é interna
    compartilhado_em = Column(DateTime, nullable=True)
    visualizacoes_familia = Column(Integer, nullable=False, default=0, server_default="0")
    aluno = relationship("Aluno")


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
    servico = Column(String(150), nullable=True)  # migração aditiva: serviço da receita (relatórios)
    aluno = relationship("Aluno")


class LinkFamiliar(Base):
    """Link individual e revogável para a família acompanhar o desempenho.

    Guarda apenas o hash SHA-256 do token: quem tiver acesso ao banco não
    consegue reconstruir o link.
    """
    __tablename__ = "links_familiares"
    id = Column(Integer, primary_key=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    expira_em = Column(Date, nullable=False)
    ativo = Column(Integer, nullable=False, default=1)
    criado_por = Column(String(100), nullable=True)
    acessos = Column(Integer, nullable=False, default=0)
    ultimo_acesso = Column(DateTime, nullable=True)
    # O que a família vê neste link (migração aditiva; links antigos continuam vendo tudo).
    ver_caderno = Column(Integer, nullable=False, default=1, server_default="1")
    ver_desempenho = Column(Integer, nullable=False, default=1, server_default="1")
    ver_atividades = Column(Integer, nullable=False, default=1, server_default="1")
    aluno = relationship("Aluno")


class MaterialPedagogico(Base):
    """PDF de atividade, material escolar ou avaliação.

    aluno_id vazio = acervo geral (material reutilizável para vários alunos).
    atividade_id liga o PDF a uma atividade registrada em 📁 Atividades.
    """
    __tablename__ = "materiais_pedagogicos"
    id = Column(Integer, primary_key=True)
    titulo = Column(String(180), nullable=False)
    tipo = Column(String(40), nullable=False, default="Atividade")
    area = Column(String(100), nullable=True)
    nivel = Column(String(100), nullable=True)  # série / ano escolar / faixa
    descricao = Column(Text, nullable=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=True, index=True)
    atividade_id = Column(Integer, ForeignKey("atividades_alunos.id"), nullable=True, index=True)
    nome_original = Column(String(255), nullable=False)
    caminho_storage = Column(String(500), nullable=False, unique=True)
    tamanho_bytes = Column(Integer, nullable=False, default=0)
    paginas = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=False, index=True)
    texto_extraido = Column(Text, nullable=True)  # usado só na busca interna
    status = Column(String(20), nullable=False, default="Ativo")
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    criado_por = Column(String(100), nullable=True)
    aluno = relationship("Aluno")
    atividade = relationship("AtividadeAluno")


class FolhaInterativa(Base):
    """Uma aplicação de um material em PDF a um aluno, preenchida com caneta no atendimento."""
    __tablename__ = "folhas_interativas"
    id = Column(Integer, primary_key=True)
    material_id = Column(Integer, ForeignKey("materiais_pedagogicos.id"), nullable=False, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    titulo = Column(String(180), nullable=False)
    status = Column(String(20), nullable=False, default="Em andamento")  # Em andamento / Concluída / Cancelada
    total_paginas = Column(Integer, nullable=False, default=1)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=True)
    concluido_em = Column(DateTime, nullable=True)
    criado_por = Column(String(100), nullable=True)
    documento_id = Column(Integer, ForeignKey("documentos_alunos.id"), nullable=True)  # PDF final no Caderno
    material = relationship("MaterialPedagogico")
    aluno = relationship("Aluno")


class FolhaPagina(Base):
    """Tinta de uma página (PNG transparente em base64), separada do fundo do PDF original."""
    __tablename__ = "folhas_paginas"
    __table_args__ = (UniqueConstraint("folha_id", "pagina", name="uq_folha_pagina"),)
    id = Column(Integer, primary_key=True)
    folha_id = Column(Integer, ForeignKey("folhas_interativas.id"), nullable=False, index=True)
    pagina = Column(Integer, nullable=False)
    tinta_png = Column(Text, nullable=True)
    atualizado_em = Column(DateTime, nullable=True)


class LogAuditoria(Base):
    """Trilha de quem fez o quê (login, links, senhas, mensalidades, documentos)."""
    __tablename__ = "log_auditoria"
    id = Column(Integer, primary_key=True)
    data_hora = Column(DateTime, nullable=False, default=datetime.now, index=True)
    usuario = Column(String(100), nullable=True)
    acao = Column(String(80), nullable=False)
    detalhe = Column(Text, nullable=True)


def backup_sqlite_automatico():
    """
    Cria uma cópia diária do banco SQLite antes da inicialização
    do esquema. Não executa backup SQLite no PostgreSQL.
    """

    # Backup automático somente quando estiver usando SQLite.
    if not USANDO_SQLITE:
        return

    caminho_texto = urllib.parse.unquote(
        DATABASE_URL.split("sqlite:///", 1)[1]
    )

    banco = Path(caminho_texto)

    if not banco.is_absolute():
        banco = (Path.cwd() / banco).resolve()

    if not banco.exists() or banco.name == ":memory:":
        return

    pasta_backup = BASE_DIR / "backups_banco"
    pasta_backup.mkdir(parents=True, exist_ok=True)

    destino = pasta_backup / (
        f"{banco.stem}_{datetime.now():%Y%m%d}.db"
    )

    if destino.exists():
        return

    origem_con = sqlite3.connect(str(banco), timeout=30)
    backup_con = sqlite3.connect(str(destino))

    try:
        origem_con.backup(backup_con)

    except Exception:
        try:
            backup_con.close()
            origem_con.close()
            destino.unlink(missing_ok=True)
        except Exception:
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


# ============================================================
# INICIALIZAÇÃO DO BANCO DE DADOS
# Executada UMA vez por processo (cache_resource), e não a cada clique.
# ============================================================

MIGRACOES_ADITIVAS = {
    "atividades_alunos": {
        "area": "VARCHAR(100)",
        "objetivo": "TEXT",
        "data_prazo": "DATE",
        "resultado": "TEXT",
        "observacoes": "TEXT",
    },
    # Caderno Digital: documentos existentes ficam PRIVADOS (visivel_familia = 0).
    "links_familiares": {
        "ver_caderno": "INTEGER NOT NULL DEFAULT 1",
        "ver_desempenho": "INTEGER NOT NULL DEFAULT 1",
        "ver_atividades": "INTEGER NOT NULL DEFAULT 1",
    },
    "lancamentos_financeiros": {
        "servico": "VARCHAR(150)",
    },
    "documentos_alunos": {
        "visivel_familia": "INTEGER NOT NULL DEFAULT 0",
        "mensagem_familia": "TEXT",
        "compartilhado_em": "TIMESTAMP",
        "visualizacoes_familia": "INTEGER NOT NULL DEFAULT 0",
    },
}


def aplicar_migracoes_aditivas():
    """Adiciona somente colunas ausentes; nunca remove/reescreve dados existentes."""
    inspetor = inspect(engine)
    for tabela, colunas_novas in MIGRACOES_ADITIVAS.items():
        if not inspetor.has_table(tabela):
            continue  # tabela nova: create_all já cria com todas as colunas
        existentes = {c["name"] for c in inspetor.get_columns(tabela)}
        for nome, tipo_sql in colunas_novas.items():
            if nome not in existentes:
                with engine.begin() as conexao:
                    conexao.execute(sql_text(f'ALTER TABLE {tabela} ADD COLUMN "{nome}" {tipo_sql}'))


def versao_esquema():
    """Assinatura do esquema esperado (tabelas + colunas do modelo + migrações aditivas).

    Vai como argumento de inicializar_banco: o cache_resource é por argumento, então qualquer
    mudança de esquema faz as migrações rodarem de novo. Sem isso, o Streamlit Cloud atualiza o
    código SEM reiniciar o processo e o cache antigo pulava as migrações (colunas novas ausentes).
    """
    partes = [json.dumps(MIGRACOES_ADITIVAS, sort_keys=True)]
    for nome, tabela in sorted(Base.metadata.tables.items()):
        partes.append(nome + ":" + ",".join(sorted(c.name for c in tabela.columns)))
    return hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()[:16]


def erro_de_esquema(exc):
    """Coluna/tabela inexistente (PostgreSQL ou SQLite): sinal de migração não aplicada."""
    texto = str(exc).casefold()
    return any(t in texto for t in ("undefinedcolumn", "undefinedtable", "does not exist",
                                    "no such column", "no such table"))


@st.cache_resource(show_spinner="Preparando o banco de dados...")
def inicializar_banco(versao=None):
    """Backup diário (SQLite), criação de tabelas novas e migrações aditivas.

    versao: assinatura de versao_esquema(); só serve para invalidar o cache quando o esquema muda.
    """
    try:
        backup_sqlite_automatico()
    except Exception as exc:
        print(f"[AVISO] Backup automático não concluído: {exc}")
    # Cria somente tabelas inexistentes (ex.: links_familiares, log_auditoria).
    Base.metadata.create_all(engine)
    aplicar_migracoes_aditivas()
    criar_usuario_admin_padrao()
    return True


# --------------------------- UTILITÁRIOS ---------------------
def limpar_cpf(cpf):
    return re.sub(r"\D", "", str(cpf or ""))


SENHA_PADRAO_ADMIN = "admin123"
PBKDF2_ITERACOES = 390_000
PREFIXO_HASH = "pbkdf2_sha256$"
CHAVES_SESSAO = ("usuario_id", "usuario_logado", "perfil_usuario", "trocar_senha_obrigatoria",
                 "menu_principal", "folha_aberta", "aviso_folha_concluida")


def gerar_hash_senha(senha):
    """PBKDF2-SHA256 com sal aleatório (biblioteca padrão, sem dependências novas)."""
    sal = secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", str(senha).encode("utf-8"), sal, PBKDF2_ITERACOES)
    return f"{PREFIXO_HASH}{PBKDF2_ITERACOES}${sal.hex()}${derivada.hex()}"


def hash_precisa_atualizar(senha_hash):
    """Hashes SHA-256 da versão anterior são convertidos automaticamente no próximo login."""
    return not str(senha_hash or "").startswith(PREFIXO_HASH)


def verificar_senha(senha, senha_hash):
    senha_hash = str(senha_hash or "")
    senha_bytes = str(senha or "").encode("utf-8")
    if senha_hash.startswith(PREFIXO_HASH):
        try:
            _, iteracoes, sal_hex, esperado = senha_hash.split("$", 3)
            derivada = hashlib.pbkdf2_hmac("sha256", senha_bytes, bytes.fromhex(sal_hex), int(iteracoes))
        except (ValueError, TypeError):
            return False
        return secrets.compare_digest(derivada.hex(), esperado)
    # Compatibilidade com os hashes SHA-256 legados (sem sal).
    return secrets.compare_digest(hashlib.sha256(senha_bytes).hexdigest(), senha_hash)


def criar_usuario_admin_padrao():
    db = SessionLocal()
    try:
        if db.query(Usuario).count() == 0:
            db.add(Usuario(
                nome="Administrador Espaço Dinâmico",
                cpf="00000000000",
                senha_hash=gerar_hash_senha(SENHA_PADRAO_ADMIN),
                perfil="Admin",
                ativo=1,
            ))
            db.commit()
    finally:
        db.close()


MAX_FALHAS_LOGIN = 5
JANELA_BLOQUEIO_MIN = 10


def referencia_cpf(cpf_limpo):
    """Identificador do CPF para o log sem gravar o CPF em claro (LGPD)."""
    return hash_token(f"login:{cpf_limpo}")[:16]


def detalhe_falha_login(cpf_limpo):
    if not cpf_limpo:
        return "CPF vazio"
    return f"CPF final {cpf_limpo[-3:]}; ref={referencia_cpf(cpf_limpo)}"


def cpf_bloqueado(db, cpf_limpo):
    """Bloqueia o CPF após MAX_FALHAS_LOGIN falhas na janela, contando no log de auditoria.

    O bloqueio por session_state sozinho era zerado ao recarregar o navegador.
    """
    if not cpf_limpo:
        return False
    inicio = datetime.now() - timedelta(minutes=JANELA_BLOQUEIO_MIN)
    try:
        falhas = db.query(func.count(LogAuditoria.id)).filter(
            LogAuditoria.acao == "login_falhou",
            LogAuditoria.data_hora >= inicio,
            LogAuditoria.detalhe.like(f"%ref={referencia_cpf(cpf_limpo)}%"),
        ).scalar() or 0
    except SQLAlchemyError as exc:
        db.rollback()
        print(f"[AVISO] Verificação de bloqueio de login falhou: {exc}")
        return False
    return falhas >= MAX_FALHAS_LOGIN


def encerrar_sessao():
    for chave in CHAVES_SESSAO:
        st.session_state.pop(chave, None)


def registrar_auditoria(acao, detalhe="", usuario=None):
    """Grava um evento em sessão própria; falha de auditoria nunca derruba a tela."""
    sessao = SessionLocal()
    try:
        sessao.add(LogAuditoria(
            data_hora=datetime.now(), acao=str(acao)[:80], detalhe=str(detalhe or ""),
            usuario=(usuario or st.session_state.get("usuario_logado") or "-")[:100],
        ))
        sessao.commit()
    except Exception as exc:
        sessao.rollback()
        print(f"[AVISO] Auditoria não registrada ({acao}): {exc}")
    finally:
        sessao.close()


# --------------------------- CONFIGURAÇÕES -------------------
def config_padrao():
    return {
        "nome_instituicao": "Espaço Dinâmico",
        "profissional_responsavel": "Larissa Lyrio",
        "titulo_profissional": "Neuropsicopedagoga",
        "app_url": os.getenv("APP_URL", ""),
        # Usados nos recibos (opcionais).
        "documento_profissional": "",
        "cidade": "",
        # Serviços oferecidos (um por linha): lista suspensa em Contratos e Financeiro.
        "servicos": "Intervenção Pedagógica\nIntervenção Neuropsicopedagógica",
    }


def lista_servicos(cfg):
    """Serviços cadastrados em Configurações (um por linha), sem repetição."""
    itens = []
    for linha in str(cfg.get("servicos") or "").splitlines():
        linha = linha.strip()
        if linha and linha not in itens:
            itens.append(linha)
    return itens or ["Intervenção Pedagógica", "Intervenção Neuropsicopedagógica"]


def opcoes_com_atual(opcoes, atual):
    """Inclui o valor já gravado (ex.: texto antigo) para não perdê-lo ao editar."""
    atual = (atual or "").strip()
    return opcoes + [atual] if atual and atual not in opcoes else list(opcoes)


def carregar_configuracoes(db):
    valores = config_padrao()
    itens = db.query(ConfiguracaoSistema).filter(ConfiguracaoSistema.chave.in_(list(valores))).all()
    for item in itens:
        if item.valor:
            valores[item.chave] = item.valor
    return valores


# --------------------------- PERMISSÕES ----------------------
MENU_PAGINAS = [
    "📊 Painel", "👥 Alunos e responsáveis", "📄 Contratos",
    "📂 Prontuários", "📁 Atividades", "✍️ Atividade com caneta", "📓 Caderno Digital",
    "💰 Financeiro", "📈 Desempenho", "👤 Usuários", "⚙️ Configurações",
]

# Ajuste aqui quem vê cada tela. Prontuários e documentos clínicos são
# dados sensíveis (LGPD): o perfil Financeiro não tem acesso a eles.
PERMISSOES = {
    "Admin": set(MENU_PAGINAS),
    "Profissional": {
        "📊 Painel", "👥 Alunos e responsáveis", "📂 Prontuários", "📁 Atividades",
        "✍️ Atividade com caneta", "📓 Caderno Digital", "📈 Desempenho",
    },
    "Financeiro": {
        "📊 Painel", "👥 Alunos e responsáveis", "📄 Contratos", "💰 Financeiro",
    },
}


# --------------------------- ATIVIDADES ----------------------
STATUS_CONCLUIDOS = ("Realizada", "Cancelada")


def normalizar_status_atividade(status):
    """Registros antigos usavam 'Realizado' (padrão do modelo); a tela usa 'Realizada'."""
    return "Realizada" if status == "Realizado" else (status or "Planejada")


# --------------------------- LINK DA FAMÍLIA -----------------
def hash_token(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


SECOES_PORTAL = {"ver_caderno": "📓 Caderno Digital", "ver_desempenho": "📈 Desempenho",
                 "ver_atividades": "📁 Atividades"}


def secoes_do_link(link):
    return [rot for campo, rot in SECOES_PORTAL.items() if getattr(link, campo, 1)]


def gerar_link_familiar(db, aluno_id, dias_validade, criado_por, revogar_anteriores=True, secoes=None):
    """Gera token aleatório; no banco fica apenas o hash (o link não pode ser lido do banco).

    secoes: dict {"ver_caderno": bool, ...}; ausente = família vê todas as seções.
    """
    secoes = secoes or {}
    token = secrets.token_urlsafe(32)
    if revogar_anteriores:
        db.query(LinkFamiliar).filter_by(aluno_id=aluno_id, ativo=1).update({"ativo": 0})
    db.add(LinkFamiliar(
        aluno_id=aluno_id, token_hash=hash_token(token), criado_em=datetime.now(),
        expira_em=date.today() + timedelta(days=int(dias_validade)), ativo=1,
        criado_por=criado_por, acessos=0,
        **{campo: 1 if secoes.get(campo, True) else 0 for campo in SECOES_PORTAL},
    ))
    db.commit()
    return token


def validar_token_portal(db, token):
    token = str(token or "").strip()
    if not token or len(token) > 200:
        return None
    link = db.query(LinkFamiliar).filter_by(token_hash=hash_token(token), ativo=1).first()
    if not link or not link.expira_em or link.expira_em < date.today():
        return None
    if not link.aluno or not link.aluno.ativo:
        return None
    return link


def montar_url_portal(app_url, token):
    base = str(app_url or "").strip().rstrip("/")
    return f"{base}/?portal={token}" if base else f"?portal={token}"


def detectar_url_base():
    """Endereço (esquema + domínio) pelo qual o sistema foi aberto no navegador."""
    try:
        url = getattr(st.context, "url", None)
        if url:
            partes = urllib.parse.urlsplit(url)
            if partes.scheme and partes.netloc:
                return f"{partes.scheme}://{partes.netloc}"
    except Exception:
        pass
    try:
        host = st.context.headers.get("Host") or ""
        if host:
            esquema = "http" if eh_endereco_local(host) else "https"
            return f"{esquema}://{host}"
    except Exception:
        pass
    return ""


def eh_endereco_local(url):
    texto = str(url or "").lower()
    return any(h in texto for h in ("localhost", "127.0.0.1", "0.0.0.0", "192.168.", "10.0."))


def link_whatsapp(telefone, texto):
    digitos = re.sub(r"\D", "", str(telefone or ""))
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    if len(digitos) < 12:
        return None
    return f"https://wa.me/{digitos}?text={urllib.parse.quote(texto)}"


def formatar_data_hora(valor):
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    return para_str_br(valor)


# --------------------------- FINANCEIRO ----------------------
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def resumo_financeiro(db, referencia=None):
    hoje = referencia or date.today()
    inicio = hoje.replace(day=1)
    fim = date(hoje.year, hoje.month, calendar.monthrange(hoje.year, hoje.month)[1])
    L = LancamentoFinanceiro

    def soma(*filtros):
        valor = db.query(func.coalesce(func.sum(L.valor), 0)).filter(*filtros).scalar()
        return float(valor or 0)

    atraso = (L.tipo == "Receita", L.status == "Pendente", L.data_vencimento < hoje)
    recebido = soma(L.tipo == "Receita", L.status == "Pago", L.data_pagamento.between(inicio, fim))
    despesas = soma(L.tipo == "Despesa", L.status == "Pago", L.data_pagamento.between(inicio, fim))
    return {
        "a_receber": soma(L.tipo == "Receita", L.status == "Pendente", L.data_vencimento >= hoje),
        "em_atraso": soma(*atraso),
        "qtd_atraso": db.query(func.count(L.id)).filter(*atraso).scalar() or 0,
        "recebido_mes": recebido,
        "despesas_mes": despesas,
        "saldo_mes": recebido - despesas,
    }


# --------------------------- RECIBOS -------------------------
_UNIDADES = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
             "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
_DEZENAS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CENTENAS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
             "seiscentos", "setecentos", "oitocentos", "novecentos"]


def _extenso_ate_999(n):
    if n == 100:
        return "cem"
    centena, resto = divmod(n, 100)
    partes = [_CENTENAS[centena]] if centena else []
    if resto:
        if resto < 20:
            partes.append(_UNIDADES[resto])
        else:
            dezena, unidade = divmod(resto, 10)
            partes.append(_DEZENAS[dezena] + (f" e {_UNIDADES[unidade]}" if unidade else ""))
    return " e ".join(partes)


def extenso_inteiro(n):
    n = int(n)
    if n == 0:
        return "zero"
    milhoes, resto = divmod(n, 1_000_000)
    milhares, unidades = divmod(resto, 1000)
    grupos = []
    if milhoes:
        grupos.append("um milhão" if milhoes == 1 else f"{_extenso_ate_999(milhoes)} milhões")
    if milhares:
        grupos.append("mil" if milhares == 1 else f"{_extenso_ate_999(milhares)} mil")
    if unidades:
        # Regra do português: "mil e cinquenta", "mil e trezentos", mas "mil trezentos e dez".
        ultimo = _extenso_ate_999(unidades)
        if grupos and (unidades < 100 or unidades % 100 == 0):
            return " ".join(grupos) + " e " + ultimo
        grupos.append(ultimo)
    return " ".join(grupos)


def valor_por_extenso(valor):
    total_centavos = int(round(float(valor or 0) * 100))
    reais, centavos = divmod(total_centavos, 100)
    partes = []
    if reais:
        sufixo = "real" if reais == 1 else "reais"
        if reais >= 1_000_000 and reais % 1_000_000 == 0:
            sufixo = "de reais"
        partes.append(f"{extenso_inteiro(reais)} {sufixo}")
    if centavos:
        partes.append(f"{extenso_inteiro(centavos)} {'centavo' if centavos == 1 else 'centavos'}")
    return " e ".join(partes) if partes else "zero real"


def data_por_extenso(d):
    return f"{d.day} de {MESES[d.month - 1].lower()} de {d.year}"


def gerar_recibo_pdf(lanc, cfg, logo=None):
    """Recibo em PDF (A4) de um lançamento de Receita já pago."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors

    esc = lambda v: html.escape(str(v or ""))
    aluno = lanc.aluno
    responsavel = aluno.responsavel if aluno else None
    pagador = responsavel.nome if responsavel else (aluno.nome if aluno else "—")
    data_pag = lanc.data_pagamento or date.today()
    numero = f"{lanc.id:06d}"

    base = ParagraphStyle("base", fontName="Helvetica", fontSize=11.5, leading=17, textColor=colors.HexColor("#172b4d"))
    titulo = ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24, alignment=TA_CENTER)
    centro = ParagraphStyle("centro", parent=base, alignment=TA_CENTER, fontSize=10, textColor=colors.HexColor("#64748b"))
    corpo = ParagraphStyle("corpo", parent=base, alignment=TA_JUSTIFY, fontSize=12.5, leading=21)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=f"Recibo {numero}", author=cfg["nome_instituicao"])
    elementos = []
    if logo and os.path.isfile(logo):
        try:
            elementos += [Image(logo, width=2.6 * cm, height=2.6 * cm, kind="proportional"), Spacer(1, 6)]
        except Exception as exc:
            print(f"[AVISO] Logo não incluída no recibo: {exc}")
    elementos.append(Paragraph(esc(cfg["nome_instituicao"]), ParagraphStyle("inst", parent=titulo, fontSize=15)))
    linha_prof = f"{esc(cfg['profissional_responsavel'])} · {esc(cfg['titulo_profissional'])}"
    if cfg.get("documento_profissional"):
        linha_prof += f" · {esc(cfg['documento_profissional'])}"
    elementos += [Paragraph(linha_prof, centro), Spacer(1, 22)]

    cabecalho_tab = Table([[Paragraph(f"<b>RECIBO Nº {numero}</b>", ParagraphStyle("n", parent=base, fontSize=14)),
                            Paragraph(f"<b>{esc(moeda(lanc.valor))}</b>",
                                      ParagraphStyle("v", parent=base, fontSize=14, alignment=2))]],
                          colWidths=["60%", "40%"])
    cabecalho_tab.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#087e8b")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e8f7f6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    elementos += [cabecalho_tab, Spacer(1, 24)]

    referente = esc(lanc.descricao)
    if aluno:
        referente += f", do(a) aluno(a) <b>{esc(aluno.nome)}</b>"
    texto = (f"Recebi de <b>{esc(pagador)}</b> a importância de <b>{esc(moeda(lanc.valor))}</b> "
             f"({esc(valor_por_extenso(lanc.valor))}), referente a {referente}, "
             f"paga em {esc(para_str_br(data_pag))}.")
    elementos += [Paragraph(texto, corpo), Spacer(1, 10),
                  Paragraph("Para clareza, firmo o presente recibo, dando plena quitação do valor acima.", corpo),
                  Spacer(1, 34)]
    local = f"{esc(cfg['cidade'])}, " if cfg.get("cidade") else ""
    elementos += [Paragraph(f"{local}{esc(data_por_extenso(data_pag))}.", base), Spacer(1, 64)]

    assinatura = Table([[""], [Paragraph(f"<b>{esc(cfg['profissional_responsavel'])}</b><br/>{esc(cfg['titulo_profissional'])}",
                                         ParagraphStyle("ass", parent=base, alignment=TA_CENTER, fontSize=10.5, leading=14))]],
                       colWidths=[9 * cm])
    assinatura.setStyle(TableStyle([("LINEABOVE", (0, 1), (0, 1), 0.8, colors.HexColor("#172b4d")),
                                    ("TOPPADDING", (0, 1), (0, 1), 6)]))
    elementos.append(assinatura)
    elementos += [Spacer(1, 40), Paragraph(f"Documento gerado pelo sistema em {datetime.now():%d/%m/%Y %H:%M}.", centro)]
    doc.build(elementos)
    return buffer.getvalue()


def dre_do_mes(db, ano, mes):
    """Mini DRE pelo regime de caixa: o que foi efetivamente PAGO dentro do mês, por categoria."""
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
    L = LancamentoFinanceiro
    # Agrupa pela coluna pura: no PostgreSQL, COALESCE(categoria, 'Geral') no SELECT e no GROUP BY vira
    # dois parâmetros diferentes e dá GroupingError (o SQLite aceitava). Categoria vazia vira "Geral" aqui.
    linhas = (db.query(L.tipo, L.categoria, func.coalesce(func.sum(L.valor), 0))
              .filter(L.status == "Pago", L.data_pagamento.between(inicio, fim))
              .group_by(L.tipo, L.categoria).all())
    somas = {}
    for tipo, categoria, valor in linhas:
        chave = (tipo, (categoria or "").strip() or "Geral")
        somas[chave] = somas.get(chave, 0.0) + float(valor or 0)
    receitas = sorted(((c, v) for (t, c), v in somas.items() if t == "Receita"), key=lambda x: -x[1])
    despesas = sorted(((c, v) for (t, c), v in somas.items() if t == "Despesa"), key=lambda x: -x[1])
    total_r = sum(v for _, v in receitas)
    total_d = sum(v for _, v in despesas)
    return {"receitas": receitas, "despesas": despesas, "receita": total_r, "despesa": total_d,
            "resultado": total_r - total_d, "margem": ((total_r - total_d) / total_r * 100) if total_r else None}


def html_mini_dre(dre, titulo):
    """Cartão do mini DRE (Receita, (−) Despesa, (=) Resultado) com o detalhe por categoria."""
    esc = html.escape

    def detalhe(itens):
        return "".join(f'<tr class="det"><td>{esc(c)}</td><td>{esc(moeda(v))}</td></tr>' for c, v in itens)

    resultado = dre["resultado"]
    classe = "pos" if resultado > 0 else "neg" if resultado < 0 else ""
    margem = (f'<div class="ed-dre-margem">Margem do mês: <b>{dre["margem"]:.1f}%</b></div>'.replace(".", ",")
              if dre["margem"] is not None else "")
    return f'''<div class="ed-dre">
      <div class="ed-dre-titulo">{esc(titulo)}</div>
      <table>
        <tr class="grupo"><td>RECEITA</td><td>{esc(moeda(dre["receita"]))}</td></tr>{detalhe(dre["receitas"])}
        <tr class="grupo menos"><td>(−) DESPESA</td><td>{esc(moeda(dre["despesa"]))}</td></tr>{detalhe(dre["despesas"])}
        <tr class="total {classe}"><td>(=) RESULTADO</td><td>{esc(moeda(resultado))}</td></tr>
      </table>{margem}
      <div class="ed-dre-nota">Regime de caixa: lançamentos com situação <b>Pago</b> e data de pagamento no mês.</div>
    </div>'''


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


def obter_config_storage():
    """Lê credenciais privadas do Supabase exclusivamente no servidor."""
    try:
        cfg = st.secrets.get("supabase", {})
    except Exception:
        cfg = {}
    # "or" (e não o padrão do get): campo presente mas vazio no secrets.toml cai para a variável de ambiente.
    url = str(cfg.get("url") or os.getenv("SUPABASE_URL", "")).strip().strip('"').rstrip("/")
    # Aceita a URL colada com sufixo da API (ex.: .../rest/v1 ou .../storage/v1).
    url = re.sub(r"/(rest|storage|auth)/v1.*$", "", url)
    chave = str(cfg.get("service_role_key") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")).strip().strip('"')
    bucket = str(cfg.get("bucket") or "documentos-clinicos").strip()
    if not url or not chave:
        return None
    return {"url": url, "key": chave, "bucket": bucket}


def tipo_chave_supabase(chave):
    """Classifica a chave SEM expô-la: 'jwt' (legada), 'secret', 'publishable' ou 'desconhecida'."""
    if chave.startswith("sb_secret_"):
        return "secret"
    if chave.startswith("sb_publishable_"):
        return "publishable"
    if chave.startswith("eyJ") and chave.count(".") == 2:
        try:
            import base64
            carga = chave.split(".")[1]
            dados = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
            return "jwt_" + str(dados.get("role", "?"))  # jwt_service_role / jwt_anon
        except Exception:
            return "jwt_?"
    return "desconhecida"


def requisicao_storage(metodo, endpoint, payload=None, content_type="application/json"):
    cfg = obter_config_storage()
    if not cfg:
        raise RuntimeError("Storage não configurado. Configure [supabase] nos Secrets do Streamlit.")
    url = f"{cfg['url']}/storage/v1/{endpoint.lstrip('/')}"
    corpo = payload
    if isinstance(payload, dict):
        corpo = json.dumps(payload).encode("utf-8")
    headers = {"apikey": cfg["key"], "Content-Type": content_type}
    # Chave legada (JWT) vai também no Authorization. As chaves novas (sb_secret_) não são JWT:
    # no Authorization o Storage responde "Invalid Compact JWS"; o gateway usa só o apikey.
    if tipo_chave_supabase(cfg["key"]).startswith("jwt"):
        headers["Authorization"] = f"Bearer {cfg['key']}"
    req = urllib.request.Request(url, data=corpo, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=60) as resposta:
            bruto = resposta.read()
            try:
                return json.loads(bruto.decode("utf-8")) if bruto else {}
            except ValueError as exc:
                # Resposta em HTML: a URL não é a da API do projeto (ex.: link do painel).
                raise RuntimeError("RESPOSTA_NAO_JSON: a URL não parece ser a do projeto Supabase") from exc
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Supabase Storage retornou HTTP {exc.code}: {detalhe}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha de comunicação com Supabase Storage: {exc.reason}") from exc


LIMITE_PDF_BYTES = 20 * 1024 * 1024


def descrever_chave_invalida(chave):
    """Diz o que há de errado com a chave usando só características dela (nunca o valor)."""
    onde = (" Pegue a chave certa em Supabase → Project Settings → API Keys: aba 'API Keys' → Secret key "
            "(sb_secret_…, clique em Reveal) ou aba 'Legacy API Keys' → service_role (eyJ…).")
    if chave.lower().startswith("bearer"):
        return "Tire a palavra 'Bearer' do início da chave nos Secrets." + onde
    if re.search(r"\s", chave):
        return "A chave tem espaço ou quebra de linha no meio: cole-a numa linha só, entre aspas." + onde
    if chave.startswith("eyJ"):
        return (f"A chave parece cortada ({chave.count('.') + 1} parte(s) de 3; {len(chave)} caracteres). "
                "Copie-a inteira com o botão de copiar do Supabase." + onde)
    if chave.startswith("sb_"):
        return "A chave começa com sb_ mas não é sb_secret_. Use a Secret key." + onde
    return (f"A chave cadastrada ({len(chave)} caracteres) não é uma chave de API do Supabase. "
            "Não use o 'JWT Secret' nem a senha do banco." + onde)


def explicar_falha_storage(texto, cfg):
    """Mensagem útil para o usuário a partir do erro técnico (o detalhe vai só para o log)."""
    print(f"[AVISO] Diagnóstico do Storage: {texto[:500]}")
    tipo = tipo_chave_supabase(cfg["key"])
    url_ok = bool(re.fullmatch(r"https://[a-z0-9]{20}\.supabase\.co", cfg["url"]))
    dica_url = "" if url_ok else (f" A URL cadastrada ({cfg['url'][:60]}) não está no formato "
                                  "https://SEU-PROJETO.supabase.co.")
    if "RESPOSTA_NAO_JSON" in texto or ("Falha de comunicação" in texto and not url_ok):
        return "A URL do Supabase está errada: use a Project URL (https://SEU-PROJETO.supabase.co), não o link do painel." + dica_url
    if "Falha de comunicação" in texto:
        return "Não foi possível alcançar o Supabase (rede ou projeto pausado). Confira se o projeto está ativo no painel."
    if tipo == "publishable" or tipo == "jwt_anon":
        return ("A chave cadastrada é a chave PÚBLICA (anon/publishable). Use a chave secreta: "
                "service_role (começa com eyJ…) ou secret (começa com sb_secret_…).")
    if tipo == "desconhecida" or tipo == "jwt_?":
        return descrever_chave_invalida(cfg["key"]) + dica_url
    if "HTTP 400" in texto or "HTTP 401" in texto or "HTTP 403" in texto:
        return ("O Supabase recusou a chave (formato reconhecido: "
                f"{'secret' if tipo == 'secret' else 'service_role'}). Confira se ela é do MESMO projeto da URL "
                "e se não foi revogada." + dica_url)
    return "O Supabase respondeu com erro. Tente de novo em instantes." + dica_url


def diagnosticar_storage():
    """Confere credenciais e bucket. Retorna (situacao, mensagem).

    situacao: "sem_config", "erro", "sem_bucket", "publico" ou "ok".
    """
    cfg = obter_config_storage()
    if not cfg:
        return "sem_config", "Credenciais [supabase] não encontradas nos Secrets."
    try:
        buckets = requisicao_storage("GET", "bucket")
    except RuntimeError as exc:
        return "erro", explicar_falha_storage(str(exc), cfg)
    if not isinstance(buckets, list):
        return "erro", "Resposta inesperada do Supabase. Confira se a URL é https://SEU-PROJETO.supabase.co."
    bucket = next((b for b in buckets or [] if b.get("id") == cfg["bucket"] or b.get("name") == cfg["bucket"]), None)
    if not bucket:
        return "sem_bucket", f"Conexão OK, mas o bucket '{cfg['bucket']}' ainda não existe."
    if bucket.get("public"):
        return "publico", (f"O bucket '{cfg['bucket']}' está PÚBLICO: qualquer pessoa com o endereço abre os PDFs. "
                           "No Supabase, edite o bucket e desmarque 'Public bucket'.")
    return "ok", f"Armazenamento pronto: bucket privado '{cfg['bucket']}'."


def criar_bucket_privado():
    """Cria o bucket PRIVADO, aceitando só PDF até 20 MB."""
    cfg = obter_config_storage()
    return requisicao_storage("POST", "bucket", {
        "id": cfg["bucket"], "name": cfg["bucket"], "public": False,
        "file_size_limit": LIMITE_PDF_BYTES, "allowed_mime_types": ["application/pdf"],
    })


def enviar_pdf_storage(caminho, conteudo):
    cfg = obter_config_storage()
    if not cfg:
        raise RuntimeError("Configure as credenciais do Supabase Storage antes de importar documentos.")
    endpoint = f"object/{urllib.parse.quote(cfg['bucket'], safe='')}/{urllib.parse.quote(caminho, safe='/')}"
    return requisicao_storage("POST", endpoint, conteudo, "application/pdf")


def gerar_link_pdf(caminho, validade_segundos=600):
    cfg = obter_config_storage()
    if not cfg:
        raise RuntimeError("Storage não configurado.")
    endpoint = f"object/sign/{urllib.parse.quote(cfg['bucket'], safe='')}/{urllib.parse.quote(caminho, safe='/')}"
    resposta = requisicao_storage("POST", endpoint, {"expiresIn": int(validade_segundos)})
    link = resposta.get("signedURL") or resposta.get("signedUrl")
    if not link:
        raise RuntimeError("O Supabase não retornou o link temporário do documento.")
    if link.startswith("http://") or link.startswith("https://"):
        return link
    return f"{cfg['url']}/storage/v1{link if link.startswith('/') else '/' + link}"


def excluir_objeto_storage(caminho):
    cfg = obter_config_storage()
    if not cfg:
        return
    endpoint = f"object/{urllib.parse.quote(cfg['bucket'], safe='')}"
    requisicao_storage("DELETE", endpoint, {"prefixes": [caminho]})


# --------------------------- MATERIAIS EM PDF ----------------
TIPOS_MATERIAL = ["Atividade", "Material escolar", "Avaliação"]
LIMITE_TEXTO_EXTRAIDO = 200_000  # caracteres guardados para a busca


def validar_pdf(conteudo):
    """Retorna None se o PDF é aceitável; senão, a mensagem de erro para o usuário."""
    if not conteudo:
        return "arquivo vazio"
    if len(conteudo) > LIMITE_PDF_BYTES:
        return "excede o limite de 20 MB"
    if not conteudo.startswith(b"%PDF-"):
        return "não é um PDF válido"
    return None


def extrair_info_pdf(conteudo, max_paginas=60):
    """Conta páginas e extrai texto para a busca. Falha de leitura não impede a importação."""
    from io import BytesIO
    try:
        from pypdf import PdfReader
        leitor = PdfReader(BytesIO(conteudo))
        if leitor.is_encrypted and not leitor.decrypt(""):
            return None, ""  # PDF protegido por senha: guarda o arquivo, sem texto
        paginas = len(leitor.pages)
        partes = []
        for pagina in leitor.pages[:max_paginas]:
            try:
                partes.append(pagina.extract_text() or "")
            except Exception:
                continue
        # O PostgreSQL recusa o caractere nulo (\x00) em colunas TEXT.
        texto = re.sub(r"[ \t]+", " ", "\n".join(partes).replace("\x00", "")).strip()
        return paginas, texto[:LIMITE_TEXTO_EXTRAIDO]
    except Exception as exc:
        print(f"[AVISO] Não foi possível ler o conteúdo do PDF: {exc}")
        return None, ""


def titulo_pelo_arquivo(nome_arquivo):
    """'Atividade_fracoes-3ano.pdf' -> 'Atividade fracoes 3ano'."""
    base = Path(str(nome_arquivo or "")).stem
    return re.sub(r"[_\-]+", " ", base).strip()[:180] or "Material sem título"


def importar_material_pdf(db, conteudo, nome_arquivo, dados, usuario_nome):
    """Valida, envia ao Storage e registra UM PDF. Retorna (material, aviso).

    Se a gravação no banco falhar depois do envio, o arquivo é apagado do Storage
    para não deixar órfãos. Duplicados (mesmo conteúdo e mesmo aluno) são ignorados.
    """
    erro = validar_pdf(conteudo)
    if erro:
        return None, f"{nome_arquivo}: {erro}."
    digest = hashlib.sha256(conteudo).hexdigest()
    aluno_id = dados.get("aluno_id")
    duplicado = (db.query(MaterialPedagogico)
                 .filter_by(sha256=digest, aluno_id=aluno_id, status="Ativo").first())
    if duplicado:
        return None, f"{nome_arquivo}: já importado como “{duplicado.titulo}” (#{duplicado.id})."
    paginas, texto = extrair_info_pdf(conteudo)
    pasta = f"aluno_{aluno_id}" if aluno_id else "acervo_geral"
    caminho = f"materiais/{pasta}/{uuid.uuid4().hex}.pdf"
    titulo = (dados.get("titulo") or "").strip() or titulo_pelo_arquivo(nome_arquivo)

    enviar_pdf_storage(caminho, conteudo)
    try:
        atividade_id = dados.get("atividade_id")
        if dados.get("criar_atividade") and aluno_id and not atividade_id:
            atividade = AtividadeAluno(
                aluno_id=aluno_id, titulo=titulo[:150], categoria=dados.get("categoria") or "Intervenção",
                area=(dados.get("area") or "").strip(), data_atividade=dados.get("data") or date.today(),
                objetivo=(dados.get("descricao") or "").strip(), status="Planejada",
                descricao=f"{dados.get('tipo', 'Atividade')} em PDF: {Path(nome_arquivo).name}",
            )
            db.add(atividade)
            db.flush()
            atividade_id = atividade.id
        material = MaterialPedagogico(
            titulo=titulo, tipo=dados.get("tipo") or "Atividade", area=(dados.get("area") or "").strip(),
            nivel=(dados.get("nivel") or "").strip(), descricao=(dados.get("descricao") or "").strip(),
            aluno_id=aluno_id, atividade_id=atividade_id, nome_original=Path(nome_arquivo).name[:255],
            caminho_storage=caminho, tamanho_bytes=len(conteudo), paginas=paginas, sha256=digest,
            texto_extraido=texto, status="Ativo", criado_em=datetime.now(), criado_por=usuario_nome,
        )
        db.add(material)
        db.commit()
    except Exception:
        db.rollback()
        try:
            excluir_objeto_storage(caminho)
        except Exception as limpeza_exc:
            print(f"[AVISO] Falha ao limpar arquivo órfão: {limpeza_exc}")
        raise
    aviso = None if texto else f"{nome_arquivo}: importado, mas sem texto pesquisável (PDF escaneado/imagem)."
    return material, aviso


# --------------------------- FOLHAS COM CANETA ---------------
LARGURA_FOLHA_PX = 1100      # resolução da página na tela (≈ 133 dpi em A4)
MAX_PAGINAS_FOLHA = 40

import streamlit.components.v1 as _componentes
_componente_canvas = _componentes.declare_component(
    "caderno_canvas", path=str(BASE_DIR / "componentes" / "caderno_canvas"))


def baixar_pdf_storage(caminho):
    """Baixa um arquivo privado do bucket (credencial só no servidor)."""
    cfg = obter_config_storage()
    if not cfg:
        raise RuntimeError("Storage não configurado.")
    url = (f"{cfg['url']}/storage/v1/object/{urllib.parse.quote(cfg['bucket'], safe='')}/"
           f"{urllib.parse.quote(caminho, safe='/')}")
    headers = {"apikey": cfg["key"]}
    if tipo_chave_supabase(cfg["key"]).startswith("jwt"):
        headers["Authorization"] = f"Bearer {cfg['key']}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resposta:
            return resposta.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Supabase Storage retornou HTTP {exc.code} ao baixar o arquivo") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha de comunicação com Supabase Storage: {exc.reason}") from exc


@st.cache_data(ttl=3600, max_entries=16, show_spinner=False)
def pdf_do_material(caminho, sha256):
    """PDF original do material (o sha256 na chave invalida o cache se o arquivo mudar)."""
    return baixar_pdf_storage(caminho)


def contar_paginas_pdf(conteudo):
    import pypdfium2 as pdfium
    documento = pdfium.PdfDocument(conteudo)
    try:
        return len(documento)
    finally:
        documento.close()


@st.cache_data(ttl=3600, max_entries=120, show_spinner=False)
def imagem_pagina(caminho, sha256, pagina, largura=LARGURA_FOLHA_PX):
    """Renderiza a página (1..n) como JPEG. Retorna (bytes_jpeg, largura, altura)."""
    import pypdfium2 as pdfium
    from io import BytesIO
    documento = pdfium.PdfDocument(pdf_do_material(caminho, sha256))
    try:
        pag = documento[pagina - 1]
        largura_pt, _ = pag.get_size()
        imagem = pag.render(scale=largura / largura_pt).to_pil().convert("RGB")
    finally:
        documento.close()
    buffer = BytesIO()
    imagem.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue(), imagem.width, imagem.height


def data_url(conteudo, mime):
    import base64
    return f"data:{mime};base64," + base64.b64encode(conteudo).decode("ascii")


def png_de_data_url(valor):
    """Valida e decodifica o PNG enviado pelo componente (nunca confia no navegador)."""
    import base64
    prefixo = "data:image/png;base64,"
    if not isinstance(valor, str) or not valor.startswith(prefixo):
        return None
    bruto = base64.b64decode(valor[len(prefixo):], validate=True)
    if not bruto.startswith(b"\x89PNG\r\n\x1a\n") or len(bruto) > 8 * 1024 * 1024:
        return None
    return bruto


def salvar_tinta_pagina(db, folha, pagina, png_bytes):
    """Grava (ou apaga, se vazia) a tinta da página. png_bytes=None significa página limpa."""
    import base64
    registro = db.query(FolhaPagina).filter_by(folha_id=folha.id, pagina=pagina).first()
    if registro is None:
        registro = FolhaPagina(folha_id=folha.id, pagina=pagina)
        db.add(registro)
    registro.tinta_png = base64.b64encode(png_bytes).decode("ascii") if png_bytes else None
    registro.atualizado_em = datetime.now()
    folha.atualizado_em = datetime.now()
    db.commit()


def gerar_pdf_folha(db, folha):
    """PDF final: cada página do original com a escrita do aluno por cima."""
    import base64
    from io import BytesIO
    from PIL import Image
    tintas = {p.pagina: p.tinta_png for p in db.query(FolhaPagina).filter_by(folha_id=folha.id).all()}
    paginas = []
    for n in range(1, folha.total_paginas + 1):
        jpeg, _, _ = imagem_pagina(folha.material.caminho_storage, folha.material.sha256, n)
        fundo = Image.open(BytesIO(jpeg)).convert("RGBA")
        if tintas.get(n):
            tinta = Image.open(BytesIO(base64.b64decode(tintas[n]))).convert("RGBA")
            if tinta.size != fundo.size:
                tinta = tinta.resize(fundo.size)
            fundo = Image.alpha_composite(fundo, tinta)
        paginas.append(fundo.convert("RGB"))
    import pypdfium2 as pdfium
    original = pdfium.PdfDocument(pdf_do_material(folha.material.caminho_storage, folha.material.sha256))
    try:
        largura_pt = original[0].get_size()[0]
    finally:
        original.close()
    # DPI que faz a página final ter o mesmo tamanho físico do original.
    dpi = LARGURA_FOLHA_PX / (largura_pt / 72.0)
    saida = BytesIO()
    paginas[0].save(saida, format="PDF", save_all=True, append_images=paginas[1:], resolution=dpi)
    return saida.getvalue()


def formatar_tamanho(bytes_total):
    valor = float(bytes_total or 0)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidade == "GB":
            return f"{valor:.1f} {unidade}"
        valor /= 1024
    return f"{valor:.1f} GB"


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
        padding-left: 2rem !important; padding-right: 2rem !important;  /* mais área útil na tela */
      }
      @media (max-width: 700px) { .block-container { padding-left: 1rem !important; padding-right: 1rem !important; } }
      /* CABEÇALHO FIXO: o sticky precisa ficar no container do elemento (filho direto do bloco
         que rola). No wrapper interno (stMarkdown) não funcionava e a logo sumia ao rolar. */
      div[data-testid="stElementContainer"]:has(.ed-header), div.element-container:has(.ed-header) {
        position: sticky; top: 3.6rem; z-index: 999; background: #f4f7fb;
        padding: .2rem 0 .35rem 0; margin-top: -.2rem;
      }
      .ed-header { position:relative; display:flex; align-items:center; gap:16px; width:100%; min-height:70px; padding:9px 18px; margin:0; box-sizing:border-box; background:linear-gradient(110deg,rgba(255,255,255,.99) 0%,rgba(248,251,255,.99) 100%); border:1px solid #e5ebf3; border-radius:14px; box-shadow:0 6px 18px rgba(20,43,74,.10); }
      .ed-header-logo { flex:0 0 56px; display:flex; align-items:center; justify-content:center; }
      .ed-header-logo img { max-width:52px; max-height:52px; object-fit:contain; }
      .ed-header-title { flex:1 1 auto; min-width:0; }
      .ed-header-title h1 { margin:0 !important; padding:0 !important; color:#142b4a; font-size:clamp(1.2rem,1.9vw,1.55rem); line-height:1.2 !important; font-weight:800; overflow-wrap:anywhere; }
      .ed-header-title p { margin:2px 0 0 0 !important; color:#64748b; font-size:.84rem; line-height:1.3 !important; }
      .ed-profissional { flex:0 0 210px; text-align:right; padding:2px 0 2px 12px; box-sizing:border-box; display:flex; flex-direction:column; justify-content:center; line-height:1.35; border-left:1px solid #e2e8f0; }
      .ed-profissional strong { display:block; color:#142b4a; font-size:.95rem; overflow-wrap:anywhere; }
      .ed-profissional span { color:#64748b; font-size:.82rem; }
      @media (max-width: 900px) { .ed-header { gap:10px; padding:8px 12px; min-height:58px; } .ed-header-logo { flex-basis:44px; } .ed-header-logo img { max-width:42px; max-height:42px; } .ed-header-title p { display:none; } .ed-profissional { display:none; } }
      /* MENU LATERAL MAIS ESTREITO (só quando aberto; recolher continua funcionando). */
      section[data-testid="stSidebar"][data-collapsed="false"] { width:240px !important; min-width:240px !important; max-width:240px !important; }
      [data-testid="stSidebarContent"] { padding-bottom: .5rem; }
      [data-testid="stSidebarHeader"] { padding: .6rem .9rem 0 .9rem !important; height:auto !important; min-height:2.2rem; }
      [data-testid="stSidebarUserContent"] { padding: 0 .9rem 1rem .9rem !important; }
      [data-testid="stSidebar"] h2 { font-size:1.15rem !important; padding:.2rem 0 0 0 !important; }
      [data-testid="stSidebar"] hr { margin: .55rem 0 !important; }
      [data-testid="stSidebar"] [role="radiogroup"] label { padding: .08rem 0 !important; }
      [data-testid="stSidebar"] [role="radiogroup"] p { font-size: .86rem !important; white-space: nowrap; }
      /* MINI DRE */
      .ed-dre { background:#fff; border:1px solid #e4eaf2; border-radius:15px; padding:16px 20px 12px 20px; box-shadow:0 5px 18px rgba(20,43,74,.05); }
      .ed-dre-titulo { font-weight:800; color:#142b4a; font-size:1.02rem; margin-bottom:8px; }
      .ed-dre table { width:100%; border-collapse:collapse; border:0; }
      .ed-dre td { border:0 !important; padding:5px 2px; font-variant-numeric: tabular-nums; }
      .ed-dre td:last-child { text-align:right; white-space:nowrap; }
      .ed-dre tr.grupo td { font-weight:700; color:#142b4a; border-top:1px solid #eef2f7 !important; padding-top:9px; }
      .ed-dre tr.grupo:first-child td { border-top:0 !important; padding-top:4px; }
      .ed-dre tr.menos td:last-child { color:#b45309; }
      .ed-dre tr.det td { color:#64748b; font-size:.88rem; padding:2px 2px 2px 16px; }
      .ed-dre tr.total td { font-weight:800; font-size:1.12rem; color:#142b4a; border-top:2px solid #142b4a !important; padding-top:10px; }
      .ed-dre tr.total.pos td:last-child { color:#15803d; }
      .ed-dre tr.total.neg td:last-child { color:#b91c1c; }
      .ed-dre-margem { margin-top:6px; color:#334155; font-size:.9rem; }
      .ed-dre-nota { margin-top:6px; color:#94a3b8; font-size:.78rem; }
      .ed-dre-anual { background:#fff; border:1px solid #e4eaf2; border-radius:15px; padding:14px 16px; box-shadow:0 5px 18px rgba(20,43,74,.05); }
      .ed-dre-anual .rolagem { overflow-x:auto; }
      .ed-dre-anual table { border-collapse:collapse; width:100%; min-width:1050px; font-size:.82rem; font-variant-numeric:tabular-nums; border:0; }
      .ed-dre-anual th, .ed-dre-anual td { border:0 !important; padding:5px 6px; text-align:right; white-space:nowrap; }
      .ed-dre-anual .cat { text-align:left; position:sticky; left:0; background:#fff; min-width:150px; }
      .ed-dre-anual tr.cab th { color:#64748b; font-weight:600; border-bottom:1px solid #e2e8f0 !important; }
      .ed-dre-anual tr.grupo td { font-weight:800; color:#142b4a; padding-top:12px; }
      .ed-dre-anual td.det { color:#475569; padding-left:16px; }
      .ed-dre-anual tr.subtotal td { font-weight:700; color:#142b4a; border-top:1px solid #e2e8f0 !important; }
      .ed-dre-anual tr.subtotal.menos td { color:#b45309; }
      .ed-dre-anual tr.resultado td { font-weight:800; color:#142b4a; border-top:2px solid #142b4a !important; font-size:.86rem; }
      .ed-dre-anual tr.acum td { color:#64748b; }
      .ed-dre-anual td.tot { font-weight:700; background:#f8fafc; }
      .ed-dre-anual td.neg { color:#b91c1c !important; }
      .stButton > button, .stFormSubmitButton > button { border-radius:9px; font-weight:600; min-height:2.55rem; }
      div[data-testid="stTabs"] button { font-weight:600; }
      [data-testid="stSidebar"] div.st-key-sair_sistema button { background:rgba(255,255,255,.10) !important; color:#fff !important; border:1px solid rgba(255,255,255,.28) !important; }
      [data-testid="stSidebar"] div.st-key-sair_sistema button:hover { background:rgba(255,255,255,.20) !important; border-color:rgba(255,255,255,.55) !important; }
      [data-testid="stSidebar"] div.st-key-sair_sistema button p { color:#fff !important; }
      .ed-note { background:#e8f7f6; border-left:4px solid #20b8b0; padding:12px 15px; border-radius:8px; }
    </style>
    """, unsafe_allow_html=True)


def cabecalho(logo, cfg=None):
    cfg = cfg or config_padrao()
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
      <div class="ed-header-title"><h1>{html.escape(cfg["nome_instituicao"])}</h1><p>Sistema Integrado de Gestão Neuropsicopedagógica</p></div>
      <div class="ed-profissional"><strong>{html.escape(cfg["profissional_responsavel"])}</strong><span>{html.escape(cfg["titulo_profissional"])}</span></div>
    </section>'''
    st.markdown(bloco, unsafe_allow_html=True)


# Cores da logo (peças A, B, C, D), usadas nas barras do gráfico de dificuldades.
PALETA_LOGO = ["#6b9bd2", "#e7776c", "#7cc2b2", "#efdc5c"]  # tons da logo, levemente suavizados


def exibir_grafico_barras_fino(df, categoria, valor, titulo, chave, cores=None, texto=None):
    # Grafico horizontal com rotulos completos.
    # cores: lista de cores aplicada barra a barra (da maior para a menor); texto: coluna do rótulo.
    if df is None or df.empty or categoria not in df.columns or valor not in df.columns:
        st.info("Não há dados suficientes para montar este gráfico.")
        return
    graf = df[[categoria, valor] + ([texto] if texto and texto in df.columns else [])].copy()
    graf[categoria] = graf[categoria].astype(str).str.strip()
    graf[valor] = pd.to_numeric(graf[valor], errors="coerce")
    graf = graf.dropna(subset=[categoria, valor])
    graf = graf[graf[categoria].ne("")].sort_values(valor, ascending=True)
    if graf.empty:
        st.info("Não há dados válidos para montar este gráfico.")
        return
    graf["__rotulo"] = graf[categoria].map(lambda x: "<br>".join(textwrap.wrap(x, width=28, break_long_words=False, break_on_hyphens=False)) or x)
    altura = max(220, min(640, 54 * len(graf) + 75))
    usar_texto = texto if texto and texto in graf.columns else valor
    fig = px.bar(graf, x=valor, y="__rotulo", orientation="h", text=usar_texto,
                 custom_data=[categoria], color_discrete_sequence=["#168b9a"])
    if cores:
        # graf está em ordem crescente (maior barra no topo): a maior recebe a 1ª cor da paleta.
        n = len(graf)
        fig.update_traces(marker_color=[cores[(n - 1 - i) % len(cores)] for i in range(n)])
    fig.update_traces(width=0.48, textposition="outside", cliponaxis=False,
        marker_line_width=0,
        hovertemplate="<b>%{customdata[0]}</b><br>" + valor + ": %{x}<extra></extra>",
        textfont={"size": 12, "color": "#5b6b80"})
    fig.update_layout(title={"text": titulo, "x": 0, "xanchor": "left", "font": {"size": 16, "color": "#142b4a"}},
        height=altura, autosize=True, showlegend=False,
        margin={"l": 18, "r": 55, "t": 62, "b": 24},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        bargap=0.62, font={"family": "Arial, sans-serif", "size": 11, "color": "#334155"},
        xaxis={"title": None, "showgrid": True, "gridcolor": "#e8edf4", "zeroline": False, "rangemode": "tozero", "automargin": True},
        yaxis={"title": None, "showgrid": False, "automargin": True, "tickfont": {"size": 11}},
        hoverlabel={"bgcolor": "#142b4a", "font": {"color": "#ffffff"}})
    st.plotly_chart(fig, width="stretch", key=chave,
                    config={"displayModeBar": False, "responsive": True})


# --------------------------- LOGIN ---------------------------
def renderizar_tela_login(db, logo, cfg):
    aplicar_estilo_global()
    st.markdown("<div style='height:3vh'></div>", unsafe_allow_html=True)
    esquerda, centro, direita = st.columns([1, 1.25, 1])
    with centro:
        if logo:
            _, imgcol, _ = st.columns([1, 1, 1])
            with imgcol:
                st.image(logo, width="stretch")
        st.markdown(f"<h1 style='text-align:center;color:#142b4a'>{html.escape(cfg['nome_instituicao'])}</h1>", unsafe_allow_html=True)
        st.markdown(
            f"<p style='text-align:center;color:#64748b'>{html.escape(cfg['profissional_responsavel'])} · "
            f"{html.escape(cfg['titulo_profissional'])}</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.subheader("🔐 Acesso ao sistema")
            restante = int(st.session_state.get("login_bloqueado_ate", 0) - time.time())
            with st.form("form_login", clear_on_submit=False):
                cpf = st.text_input("CPF", max_chars=14, placeholder="Digite apenas os números")
                senha = st.text_input("Senha", type="password")
                enviar = st.form_submit_button("Entrar", width="stretch", type="primary")
            cpf_limpo = limpar_cpf(cpf) if enviar else ""
            if enviar and restante > 0:
                st.warning(f"Muitas tentativas incorretas. Aguarde {restante} segundos e tente novamente.")
            elif enviar and cpf_bloqueado(db, cpf_limpo):
                # Bloqueio gravado no banco: recarregar a página não zera as tentativas.
                st.warning(f"Muitas tentativas incorretas para este CPF. Aguarde {JANELA_BLOQUEIO_MIN} minutos e tente novamente.")
            elif enviar:
                usuario = db.query(Usuario).filter(Usuario.cpf == cpf_limpo).first()
                if usuario and usuario.ativo == 1 and verificar_senha(senha, usuario.senha_hash):
                    if hash_precisa_atualizar(usuario.senha_hash):
                        try:
                            usuario.senha_hash = gerar_hash_senha(senha)
                            db.commit()
                        except SQLAlchemyError as exc:
                            db.rollback()
                            print(f"[AVISO] Não foi possível atualizar o hash da senha: {exc}")
                    st.session_state.pop("login_tentativas", None)
                    st.session_state.pop("login_bloqueado_ate", None)
                    st.session_state["usuario_id"] = usuario.id
                    st.session_state["usuario_logado"] = usuario.nome
                    st.session_state["perfil_usuario"] = usuario.perfil
                    # Senha padrão ou curta: exige troca antes de liberar o sistema.
                    st.session_state["trocar_senha_obrigatoria"] = (senha == SENHA_PADRAO_ADMIN or len(senha) < 8)
                    registrar_auditoria("login", usuario=usuario.nome)
                    st.rerun()
                else:
                    time.sleep(1)  # desacelera tentativas automáticas
                    tentativas = st.session_state.get("login_tentativas", 0) + 1
                    st.session_state["login_tentativas"] = tentativas
                    registrar_auditoria("login_falhou", detalhe_falha_login(cpf_limpo), usuario="-")
                    if tentativas >= 5:
                        st.session_state["login_bloqueado_ate"] = time.time() + 120
                        st.session_state["login_tentativas"] = 0
                        st.error("Muitas tentativas incorretas. O acesso foi bloqueado por 2 minutos.")
                    else:
                        st.error("CPF ou senha incorretos, ou usuário inativo.")
        st.caption("A sessão é mantida pelo Streamlit. Ao recarregar o navegador, será necessário entrar novamente.")


# --------------------------- TELAS ---------------------------
def tela_painel(db, perfil):
    st.title("Painel de gestão")
    hoje = date.today()
    alunos = db.query(func.count(Aluno.id)).filter(Aluno.ativo == 1).scalar() or 0
    inativos = db.query(func.count(Aluno.id)).filter(Aluno.ativo != 1).scalar() or 0
    responsaveis = db.query(func.count(Responsavel.id)).scalar() or 0
    contratos = db.query(func.count(Contrato.id)).filter(Contrato.status == "Ativo").scalar() or 0
    atividades_vencidas = db.query(func.count(AtividadeAluno.id)).filter(
        AtividadeAluno.data_prazo < hoje,
        or_(AtividadeAluno.status.is_(None),
            ~AtividadeAluno.status.in_(["Realizada", "Realizado", "Cancelada"])),
    ).scalar() or 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alunos ativos", alunos, f"{inativos} inativo(s)" if inativos else None, delta_color="off",
              delta_arrow="off")
    c2.metric("Responsáveis", responsaveis)
    c3.metric("Contratos ativos", contratos)
    c4.metric("Atividades com prazo vencido", atividades_vencidas)

    if perfil in ("Admin", "Financeiro"):
        cab, sel_mes, sel_ano = st.columns([3, 1.2, 0.8])
        cab.subheader("Financeiro")
        mes = sel_mes.selectbox("Mês", list(range(1, 13)), index=hoje.month - 1,
                                format_func=lambda m: MESES[m - 1], key="painel_dre_mes")
        ano = int(sel_ano.number_input("Ano", min_value=2020, max_value=2100, value=hoje.year, step=1,
                                       key="painel_dre_ano"))
        dre = dre_do_mes(db, ano, mes)
        r = resumo_financeiro(db, hoje)
        col_dre, col_pend = st.columns([1.6, 1])
        col_dre.markdown(html_mini_dre(dre, f"Mini DRE — {MESES[mes - 1]}/{ano}"), unsafe_allow_html=True)
        with col_pend:
            st.metric("A receber (em dia)", moeda(r["a_receber"]), help="Receitas pendentes com vencimento a partir de hoje.")
            st.metric("Em atraso", moeda(r["em_atraso"]), f"{r['qtd_atraso']} lançamento(s)",
                      delta_color="inverse" if r["qtd_atraso"] else "off",
                      help="Receitas pendentes com vencimento anterior a hoje.")

    cab_al, fil_al = st.columns([3, 2])
    cab_al.subheader("Alunos cadastrados")
    situacao = fil_al.radio("Mostrar", SITUACOES_ALUNO, horizontal=True, key="painel_alunos_situacao")
    lista = filtrar_por_situacao(db.query(Aluno).options(joinedload(Aluno.responsavel)), situacao
                                 ).order_by(Aluno.ativo.desc(), Aluno.nome).all()
    if lista:
        st.dataframe(pd.DataFrame([{
            "ID": a.id, "Aluno": a.nome, "Situação": "Ativo" if a.ativo else "Inativo",
            "Nascimento": para_str_br(a.data_nascimento),
            "Idade": calcular_idade(a.data_nascimento), "Escolaridade": a.escolaridade or "-",
            "Responsável": a.responsavel.nome if a.responsavel else "-",
        } for a in lista]), width="stretch", hide_index=True)
    else:
        st.info("Nenhum aluno com essa situação.")


SITUACOES_ALUNO = ["Ativos", "Inativos", "Todos"]


def rotulo_aluno(a):
    return f"{a.id} — {a.nome}{'' if a.ativo else ' (inativo)'}"


def filtrar_por_situacao(consulta, situacao):
    if situacao == "Ativos":
        return consulta.filter(Aluno.ativo == 1)
    if situacao == "Inativos":
        return consulta.filter(Aluno.ativo != 1)
    return consulta


def contagem_por_aluno(db, coluna_aluno):
    """{aluno_id: quantidade} em uma única consulta agrupada."""
    return dict(db.query(coluna_aluno, func.count()).group_by(coluna_aluno).all())


def ultima_data_por_aluno(db, coluna_aluno, coluna_data):
    return dict(db.query(coluna_aluno, func.max(coluna_data)).group_by(coluna_aluno).all())


def tela_consulta_alunos(db, perfil):
    """Consulta de alunos ativos E inativos. O histórico é preservado: inativar nunca apaga dados."""
    f1, f2, f3 = st.columns([1.4, 2, 1.6])
    situacao = f1.radio("Situação", SITUACOES_ALUNO, horizontal=True, key="consulta_alunos_situacao")
    busca = f2.text_input("Buscar por nome do aluno ou do responsável", key="consulta_alunos_busca").strip()
    consulta = db.query(Aluno).options(joinedload(Aluno.responsavel))
    alunos = filtrar_por_situacao(consulta, situacao).order_by(Aluno.ativo.desc(), Aluno.nome).all()
    if busca:
        termo = normalizar_texto(busca)
        alunos = [a for a in alunos if termo in normalizar_texto(a.nome)
                  or (a.responsavel and termo in normalizar_texto(a.responsavel.nome))]
    total_ativos = db.query(func.count(Aluno.id)).filter(Aluno.ativo == 1).scalar() or 0
    total_inativos = db.query(func.count(Aluno.id)).filter(Aluno.ativo != 1).scalar() or 0
    f3.metric("Ativos · Inativos", f"{total_ativos} · {total_inativos}")
    if not alunos:
        st.info("Nenhum aluno encontrado com esses filtros.")
        return

    clinico = perfil in ("Admin", "Profissional")   # LGPD: perfil Financeiro não vê contagens clínicas
    contratos = {}
    for c in db.query(Contrato).order_by(Contrato.id).all():
        if c.status == "Ativo" or c.aluno_id not in contratos:
            contratos[c.aluno_id] = c
    lanc = contagem_por_aluno(db, LancamentoFinanceiro.aluno_id)
    if clinico:
        pront = contagem_por_aluno(db, Prontuario.aluno_id)
        ativ = contagem_por_aluno(db, AtividadeAluno.aluno_id)
        docs = contagem_por_aluno(db, DocumentoAluno.aluno_id)
        ultimas = [ultima_data_por_aluno(db, Prontuario.aluno_id, Prontuario.data_registro),
                   ultima_data_por_aluno(db, AtividadeAluno.aluno_id, AtividadeAluno.data_atividade),
                   ultima_data_por_aluno(db, DocumentoAluno.aluno_id, DocumentoAluno.criado_em)]
    linhas = []
    for a in alunos:
        c = contratos.get(a.id)
        linha = {
            "ID": a.id, "Aluno": a.nome, "Situação": "Ativo" if a.ativo else "Inativo",
            "Nascimento": para_str_br(a.data_nascimento), "Idade": calcular_idade(a.data_nascimento),
            "Escolaridade": a.escolaridade or "-", "Responsável": a.responsavel.nome if a.responsavel else "-",
            "Telefone": (a.responsavel.telefone if a.responsavel else "") or "-",
            "Contrato": f"{c.descricao_servico or '-'} · {moeda(c.valor_mensalidade)} ({c.status})" if c else "-",
            "Lançamentos": lanc.get(a.id, 0),
        }
        if clinico:
            datas = [d.get(a.id) for d in ultimas if d.get(a.id)]
            linha.update({"Prontuários": pront.get(a.id, 0), "Atividades": ativ.get(a.id, 0),
                          "Caderno": docs.get(a.id, 0),
                          "Último registro": para_str_br(max(datas)) if datas else "-"})
        linhas.append(linha)
    tabela = pd.DataFrame(linhas)
    st.caption(f"{len(tabela)} aluno(s). Inativar um aluno **não apaga nada**: contratos, prontuários, atividades, "
               "caderno e lançamentos continuam guardados e podem ser consultados nas telas de cada módulo.")
    st.dataframe(tabela, width="stretch", hide_index=True)
    st.download_button("⬇️ Exportar esta lista (CSV)", data=tabela.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"alunos_{situacao.lower()}.csv", mime="text/csv", key="consulta_alunos_csv")


def tela_cadastros(db, perfil="Admin"):
    st.title("Alunos e responsáveis")
    tab0, tab1, tab2, tab3, tab4 = st.tabs([
        "🔎 Consultar alunos", "➕ Cadastrar responsável", "➕ Cadastrar aluno", "✏️ Gerenciar alunos",
        "👥 Gerenciar responsáveis"
    ])
    with tab0:
        tela_consulta_alunos(db, perfil)

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
                # Sem "or date.today()": antes, salvar um aluno sem nascimento gravava a data de hoje.
                nasc_edit = st.date_input("Nascimento", value=aluno.data_nascimento, min_value=date(1900, 1, 1), max_value=date.today(), format="DD/MM/YYYY")
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
            rotulo = "Inativar aluno" if aluno.ativo else "Reativar aluno"
            if st.button(rotulo, key=f"alternar_ativo_aluno_{aluno.id}"):
                novo_estado = 0 if aluno.ativo else 1
                try:
                    aluno.ativo = novo_estado
                    db.commit()
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "alteração da situação do aluno")
                else:
                    registrar_auditoria("aluno_inativado" if not novo_estado else "aluno_reativado", f"aluno_id={aluno.id}")
                    st.rerun()

    with tab4:
        responsaveis = db.query(Responsavel).order_by(Responsavel.nome).all()
        if not responsaveis:
            st.info("Não há responsáveis cadastrados.")
        else:
            st.dataframe(pd.DataFrame([{
                "ID": r.id, "Nome": r.nome, "Telefone": r.telefone or "", "E-mail": r.email or "",
                "Alunos vinculados": len(r.alunos)
            } for r in responsaveis]), width="stretch", hide_index=True)
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

def tela_gerar_mensalidades(db):
    st.markdown("Gera os lançamentos de **Receita / Mensalidade** de todos os contratos ativos na competência escolhida. "
                "Lançamentos já existentes são ignorados, então a geração pode ser repetida sem duplicar.")
    hoje = date.today()
    c1, c2 = st.columns(2)
    mes = c1.selectbox("Mês", list(range(1, 13)), index=hoje.month - 1, format_func=lambda m: MESES[m - 1], key="gm_mes")
    ano = int(c2.number_input("Ano", min_value=2020, max_value=2100, value=hoje.year, step=1, key="gm_ano"))
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    fim_mes = date(ano, mes, ultimo_dia)
    contratos = (db.query(Contrato).options(joinedload(Contrato.aluno))
                 .filter(Contrato.status == "Ativo").order_by(Contrato.id).all())
    previstos = []
    for c in contratos:
        if not c.aluno or not c.aluno.ativo or not c.valor_mensalidade:
            continue
        if c.data_inicio and c.data_inicio > fim_mes:
            continue
        descricao = f"Mensalidade {mes:02d}/{ano} — contrato #{c.id}"
        existe = db.query(LancamentoFinanceiro.id).filter_by(aluno_id=c.aluno_id, descricao=descricao).first() is not None
        # Dia 31 em mês de 30 dias (ou fevereiro) vira o último dia do mês.
        vencimento = date(ano, mes, min(int(c.dia_vencimento or 10), ultimo_dia))
        previstos.append({"contrato": c, "descricao": descricao, "vencimento": vencimento, "existe": existe})
    if not previstos:
        st.info("Nenhum contrato ativo elegível para esta competência.")
        return
    novos = [p for p in previstos if not p["existe"]]
    st.dataframe(pd.DataFrame([{
        "Contrato": p["contrato"].id, "Aluno": p["contrato"].aluno.nome,
        "Valor": moeda(p["contrato"].valor_mensalidade), "Vencimento": para_str_br(p["vencimento"]),
        "Situação": "Já lançado" if p["existe"] else "Será gerado",
    } for p in previstos]), width="stretch", hide_index=True)
    st.caption(f"{len(novos)} novo(s) lançamento(s) — total {moeda(sum(p['contrato'].valor_mensalidade for p in novos))}.")
    if st.button(f"Gerar {len(novos)} lançamento(s)", type="primary", disabled=not novos, key="gm_gerar"):
        try:
            for p in novos:
                c = p["contrato"]
                db.add(LancamentoFinanceiro(
                    aluno_id=c.aluno_id, tipo="Receita", descricao=p["descricao"], categoria="Mensalidade",
                    valor=float(c.valor_mensalidade), data_vencimento=p["vencimento"], status="Pendente",
                    observacao=f"Gerado automaticamente a partir do contrato #{c.id}.",
                    servico=c.descricao_servico,
                ))
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            mensagem_erro(exc, "geração das mensalidades")
            return
        registrar_auditoria("mensalidades_geradas", f"competência {mes:02d}/{ano}: {len(novos)} lançamento(s)")
        st.success(f"{len(novos)} mensalidade(s) gerada(s). Confira em 💰 Financeiro.")
        st.rerun()


def tela_contratos(db):
    st.title("Contratos e mensalidades")
    servicos = lista_servicos(carregar_configuracoes(db))
    alunos = db.query(Aluno).filter_by(ativo=1).order_by(Aluno.nome).all()
    mapa = {f"{a.id} — {a.nome}": a.id for a in alunos}
    tab1, tab2, tab3 = st.tabs(["➕ Novo contrato", "✏️ Consultar e gerenciar contratos", "🧾 Gerar mensalidades"])
    # tab3 é renderizada antes porque tab2 encerra a função quando não há contratos.
    with tab3:
        tela_gerar_mensalidades(db)
    with tab1:
        if not mapa:
            st.info("Cadastre um aluno ativo antes de criar um contrato.")
        else:
            # Formulário começa VAZIO (antes já vinha com o primeiro aluno e valores preenchidos).
            with st.form("f_contrato", clear_on_submit=True):
                aluno_label = st.selectbox("Aluno *", list(mapa), index=None, placeholder="Selecione o aluno")
                servico = st.selectbox("Serviço *", servicos, index=None, placeholder="Selecione o serviço")
                c1, c2 = st.columns(2)
                valor = c1.number_input("Mensalidade (R$) *", min_value=0.0, value=None, step=25.0,
                                        placeholder="Ex.: 350,00")
                vencimento = c2.number_input("Dia de vencimento *", min_value=1, max_value=31, value=None,
                                             step=1, placeholder="1 a 31")
                inicio = st.date_input("Data de início", value=None, format="DD/MM/YYYY")
                criar = st.form_submit_button("Criar contrato", type="primary")
            if criar:
                faltando = [nome for nome, v in (("aluno", aluno_label), ("serviço", servico),
                                                 ("mensalidade", valor), ("dia de vencimento", vencimento)) if not v]
                if faltando:
                    st.error("Preencha: " + ", ".join(faltando) + ".")
                else:
                    try:
                        db.add(Contrato(aluno_id=mapa[aluno_label], descricao_servico=servico,
                                        valor_mensalidade=float(valor), dia_vencimento=int(vencimento),
                                        data_inicio=inicio or date.today(), status="Ativo"))
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
        } for c in contratos]), width="stretch", hide_index=True)
        cmap = {f"{c.id} — {c.aluno.nome if c.aluno else 'Aluno não localizado'} — {c.status}": c.id for c in contratos}
        selecionado = st.selectbox("Selecione o contrato para editar", list(cmap), key="contrato_editar_sel")
        contrato = db.get(Contrato, cmap[selecionado])
        with st.form(f"f_editar_contrato_{contrato.id}"):
            opcoes_serv = opcoes_com_atual(servicos, contrato.descricao_servico)
            servico_e = st.selectbox("Serviço", opcoes_serv,
                                     index=opcoes_serv.index(contrato.descricao_servico)
                                     if contrato.descricao_servico in opcoes_serv else None,
                                     placeholder="Selecione o serviço")
            valor_e = st.number_input("Mensalidade (R$)", min_value=0.0, value=float(contrato.valor_mensalidade or 0), step=25.0)
            venc_e = st.number_input("Dia de vencimento", min_value=1, max_value=31, value=int(contrato.dia_vencimento or 10))
            status_opcoes = ["Ativo", "Suspenso", "Encerrado"]
            status_atual = contrato.status if contrato.status in status_opcoes else "Ativo"
            status_e = st.selectbox("Situação", status_opcoes, index=status_opcoes.index(status_atual))
            salvar_e = st.form_submit_button("Salvar alterações", type="primary")
        if salvar_e:
            if not servico_e:
                st.error("Selecione o serviço.")
            else:
                contrato.descricao_servico = servico_e
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
    incluir_inativos = st.checkbox("Incluir alunos inativos (consultar histórico)", key="prontuario_inativos")
    consulta = db.query(Aluno).order_by(Aluno.ativo.desc(), Aluno.nome)
    alunos = consulta.all() if incluir_inativos else consulta.filter(Aluno.ativo == 1).all()
    if not alunos:
        st.info("Cadastre um aluno ativo antes de registrar uma evolução.")
        return
    mapa = {rotulo_aluno(a): a.id for a in alunos}
    aluno_label = st.selectbox("Aluno", list(mapa), key="prontuario_aluno")
    aluno_id = mapa[aluno_label]
    if aluno_label.endswith("(inativo)"):
        st.info("Aluno inativo: o histórico está preservado para consulta.")
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
            } for p in registros]), width="stretch", hide_index=True)
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

ACERVO_GERAL = "📚 Acervo geral (sem aluno)"


def trecho_encontrado(texto, termo, margem=90):
    """Pedaço do texto do PDF em volta do termo buscado, para mostrar onde ele aparece."""
    if not texto or not termo:
        return ""
    pos = texto.casefold().find(termo.casefold())
    if pos < 0:
        return ""
    inicio, fim = max(0, pos - margem), min(len(texto), pos + len(termo) + margem)
    return ("…" if inicio else "") + texto[inicio:fim].replace("\n", " ") + ("…" if fim < len(texto) else "")


def tela_materiais_pdf(db, usuario, alunos, categorias):
    st.markdown("Guarde **atividades, materiais escolares e avaliações** em PDF, vinculados a um aluno "
                "ou no **acervo geral** para reutilizar. Os arquivos ficam no armazenamento privado.")
    if not painel_storage(usuario, "storage_materiais"):
        return
    mapa_destino = {ACERVO_GERAL: None}
    mapa_destino.update({f"{a.id} — {a.nome}{'' if a.ativo else ' (inativo)'}": a.id for a in alunos})
    aba_importar, aba_biblioteca = st.tabs(["⬆️ Importar PDFs", "🔎 Biblioteca de materiais"])

    with aba_importar:
        with st.form("f_importar_materiais", clear_on_submit=True):
            arquivos = st.file_uploader("PDFs (pode selecionar vários de uma vez, até 20 MB cada)",
                                        type=["pdf"], accept_multiple_files=True)
            c1, c2 = st.columns(2)
            tipo = c1.selectbox("Tipo", TIPOS_MATERIAL)
            destino = c2.selectbox("Guardar para", list(mapa_destino))
            titulo = st.text_input("Título (opcional)",
                                   help="Em branco, usa o nome do arquivo. Com vários arquivos, vira um prefixo.")
            c3, c4, c5 = st.columns(3)
            area = c3.text_input("Área / disciplina", placeholder="ex.: Matemática — frações")
            nivel = c4.text_input("Série / nível", placeholder="ex.: 3º ano")
            data_ref = c5.date_input("Data de referência", value=date.today(), format="DD/MM/YYYY")
            descricao = st.text_area("Descrição / objetivo", placeholder="Para que serve, como aplicar, critérios da avaliação…")
            c6, c7 = st.columns([2, 1])
            criar_atividade = c6.checkbox("Criar também uma atividade planejada para o aluno (uma por arquivo)",
                                          help="Só vale quando o PDF é guardado para um aluno.")
            categoria = c7.selectbox("Categoria da atividade", categorias)
            importar = st.form_submit_button("Importar PDFs", type="primary")
        if importar:
            aluno_id = mapa_destino[destino]
            if not arquivos:
                st.error("Selecione pelo menos um arquivo PDF.")
            else:
                importados, avisos = [], []
                barra = st.progress(0.0, text="Importando…")
                for i, arq in enumerate(arquivos, start=1):
                    titulo_arq = titulo.strip()
                    if titulo_arq and len(arquivos) > 1:
                        titulo_arq = f"{titulo_arq} — {titulo_pelo_arquivo(arq.name)}"
                    dados = {"titulo": titulo_arq, "tipo": tipo, "area": area, "nivel": nivel, "descricao": descricao,
                             "aluno_id": aluno_id, "data": data_ref, "categoria": categoria,
                             "criar_atividade": criar_atividade and aluno_id is not None}
                    try:
                        material, aviso = importar_material_pdf(db, arq.getvalue(), arq.name, dados, usuario.nome)
                    except Exception as exc:
                        print(f"[ERRO] importação de material {arq.name}: {exc}")
                        avisos.append(f"{arq.name}: não foi possível importar (falha no envio ou no banco).")
                    else:
                        if material:
                            importados.append(material)
                        if aviso:
                            avisos.append(aviso)
                    barra.progress(i / len(arquivos), text=f"Importando… {i}/{len(arquivos)}")
                barra.empty()
                if importados:
                    registrar_auditoria("materiais_importados",
                                        f"{len(importados)} PDF(s); tipo={tipo}; aluno_id={aluno_id or 'acervo'}; "
                                        f"ids={','.join(str(m.id) for m in importados)}", usuario.nome)
                    extra = " e atividade(s) criada(s)" if criar_atividade and aluno_id else ""
                    st.success(f"{len(importados)} PDF(s) importado(s){extra}. Veja em 🔎 Biblioteca de materiais.")
                if criar_atividade and aluno_id is None:
                    st.info("Nenhuma atividade foi criada: o material foi para o acervo geral, sem aluno.")
                for aviso in avisos:
                    st.warning(aviso)

    with aba_biblioteca:
        f1, f2, f3 = st.columns([2, 1, 1])
        busca = f1.text_input("Buscar no título, descrição, área ou **dentro do PDF**", key="mat_busca").strip()
        filtro_tipo = f2.selectbox("Tipo", ["Todos"] + TIPOS_MATERIAL, key="mat_tipo")
        filtro_dest = f3.selectbox("Aluno", ["Todos"] + list(mapa_destino), key="mat_aluno")
        incluir_arquivados = st.checkbox("Incluir arquivados", key="mat_arquivados")
        M = MaterialPedagogico
        consulta = db.query(M).options(joinedload(M.aluno), joinedload(M.atividade))
        if busca:
            termo = f"%{busca}%"
            consulta = consulta.filter(or_(M.titulo.ilike(termo), M.descricao.ilike(termo), M.area.ilike(termo),
                                           M.nivel.ilike(termo), M.texto_extraido.ilike(termo)))
        if filtro_tipo != "Todos":
            consulta = consulta.filter(M.tipo == filtro_tipo)
        if filtro_dest != "Todos":
            aluno_f = mapa_destino[filtro_dest]
            consulta = consulta.filter(M.aluno_id.is_(None) if aluno_f is None else M.aluno_id == aluno_f)
        if not incluir_arquivados:
            consulta = consulta.filter(M.status == "Ativo")
        materiais = consulta.order_by(M.criado_em.desc(), M.id.desc()).limit(500).all()
        if not materiais:
            st.info("Nenhum material encontrado com esses filtros.")
            return
        st.caption(f"{len(materiais)} material(is) encontrado(s).")
        st.dataframe(pd.DataFrame([{
            "ID": m.id, "Título": m.titulo, "Tipo": m.tipo,
            "Aluno": m.aluno.nome if m.aluno else "Acervo geral", "Área": m.area or "-", "Nível": m.nivel or "-",
            "Páginas": m.paginas or "-", "Tamanho": formatar_tamanho(m.tamanho_bytes),
            "Atividade": f"#{m.atividade_id} {m.atividade.titulo}" if m.atividade else "-",
            "Importado em": formatar_data_hora(m.criado_em), "Por": m.criado_por or "-", "Situação": m.status,
        } for m in materiais]), width="stretch", hide_index=True)

        opcoes = {f"#{m.id} — {m.titulo} ({m.aluno.nome if m.aluno else 'acervo'})": m.id for m in materiais}
        mat = db.get(M, opcoes[st.selectbox("Material", list(opcoes), key="mat_sel")])
        if busca:
            trecho = trecho_encontrado(mat.texto_extraido, busca)
            if trecho:
                st.markdown(f"> {html.escape(trecho)}")
        b1, b2 = st.columns(2)
        with b1:
            chave_link = f"link_mat_{mat.id}"
            if st.button("Gerar link para abrir (10 min)", key=f"btn_{chave_link}", width="stretch"):
                try:
                    st.session_state[chave_link] = gerar_link_pdf(mat.caminho_storage)
                    registrar_auditoria("material_aberto", f"material_id={mat.id}", usuario.nome)
                except Exception as exc:
                    mensagem_erro(exc, "geração do acesso ao PDF")
            if st.session_state.get(chave_link):
                st.link_button("📄 Abrir PDF", st.session_state[chave_link], width="stretch")
        with b2:
            arquivar = mat.status == "Ativo"
            confirmar = st.checkbox("Confirmo " + ("o arquivamento" if arquivar else "a reativação"), key=f"conf_mat_{mat.id}")
            if st.button("Arquivar material" if arquivar else "Reativar material", key=f"arq_mat_{mat.id}",
                         disabled=not confirmar, width="stretch"):
                try:
                    mat.status = "Arquivado" if arquivar else "Ativo"
                    db.commit()
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "alteração do material")
                else:
                    registrar_auditoria("material_arquivado" if arquivar else "material_reativado",
                                        f"material_id={mat.id}", usuario.nome)
                    st.rerun()

        with st.expander("✏️ Editar dados do material"):
            atividades_aluno = (db.query(AtividadeAluno).filter_by(aluno_id=mat.aluno_id)
                                .order_by(AtividadeAluno.data_atividade.desc()).all() if mat.aluno_id else [])
            mapa_ativ = {"Nenhuma": None}
            mapa_ativ.update({f"#{a.id} — {a.titulo} ({para_str_br(a.data_atividade)})": a.id for a in atividades_aluno})
            dest_atual = next((k for k, v in mapa_destino.items() if v == mat.aluno_id), ACERVO_GERAL)
            ativ_atual = next((k for k, v in mapa_ativ.items() if v == mat.atividade_id), "Nenhuma")
            with st.form(f"f_editar_material_{mat.id}"):
                titulo_e = st.text_input("Título", value=mat.titulo)
                e1, e2 = st.columns(2)
                tipo_e = e1.selectbox("Tipo", TIPOS_MATERIAL,
                                      index=TIPOS_MATERIAL.index(mat.tipo) if mat.tipo in TIPOS_MATERIAL else 0)
                dest_e = e2.selectbox("Guardar para", list(mapa_destino), index=list(mapa_destino).index(dest_atual))
                e3, e4 = st.columns(2)
                area_e = e3.text_input("Área / disciplina", value=mat.area or "")
                nivel_e = e4.text_input("Série / nível", value=mat.nivel or "")
                ativ_e = st.selectbox("Vincular à atividade do aluno", list(mapa_ativ), index=list(mapa_ativ).index(ativ_atual),
                                      help="Lista as atividades do aluno atual. Se trocar o aluno, salve e escolha a atividade depois.")
                desc_e = st.text_area("Descrição / objetivo", value=mat.descricao or "")
                salvar_e = st.form_submit_button("Salvar alterações", type="primary")
            if salvar_e:
                if not titulo_e.strip():
                    st.error("O título é obrigatório.")
                else:
                    novo_aluno = mapa_destino[dest_e]
                    try:
                        mat.titulo = titulo_e.strip()[:180]
                        mat.tipo = tipo_e
                        mat.area = area_e.strip()
                        mat.nivel = nivel_e.strip()
                        mat.descricao = desc_e.strip()
                        # Atividade só faz sentido se for do mesmo aluno.
                        mat.atividade_id = mapa_ativ[ativ_e] if novo_aluno == mat.aluno_id else None
                        mat.aluno_id = novo_aluno
                        db.commit()
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "edição do material")
                    else:
                        registrar_auditoria("material_editado", f"material_id={mat.id}", usuario.nome)
                        st.rerun()
            st.caption(f"Arquivo original: {mat.nome_original} · SHA-256 {mat.sha256[:16]}…")

        if pode_excluir(usuario):
            usos = db.query(func.count(FolhaInterativa.id)).filter(FolhaInterativa.material_id == mat.id).scalar() or 0
            aviso = (f"Também serão apagadas {usos} folha(s) com caneta feitas a partir dele "
                     "(os PDFs já guardados no Caderno Digital continuam lá)." if usos else "")
            if confirmar_exclusao(f"excl_mat_{mat.id}", f"o material “{mat.titulo}” e o arquivo PDF", aviso):
                try:
                    excluir_material(db, mat, usuario.nome)
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "exclusão do material")
                else:
                    st.session_state.pop("mat_sel", None)
                    st.rerun()


# --------------------------- EXCLUSÃO DEFINITIVA -------------
def pode_excluir(usuario):
    return getattr(usuario, "perfil", "") in ("Admin", "Profissional")


def confirmar_exclusao(chave, descricao, detalhe=""):
    """Painel com aviso + confirmação explícita. Retorna True só no clique confirmado."""
    with st.expander("🗑️ Excluir definitivamente"):
        st.warning(f"Isto apaga **{descricao}** de forma permanente. Não é possível desfazer."
                   + (f" {detalhe}" if detalhe else "")
                   + " Se quiser apenas tirar de circulação, prefira arquivar/cancelar.")
        ok = st.checkbox("Entendo que a exclusão é permanente", key=f"{chave}_ok")
        return st.button("Excluir definitivamente", key=f"{chave}_btn", type="primary", disabled=not ok)


def _apagar_arquivo_storage(caminho):
    """Depois do commit no banco: se o Storage falhar, sobra só um arquivo órfão (inofensivo)."""
    try:
        excluir_objeto_storage(caminho)
    except Exception as exc:
        print(f"[AVISO] Arquivo não removido do Storage ({caminho}): {exc}")


def excluir_folha(db, folha, usuario_nome, commit=True):
    """Apaga a folha com caneta e a escrita de cada página. O PDF já guardado no Caderno é mantido."""
    db.query(FolhaPagina).filter_by(folha_id=folha.id).delete(synchronize_session=False)
    detalhe = f"folha_id={folha.id}; titulo={folha.titulo}; aluno_id={folha.aluno_id}; status={folha.status}"
    db.delete(folha)
    if commit:
        db.commit()
        registrar_auditoria("folha_excluida", detalhe, usuario_nome)
    return detalhe


def excluir_documento(db, doc, usuario_nome):
    """Apaga o registro do Caderno Digital e o PDF no Storage."""
    caminho = doc.caminho_storage
    detalhe = f"documento_id={doc.id}; titulo={doc.titulo}; aluno_id={doc.aluno_id}; categoria={doc.categoria}"
    db.query(FolhaInterativa).filter_by(documento_id=doc.id).update({"documento_id": None},
                                                                   synchronize_session=False)
    db.delete(doc)
    db.commit()
    registrar_auditoria("caderno_registro_excluido", detalhe, usuario_nome)
    _apagar_arquivo_storage(caminho)


def excluir_material(db, mat, usuario_nome):
    """Apaga o material em PDF, as folhas com caneta feitas a partir dele e o arquivo no Storage."""
    caminho = mat.caminho_storage
    folhas = db.query(FolhaInterativa).filter_by(material_id=mat.id).all()
    for f in folhas:
        excluir_folha(db, f, usuario_nome, commit=False)
    detalhe = f"material_id={mat.id}; titulo={mat.titulo}; folhas_excluidas={len(folhas)}"
    db.delete(mat)
    db.commit()
    registrar_auditoria("material_excluido", detalhe, usuario_nome)
    _apagar_arquivo_storage(caminho)


def excluir_atividade(db, atividade, usuario_nome):
    """Apaga a atividade pedagógica; materiais vinculados ficam, só perdem o vínculo."""
    db.query(MaterialPedagogico).filter_by(atividade_id=atividade.id).update({"atividade_id": None},
                                                                             synchronize_session=False)
    detalhe = f"atividade_id={atividade.id}; titulo={atividade.titulo}; aluno_id={atividade.aluno_id}"
    db.delete(atividade)
    db.commit()
    registrar_auditoria("atividade_excluida", detalhe, usuario_nome)


def iniciar_folha(db, material, aluno_id, usuario_nome):
    total = contar_paginas_pdf(pdf_do_material(material.caminho_storage, material.sha256))
    if total > MAX_PAGINAS_FOLHA:
        raise ValueError(f"O PDF tem {total} páginas; o limite para preencher com caneta é {MAX_PAGINAS_FOLHA}.")
    folha = FolhaInterativa(material_id=material.id, aluno_id=aluno_id, titulo=material.titulo[:180],
                            status="Em andamento", total_paginas=total, criado_em=datetime.now(),
                            atualizado_em=datetime.now(), criado_por=usuario_nome)
    db.add(folha)
    db.commit()
    return folha


def concluir_folha(db, folha, compartilhar, mensagem, usuario_nome):
    """Gera o PDF final, envia ao Storage e registra no Caderno Digital."""
    conteudo = gerar_pdf_folha(db, folha)
    caminho = f"alunos/{folha.aluno_id}/folha_{folha.id}_{uuid.uuid4().hex[:8]}.pdf"
    enviar_pdf_storage(caminho, conteudo)
    try:
        categoria = "Avaliação" if folha.material and folha.material.tipo == "Avaliação" else "Atividade realizada"
        documento = DocumentoAluno(
            aluno_id=folha.aluno_id, titulo=folha.titulo, categoria=categoria,
            descricao=f"Preenchida com caneta no atendimento (folha #{folha.id}).",
            nome_original=f"{titulo_pelo_arquivo(folha.titulo)[:150]}.pdf", caminho_storage=caminho,
            mime_type="application/pdf", tamanho_bytes=len(conteudo), sha256=hashlib.sha256(conteudo).hexdigest(),
            status="Ativo", criado_em=date.today(), criado_por=usuario_nome,
            visivel_familia=1 if compartilhar else 0, mensagem_familia=(mensagem or "").strip(),
            compartilhado_em=datetime.now() if compartilhar else None, visualizacoes_familia=0,
        )
        db.add(documento)
        db.flush()
        folha.documento_id = documento.id
        folha.status = "Concluída"
        folha.concluido_em = datetime.now()
        db.commit()
    except Exception:
        db.rollback()
        try:
            excluir_objeto_storage(caminho)
        except Exception as limpeza_exc:
            print(f"[AVISO] Falha ao limpar arquivo órfão: {limpeza_exc}")
        raise
    return documento


def tela_atividade_caneta(db, usuario):
    if usuario.perfil not in ("Admin", "Profissional"):
        st.error("Acesso restrito aos perfis Admin e Profissional.")
        return
    folha_id = st.session_state.get("folha_aberta")
    folha = db.get(FolhaInterativa, folha_id) if folha_id else None
    if folha and folha.status == "Em andamento":
        _tela_folha_aberta(db, usuario, folha)
        return
    st.session_state.pop("folha_aberta", None)

    st.title("✍️ Atividade com caneta")
    st.caption("O aluno preenche a atividade pronta (Canva, Word, Excel exportados em PDF) com a mesa "
               "digitalizadora, caneta ou o dedo. Ao concluir, o resultado vai para o 📓 Caderno Digital.")
    aviso = st.session_state.get("aviso_folha_concluida")
    if aviso:
        with st.container(border=True):
            st.success(f"✅ **{aviso['titulo']}** concluída e guardada no 📓 Caderno Digital de **{aviso['aluno']}** "
                       f"(registro #{aviso['documento_id']}, " +
                       ("visível para a família)." if aviso["familia"] else "privado — compartilhe quando quiser)."))
            a1, a2 = st.columns(2)
            a1.button("📓 Ver no Caderno Digital", type="primary", width="stretch", key="ver_no_caderno",
                      on_click=ir_para_caderno, args=(aviso["aluno_id"], aviso["aluno"], aviso["documento_id"]))
            if a2.button("Fechar aviso", width="stretch", key="fechar_aviso_folha"):
                st.session_state.pop("aviso_folha_concluida", None)
                st.rerun()
    if not painel_storage(usuario, "storage_caneta"):
        return
    alunos = db.query(Aluno).filter_by(ativo=1).order_by(Aluno.nome).all()
    if not alunos:
        st.info("Cadastre um aluno ativo primeiro.")
        return
    mapa = {f"{a.id} — {a.nome}": a.id for a in alunos}
    aluno_id = mapa[st.selectbox("Aluno", list(mapa), key="caneta_aluno")]

    em_andamento = (db.query(FolhaInterativa).filter_by(aluno_id=aluno_id, status="Em andamento")
                    .order_by(FolhaInterativa.atualizado_em.desc()).all())
    if em_andamento:
        st.subheader("Continuar de onde parou")
        for f in em_andamento:
            c1, c2, c3, c4 = st.columns([3.6, 1.2, 1.6, 1.1])
            c1.markdown(f"**{html.escape(f.titulo)}** · {f.total_paginas} pág. · "
                        f"última alteração {formatar_data_hora(f.atualizado_em)}")
            if c2.button("▶️ Abrir", key=f"abrir_folha_{f.id}", width="stretch", type="primary"):
                st.session_state["folha_aberta"] = f.id
                st.session_state["folha_pagina"] = 1
                st.rerun()
            if c3.button("✅ Concluir agora", key=f"concluir_lista_{f.id}", width="stretch",
                         help="Gera o PDF com o que já foi escrito e guarda no Caderno Digital (privado)."):
                if executar_conclusao(db, usuario, f, False):
                    st.rerun()
            if c4.button("Cancelar", key=f"cancelar_folha_{f.id}", width="stretch"):
                try:
                    f.status = "Cancelada"
                    db.commit()
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "cancelamento da folha")
                else:
                    registrar_auditoria("folha_cancelada", f"folha_id={f.id}", usuario.nome)
                    st.rerun()

    st.subheader("Nova atividade")
    M = MaterialPedagogico
    materiais = (db.query(M).filter(M.status == "Ativo", or_(M.aluno_id.is_(None), M.aluno_id == aluno_id))
                 .order_by(M.criado_em.desc()).limit(300).all())
    if not materiais:
        st.info("Nenhum PDF disponível. Importe a atividade em 📁 Atividades → 📎 Materiais em PDF "
                "(no Canva, Word ou Excel use **Exportar/Salvar como PDF**).")
    else:
        opcoes = {f"{m.titulo} — {m.tipo}{'' if m.aluno_id else ' (acervo geral)'}"
                  f"{f' · {m.paginas} pág.' if m.paginas else ''}": m.id for m in materiais}
        escolha = st.selectbox("Atividade ou avaliação", list(opcoes), key="caneta_material")
        if st.button("✍️ Começar a preencher", type="primary", key="caneta_comecar"):
            try:
                with st.spinner("Preparando as páginas…"):
                    folha_nova = iniciar_folha(db, db.get(M, opcoes[escolha]), aluno_id, usuario.nome)
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                db.rollback()
                mensagem_erro(exc, "preparação da folha")
            else:
                registrar_auditoria("folha_iniciada", f"folha_id={folha_nova.id}; material_id={folha_nova.material_id}",
                                    usuario.nome)
                st.session_state["folha_aberta"] = folha_nova.id
                st.session_state["folha_pagina"] = 1
                st.rerun()

    concluidas = (db.query(FolhaInterativa).filter_by(aluno_id=aluno_id, status="Concluída")
                  .order_by(FolhaInterativa.concluido_em.desc()).limit(50).all())
    if concluidas:
        with st.expander(f"✅ Concluídas ({len(concluidas)})"):
            st.dataframe(pd.DataFrame([{
                "Atividade": f.titulo, "Páginas": f.total_paginas, "Concluída em": formatar_data_hora(f.concluido_em),
                "No caderno": f"#{f.documento_id}" if f.documento_id else "-",
            } for f in concluidas]), width="stretch", hide_index=True)
            st.caption("O PDF preenchido está no 📓 Caderno Digital, onde você decide se a família vê.")

    todas = (db.query(FolhaInterativa).filter_by(aluno_id=aluno_id)
             .order_by(FolhaInterativa.criado_em.desc()).all())
    if todas and pode_excluir(usuario):
        op_folhas = {f"#{f.id} — {f.titulo} ({f.status}, {formatar_data_hora(f.criado_em)})": f.id for f in todas}
        st.markdown("##### 🗑️ Excluir folha com caneta")
        escolha_f = st.selectbox("Folha", list(op_folhas), key="excl_folha_sel")
        folha_ex = db.get(FolhaInterativa, op_folhas[escolha_f])
        if confirmar_exclusao(f"excl_folha_{folha_ex.id}", f"a folha “{folha_ex.titulo}” e a escrita do aluno",
                              "Se ela já foi concluída, o PDF no Caderno Digital continua lá (exclua por lá, se quiser)."):
            try:
                excluir_folha(db, folha_ex, usuario.nome)
            except SQLAlchemyError as exc:
                db.rollback()
                mensagem_erro(exc, "exclusão da folha")
            else:
                st.session_state.pop("excl_folha_sel", None)
                st.rerun()


def _tela_folha_aberta(db, usuario, folha):
    modo_aluno = st.toggle("🖥️ Modo aluno (esconde menus)", key="modo_aluno")
    if modo_aluno:
        st.markdown("<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl'],header,"
                    "div[data-testid='stElementContainer']:has(.ed-header),div[data-testid='stMarkdown']:has(.ed-header){display:none !important;}"
                    ".block-container{padding-top:.6rem !important;max-width:100% !important;}</style>",
                    unsafe_allow_html=True)
    total = folha.total_paginas
    pagina = min(max(int(st.session_state.get("folha_pagina", 1)), 1), total)

    c_tit, c_ant, c_pag, c_prox, c_fam = st.columns([4, 0.8, 1.4, 0.8, 1.6])
    c_tit.markdown(f"### {html.escape(folha.titulo)}  \n<span style='color:#64748b'>{html.escape(folha.aluno.nome)}</span>",
                   unsafe_allow_html=True)
    c_fam.checkbox("👪 Família vê", key=f"familia_ve_{folha.id}",
                   help="Marque antes de concluir para o resultado aparecer no portal da família. "
                        "Pode mudar depois no Caderno Digital.")
    if c_ant.button("◀", key="folha_ant", disabled=pagina <= 1, width="stretch"):
        st.session_state["folha_pagina"] = pagina - 1
        st.rerun()
    c_pag.markdown(f"<div style='text-align:center;padding-top:.45rem'><b>Página {pagina} de {total}</b></div>",
                   unsafe_allow_html=True)
    if c_prox.button("▶", key="folha_prox", disabled=pagina >= total, width="stretch"):
        st.session_state["folha_pagina"] = pagina + 1
        st.rerun()

    try:
        jpeg, largura, altura = imagem_pagina(folha.material.caminho_storage, folha.material.sha256, pagina)
    except Exception as exc:
        mensagem_erro(exc, "abertura da página")
        if st.button("Voltar"):
            st.session_state.pop("folha_aberta", None)
            st.rerun()
        return
    registro = db.query(FolhaPagina).filter_by(folha_id=folha.id, pagina=pagina).first()
    tinta = f"data:image/png;base64,{registro.tinta_png}" if registro and registro.tinta_png else ""
    chave = f"{folha.id}-{pagina}"
    valor = _componente_canvas(fundo=data_url(jpeg, "image/jpeg"), tinta=tinta, largura=largura, altura=altura,
                               chave=chave, so_caneta=bool(st.session_state.get("so_caneta_padrao", False)),
                               key=f"canvas_{chave}", default=None)

    # O componente envia a página inteira após cada traço (e junto com "Concluir"/"Continuar depois");
    # grava só versões novas desta página e só então executa a ação: o último traço nunca fica de fora.
    acao = ""
    if isinstance(valor, dict) and valor.get("chave") == chave:
        marca = (valor.get("sessao"), valor.get("versao"))
        if st.session_state.get(f"tinta_salva_{chave}") != marca:
            png = None if valor.get("vazio") else png_de_data_url(valor.get("png"))
            if png is None and not valor.get("vazio"):
                st.warning("A escrita recebida não é válida e não foi salva.")
            else:
                try:
                    salvar_tinta_pagina(db, folha, pagina, png)
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "gravação da escrita")
                else:
                    st.session_state[f"tinta_salva_{chave}"] = marca
                    acao = valor.get("acao") or ""
    if acao == "pausar":
        st.session_state.pop("folha_aberta", None)
        st.rerun()
    if acao == "concluir":
        if executar_conclusao(db, usuario, folha, bool(st.session_state.get(f"familia_ve_{folha.id}"))):
            st.rerun()

    st.caption("Use **✅ Concluir** (dois cliques) na barra da folha para gerar o PDF e guardar no 📓 Caderno Digital "
               "do aluno, ou **⏸️ Continuar depois** para terminar em outra hora. A escrita também é salva sozinha "
               "após cada traço. Com a mesa digitalizadora, marque **Só caneta** para ignorar a mão apoiada na tela.")


def executar_conclusao(db, usuario, folha, compartilhar):
    """Conclui a folha, guarda o PDF no Caderno Digital do aluno e deixa um aviso para a próxima tela."""
    try:
        with st.spinner("Gerando o PDF com a escrita do aluno e guardando no Caderno Digital…"):
            documento = concluir_folha(db, folha, compartilhar, "", usuario.nome)
    except Exception as exc:
        db.rollback()
        mensagem_erro(exc, "conclusão da atividade")
        registrar_auditoria("folha_conclusao_falhou",
                            f"folha_id={folha.id}; erro={type(exc).__name__}: {str(exc)[:200]}", usuario.nome)
        return False
    registrar_auditoria("folha_concluida", f"folha_id={folha.id}; documento_id={documento.id}; "
                        f"familia={int(compartilhar)}", usuario.nome)
    st.session_state.pop("folha_aberta", None)
    st.session_state["aviso_folha_concluida"] = {
        "documento_id": documento.id, "titulo": folha.titulo, "aluno_id": folha.aluno_id,
        "aluno": folha.aluno.nome if folha.aluno else "-", "familia": bool(compartilhar),
    }
    return True


def ir_para_caderno(aluno_id, aluno_nome, documento_id):
    """Callback: abre o Caderno Digital já filtrado no aluno e no registro recém-criado."""
    st.session_state["menu_principal"] = "📓 Caderno Digital"
    st.session_state["docs_filtro_aluno"] = f"{aluno_id} — {aluno_nome}"
    st.session_state["caderno_destacar"] = documento_id
    st.session_state.pop("aviso_folha_concluida", None)


def tela_atividades(db, usuario):
    st.title("Atividades pedagógicas")
    st.caption("Planejamento, execução e acompanhamento individual das atividades.")
    alunos = db.query(Aluno).order_by(Aluno.nome).all()
    if not alunos:
        st.info("Cadastre um aluno antes de registrar atividades.")
        return
    mapa = {f"{a.id} — {a.nome}{'' if a.ativo else ' (inativo)'}": a.id for a in alunos}
    categorias = ["Intervenção", "Leitura", "Escrita", "Matemática", "Atenção", "Memória", "Linguagem", "Coordenação motora", "Outro"]
    status_opcoes = ["Planejada", "Em andamento", "Realizada", "Reagendada", "Cancelada"]
    tab1, tab2, tab3, tab4 = st.tabs(["➕ Nova atividade", "📋 Consultar e editar", "📊 Acompanhamento",
                                      "📎 Materiais em PDF"])
    with tab4:
        tela_materiais_pdf(db, usuario, alunos, categorias)
    with tab1:
        ativos = {f"{a.id} — {a.nome}": a.id for a in alunos if a.ativo}
        if not ativos:
            st.info("Não há alunos ativos para vincular à nova atividade.")
        else:
            with st.form("f_atividade_nova_v2", clear_on_submit=True):
                aluno_sel = st.selectbox("Aluno", list(ativos))
                titulo = st.text_input("Título da atividade *")
                c1, c2 = st.columns(2)
                with c1:
                    categoria = st.selectbox("Categoria", categorias)
                    area = st.text_input("Área / habilidade trabalhada")
                    data_atividade = st.date_input("Data prevista / realizada", value=date.today(), format="DD/MM/YYYY")
                with c2:
                    status = st.selectbox("Situação", status_opcoes, index=0)
                    prazo = st.date_input("Prazo (opcional)", value=None, format="DD/MM/YYYY")
                objetivo = st.text_area("Objetivo pedagógico")
                descricao = st.text_area("Descrição / etapas / materiais")
                resultado = st.text_area("Resultado / desempenho observado")
                observacoes = st.text_area("Observações para acompanhamento")
                salvar = st.form_submit_button("Salvar atividade", type="primary")
            if salvar:
                if not titulo.strip():
                    st.error("Informe o título da atividade.")
                else:
                    try:
                        db.add(AtividadeAluno(
                            aluno_id=ativos[aluno_sel], titulo=titulo.strip(), categoria=categoria,
                            area=area.strip(), data_atividade=data_atividade, data_prazo=prazo,
                            objetivo=objetivo.strip(), descricao=descricao.strip(), resultado=resultado.strip(),
                            observacoes=observacoes.strip(), status=status
                        ))
                        db.commit()
                        st.success("Atividade registrada com sucesso.")
                        st.rerun()
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "cadastro da atividade")
    with tab2:
        registros = db.query(AtividadeAluno).order_by(AtividadeAluno.data_atividade.desc(), AtividadeAluno.id.desc()).all()
        if not registros:
            st.info("Nenhuma atividade registrada.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                filtro_aluno = st.selectbox("Aluno", ["Todos"] + list(mapa), key="filtro_atividades_aluno_v2")
            with c2:
                filtro_status = st.selectbox("Situação", ["Todas"] + status_opcoes, key="filtro_atividades_status_v2")
            filtrados = registros
            if filtro_aluno != "Todos":
                filtrados = [r for r in filtrados if r.aluno_id == mapa[filtro_aluno]]
            if filtro_status != "Todas":
                filtrados = [r for r in filtrados if normalizar_status_atividade(r.status) == filtro_status]
            st.dataframe(pd.DataFrame([{
                "ID": r.id, "Aluno": r.aluno.nome if r.aluno else "-", "Data": para_str_br(r.data_atividade),
                "Prazo": para_str_br(r.data_prazo), "Título": r.titulo, "Área": r.area or r.categoria,
                "Situação": normalizar_status_atividade(r.status)
            } for r in filtrados]), width="stretch", hide_index=True)
            if filtrados:
                opcoes = {f"#{r.id} — {r.aluno.nome if r.aluno else '-'} — {r.titulo}": r.id for r in filtrados}
                escolha = st.selectbox("Selecione para editar", list(opcoes), key="atividade_editar_sel_v2")
                atividade = db.get(AtividadeAluno, opcoes[escolha])
                aluno_atual = next((k for k, v in mapa.items() if v == atividade.aluno_id), list(mapa)[0])
                cat_atual = atividade.categoria if atividade.categoria in categorias else "Outro"
                # Antes, registros "Realizado" viravam "Planejada" ao serem editados.
                st_norm = normalizar_status_atividade(atividade.status)
                st_atual = st_norm if st_norm in status_opcoes else "Planejada"
                with st.form(f"f_editar_atividade_v2_{atividade.id}"):
                    aluno_e = st.selectbox("Aluno", list(mapa), index=list(mapa).index(aluno_atual))
                    titulo_e = st.text_input("Título", value=atividade.titulo or "")
                    c1, c2 = st.columns(2)
                    with c1:
                        cat_e = st.selectbox("Categoria", categorias, index=categorias.index(cat_atual))
                        area_e = st.text_input("Área / habilidade", value=atividade.area or "")
                        data_e = st.date_input("Data", value=atividade.data_atividade or date.today(), format="DD/MM/YYYY")
                    with c2:
                        status_e = st.selectbox("Situação", status_opcoes, index=status_opcoes.index(st_atual))
                        prazo_e = st.date_input("Prazo", value=atividade.data_prazo, format="DD/MM/YYYY")
                    objetivo_e = st.text_area("Objetivo pedagógico", value=atividade.objetivo or "")
                    desc_e = st.text_area("Descrição / etapas / materiais", value=atividade.descricao or "")
                    resultado_e = st.text_area("Resultado / desempenho observado", value=atividade.resultado or "")
                    obs_e = st.text_area("Observações", value=atividade.observacoes or "")
                    salvar_e = st.form_submit_button("Salvar alterações", type="primary")
                if salvar_e:
                    if not titulo_e.strip():
                        st.error("O título é obrigatório.")
                    else:
                        try:
                            atividade.aluno_id = mapa[aluno_e]
                            atividade.titulo = titulo_e.strip()
                            atividade.categoria = cat_e
                            atividade.area = area_e.strip()
                            atividade.data_atividade = data_e
                            atividade.data_prazo = prazo_e
                            atividade.status = status_e
                            atividade.objetivo = objetivo_e.strip()
                            atividade.descricao = desc_e.strip()
                            atividade.resultado = resultado_e.strip()
                            atividade.observacoes = obs_e.strip()
                            db.commit()
                            st.success("Atividade atualizada.")
                            st.rerun()
                        except SQLAlchemyError as exc:
                            db.rollback()
                            mensagem_erro(exc, "edição da atividade")
                anexos = (db.query(MaterialPedagogico)
                          .filter_by(atividade_id=atividade.id, status="Ativo").order_by(MaterialPedagogico.id).all())
                if anexos:
                    st.markdown("**📎 PDFs desta atividade:** " + " · ".join(
                        f"#{m.id} {html.escape(m.titulo)} ({m.tipo})" for m in anexos))
                    st.caption("Para abrir, use a aba 📎 Materiais em PDF → Biblioteca.")
                st.caption("O histórico não é apagado: utilize Cancelada para atividades que não serão executadas.")
                if pode_excluir(usuario):
                    vinculos = (db.query(func.count(MaterialPedagogico.id))
                                .filter(MaterialPedagogico.atividade_id == atividade.id).scalar() or 0)
                    if confirmar_exclusao(f"excl_ativ_{atividade.id}", f"a atividade “{atividade.titulo}”",
                                          f"{vinculos} PDF(s) ligado(s) a ela continuam na biblioteca, só sem o vínculo."
                                          if vinculos else ""):
                        try:
                            excluir_atividade(db, atividade, usuario.nome)
                        except SQLAlchemyError as exc:
                            db.rollback()
                            mensagem_erro(exc, "exclusão da atividade")
                        else:
                            st.session_state.pop("atividade_editar_sel_v2", None)
                            st.rerun()
    with tab3:
        todos = db.query(AtividadeAluno).all()
        if todos:
            total = len(todos)
            planejadas = sum(1 for a in todos if normalizar_status_atividade(a.status) == "Planejada")
            andamento = sum(1 for a in todos if normalizar_status_atividade(a.status) == "Em andamento")
            realizadas = sum(1 for a in todos if normalizar_status_atividade(a.status) == "Realizada")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total", total)
            k2.metric("Planejadas", planejadas)
            k3.metric("Em andamento", andamento)
            k4.metric("Realizadas", realizadas)
            atrasadas = [a for a in todos if a.data_prazo and a.data_prazo < date.today() and normalizar_status_atividade(a.status) not in STATUS_CONCLUIDOS]
            if atrasadas:
                st.warning(f"Existem {len(atrasadas)} atividade(s) com prazo vencido.")
                st.dataframe(pd.DataFrame([{"Aluno": a.aluno.nome if a.aluno else "-", "Atividade": a.titulo,
                    "Prazo": para_str_br(a.data_prazo), "Situação": normalizar_status_atividade(a.status)} for a in atrasadas]), width="stretch", hide_index=True)
        else:
            st.info("Ainda não há atividades para consolidar.")


def painel_storage(usuario, prefixo="storage"):
    """Mostra a situação do Supabase Storage. Retorna True se os envios estão liberados.

    Usado pelo Caderno Digital e pelos Materiais em PDF (mesmo bucket privado).
    """
    cfg = obter_config_storage()
    if not cfg:
        st.warning("O armazenamento ainda não está configurado. Cadastre as credenciais privadas do Supabase nos Secrets para habilitar os envios.")
        st.markdown(
            "1. No Supabase: **Project Settings → API**. Copie a *Project URL* e a chave **service_role** (secret).\n"
            "2. No computador: preencha `.streamlit/secrets.toml`. No Streamlit Cloud: **App → Settings → Secrets**.\n"
            "3. Reinicie o app e volte aqui: o sistema confere a conexão e cria o bucket privado.")
        st.code('[supabase]\nurl = "https://SEU-PROJETO.supabase.co"\nservice_role_key = "SUA_SERVICE_ROLE_KEY"\nbucket = "documentos-clinicos"', language="toml")
        st.info("Não publique a service_role_key nem a coloque no código do GitHub: ela dá acesso total ao projeto.")
        return False

    # Diagnóstico guardado na sessão para não consultar o Supabase a cada clique.
    if "storage_diagnostico" not in st.session_state:
        st.session_state["storage_diagnostico"] = diagnosticar_storage()
    situacao, msg = st.session_state["storage_diagnostico"]
    with st.expander("☁️ Situação do armazenamento", expanded=situacao != "ok"):
        {"ok": st.success, "publico": st.error, "sem_bucket": st.warning}.get(situacao, st.error)(msg)
        b1, b2 = st.columns(2)
        if b1.button("🔄 Verificar novamente", key=f"{prefixo}_verificar", width="stretch"):
            st.session_state.pop("storage_diagnostico", None)
            st.rerun()
        if situacao == "sem_bucket" and usuario.perfil == "Admin":
            if b2.button("Criar bucket privado agora", key=f"{prefixo}_criar_bucket", type="primary", width="stretch"):
                try:
                    criar_bucket_privado()
                except RuntimeError as exc:
                    mensagem_erro(exc, "criação do bucket")
                else:
                    registrar_auditoria("storage_bucket_criado", cfg["bucket"], usuario.nome)
                    st.session_state.pop("storage_diagnostico", None)
                    st.rerun()
    # Bucket público expõe documentos clínicos (LGPD): envios ficam bloqueados até corrigir.
    if situacao in ("erro", "sem_bucket", "publico"):
        if situacao == "sem_bucket" and usuario.perfil != "Admin":
            st.info("Peça a um administrador para criar o bucket nesta tela.")
        return False
    return True


CATEGORIAS_CADERNO = [
    "Atividade realizada", "Produção do aluno", "Tarefa para casa", "Registro da sessão",
    "Devolutiva / relatório", "Comunicado à família", "Avaliação", "Documento escolar",
    "Laudo recebido", "Contrato e termos", "Autorização", "Comprovante", "Outros",
]
# Categorias sensíveis: só vão para a família com confirmação explícita na aba Consultar.
CATEGORIAS_SENSIVEIS = {"Laudo recebido", "Contrato e termos", "Autorização", "Comprovante"}


def tela_caderno_digital(db, usuario):
    st.title("📓 Caderno Digital")
    st.caption("O caderno do aluno: atividades, produções, tarefas e devolutivas em PDF. "
               "Você escolhe o que a família vê no portal; o resto fica privado.")
    if usuario.perfil not in ("Admin", "Profissional"):
        st.error("Acesso restrito aos perfis Admin e Profissional.")
        return
    if not painel_storage(usuario, "storage_guarda"):
        return
    alunos = db.query(Aluno).order_by(Aluno.nome).all()
    if not alunos:
        st.info("Cadastre um aluno antes de alimentar o caderno.")
        return
    mapa = {f"{a.id} — {a.nome}{'' if a.ativo else ' (inativo)'}": a.id for a in alunos}
    categorias = CATEGORIAS_CADERNO
    if st.session_state.get("caderno_destacar"):
        st.info(f"Atividade com caneta guardada como registro #{st.session_state['caderno_destacar']}. "
                "Abra a aba **🗂️ Consultar e compartilhar**: ele já está selecionado.")
    tab1, tab2, tab3 = st.tabs(["⬆️ Adicionar ao caderno", "🗂️ Consultar e compartilhar", "💡 Como alimentar"])
    with tab1:
        st.markdown("**PDF até 20 MB** · armazenamento privado. Marque *Mostrar para a família* para aparecer no portal.")
        with st.form("f_upload_documento", clear_on_submit=True):
            c1, c2 = st.columns(2)
            aluno_sel = c1.selectbox("Aluno", list(mapa))
            categoria = c2.selectbox("Tipo de registro", categorias)
            titulo = st.text_input("Título *", placeholder="ex.: Produção de texto — A viagem da Lua")
            data_doc = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            arquivo = st.file_uploader("Arquivo PDF", type=["pdf"], accept_multiple_files=False)
            compartilhar = st.checkbox("👪 Mostrar para a família no portal", value=False)
            mensagem_fam = st.text_area("Mensagem para a família (aparece no portal)",
                                        placeholder="ex.: Hoje a Ana organizou as ideias do texto com mais autonomia. "
                                                    "Em casa, peça para ela recontar a história.")
            descricao = st.text_area("Anotação interna (a família NÃO vê)")
            enviar = st.form_submit_button("Adicionar ao caderno", type="primary")
        if enviar:
            erro_pdf = validar_pdf(arquivo.getvalue()) if arquivo is not None else None
            if not titulo.strip() or arquivo is None:
                st.error("Informe o título e selecione um arquivo PDF.")
            elif erro_pdf:
                st.error(f"O arquivo {erro_pdf}.")
            elif compartilhar and categoria in CATEGORIAS_SENSIVEIS:
                st.error(f"“{categoria}” é um documento sensível. Adicione sem compartilhar e, se quiser mesmo "
                         "mostrar à família, use a aba 🗂️ Consultar e compartilhar, que pede confirmação.")
            else:
                conteudo = arquivo.getvalue()
                digest = hashlib.sha256(conteudo).hexdigest()
                duplicado = db.query(DocumentoAluno).filter_by(aluno_id=mapa[aluno_sel], sha256=digest, status="Ativo").first()
                if duplicado:
                    st.warning(f"Este mesmo arquivo já está no caderno como '{duplicado.titulo}' (#{duplicado.id}).")
                else:
                    ext_nome = Path(arquivo.name).name[:180]
                    caminho = f"alunos/{mapa[aluno_sel]}/{uuid.uuid4().hex}.pdf"
                    enviado_storage = False
                    try:
                        enviar_pdf_storage(caminho, conteudo)
                        enviado_storage = True
                        documento = DocumentoAluno(
                            aluno_id=mapa[aluno_sel], titulo=titulo.strip(), categoria=categoria,
                            descricao=descricao.strip(), nome_original=ext_nome,
                            caminho_storage=caminho, mime_type="application/pdf", tamanho_bytes=len(conteudo),
                            sha256=digest, status="Ativo", criado_em=data_doc, criado_por=usuario.nome,
                            visivel_familia=1 if compartilhar else 0, mensagem_familia=mensagem_fam.strip(),
                            compartilhado_em=datetime.now() if compartilhar else None, visualizacoes_familia=0,
                        )
                        db.add(documento)
                        db.commit()
                    except Exception as exc:
                        db.rollback()
                        if enviado_storage:
                            try:
                                excluir_objeto_storage(caminho)
                            except Exception as limpeza_exc:
                                print(f"[AVISO] Falha ao limpar arquivo órfão: {limpeza_exc}")
                        mensagem_erro(exc, "inclusão no caderno")
                    else:
                        registrar_auditoria("caderno_registro_incluido",
                                            f"documento_id={documento.id}; familia={int(compartilhar)}", usuario.nome)
                        st.success("Registro adicionado ao caderno" +
                                   (" e já visível no portal da família." if compartilhar else " (privado)."))
    with tab2:
        documentos = db.query(DocumentoAluno).order_by(DocumentoAluno.criado_em.desc(), DocumentoAluno.id.desc()).all()
        f1, f2, f3 = st.columns(3)
        filtro_aluno = f1.selectbox("Aluno", ["Todos"] + list(mapa), key="docs_filtro_aluno")
        filtro_categoria = f2.selectbox("Tipo", ["Todos"] + categorias, key="docs_filtro_categoria")
        filtro_familia = f3.selectbox("Visibilidade", ["Todos", "Visíveis à família", "Privados"], key="docs_filtro_familia")
        incluir_arquivados = st.checkbox("Incluir registros arquivados", value=False)
        filtrados = documentos
        if filtro_aluno != "Todos":
            filtrados = [d for d in filtrados if d.aluno_id == mapa[filtro_aluno]]
        if filtro_categoria != "Todos":
            filtrados = [d for d in filtrados if d.categoria == filtro_categoria]
        if filtro_familia != "Todos":
            quer = filtro_familia == "Visíveis à família"
            filtrados = [d for d in filtrados if bool(d.visivel_familia) == quer]
        if not incluir_arquivados:
            filtrados = [d for d in filtrados if d.status == "Ativo"]
        if not filtrados:
            st.info("Nenhum registro encontrado com os filtros selecionados.")
            return
        st.dataframe(pd.DataFrame([{
            "ID": d.id, "Aluno": d.aluno.nome if d.aluno else "-", "Data": para_str_br(d.criado_em),
            "Tipo": d.categoria, "Título": d.titulo,
            "Família vê": "👪 Sim" if d.visivel_familia else "🔒 Não",
            "Aberto pela família": d.visualizacoes_familia or 0,
            "Situação": d.status, "Incluído por": d.criado_por or "-",
        } for d in filtrados]), width="stretch", hide_index=True)
        opcoes = {f"#{d.id} — {d.aluno.nome if d.aluno else '-'} — {d.titulo} ({d.status})": d.id for d in filtrados}
        destacar = st.session_state.pop("caderno_destacar", None)
        if destacar:
            rotulo = next((k for k, v in opcoes.items() if v == destacar), None)
            if rotulo:
                st.session_state["doc_selecionado"] = rotulo
        selecionado = st.selectbox("Registro", list(opcoes), key="doc_selecionado")
        doc = db.get(DocumentoAluno, opcoes[selecionado])
        c1, c2 = st.columns(2)
        chave_ver = f"ver_doc_{doc.id}"
        with c1:
            ver = bool(st.session_state.get(chave_ver))
            if st.button("🔼 Fechar visualização" if ver else "👁️ Ver o PDF aqui", key=f"btn_{chave_ver}",
                         width="stretch", type="primary"):
                st.session_state[chave_ver] = not ver
                if not ver:
                    registrar_auditoria("documento_aberto", f"documento_id={doc.id}", usuario.nome)
                st.rerun()
        with c2:
            if doc.status == "Ativo":
                confirmar = st.checkbox("Confirmo o arquivamento deste registro", key=f"confirmar_arq_doc_{doc.id}")
                if st.button("Arquivar registro", key=f"arquivar_doc_{doc.id}", disabled=not confirmar, width="stretch"):
                    try:
                        doc.status = "Arquivado"
                        doc.visivel_familia = 0  # arquivado sai do portal
                        db.commit()
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "arquivamento do registro")
                    else:
                        registrar_auditoria("caderno_registro_arquivado", f"documento_id={doc.id}", usuario.nome)
                        st.rerun()
        if pode_excluir(usuario):
            familia = " A família também deixa de ver este registro no portal." if doc.visivel_familia else ""
            if confirmar_exclusao(f"excl_doc_{doc.id}", f"o registro “{doc.titulo}” e o arquivo PDF", familia.strip()):
                try:
                    excluir_documento(db, doc, usuario.nome)
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "exclusão do registro")
                else:
                    st.session_state.pop("doc_selecionado", None)
                    st.rerun()

        if st.session_state.get(chave_ver):
            with st.container(border=True):
                visualizar_pdf_inline(doc.caminho_storage, doc.sha256, doc.nome_original, f"caderno_doc_{doc.id}")

        st.markdown("##### 👪 Compartilhamento com a família")
        if doc.status == "Ativo" and not doc.visivel_familia:
            st.warning("🔒 **A família ainda NÃO vê este registro.** Marque *Mostrar este registro no portal da "
                       "família* e clique em **Salvar compartilhamento**.")
        if doc.status == "Ativo" and doc.aluno:
            bloco_link_familia(db, usuario, doc.aluno, "caderno")
        if doc.status != "Ativo":
            st.info("Registros arquivados não aparecem no portal.")
        else:
            sensivel = doc.categoria in CATEGORIAS_SENSIVEIS
            with st.form(f"f_compartilhar_{doc.id}"):
                visivel = st.checkbox("Mostrar este registro no portal da família", value=bool(doc.visivel_familia))
                msg = st.text_area("Mensagem para a família", value=doc.mensagem_familia or "")
                conf_sensivel = (st.checkbox(f"Confirmo que a família deve ver este documento sensível ({doc.categoria}).")
                                 if sensivel else True)
                salvar_comp = st.form_submit_button("Salvar compartilhamento", type="primary")
            if salvar_comp:
                if visivel and sensivel and not conf_sensivel:
                    st.error("Marque a confirmação para compartilhar um documento sensível.")
                else:
                    passou_a_compartilhar = visivel and not doc.visivel_familia
                    try:
                        doc.visivel_familia = 1 if visivel else 0
                        doc.mensagem_familia = msg.strip()
                        if passou_a_compartilhar:
                            doc.compartilhado_em = datetime.now()
                        db.commit()
                    except SQLAlchemyError as exc:
                        db.rollback()
                        mensagem_erro(exc, "compartilhamento do registro")
                    else:
                        registrar_auditoria("caderno_compartilhamento",
                                            f"documento_id={doc.id}; familia={int(visivel)}", usuario.nome)
                        st.rerun()
            if doc.visivel_familia:
                st.caption(f"Visível desde {formatar_data_hora(doc.compartilhado_em) if doc.compartilhado_em else '-'} · "
                           f"aberto {doc.visualizacoes_familia or 0} vez(es) pela família.")
        with st.expander("Detalhes do registro"):
            st.write("**Anotação interna:**", doc.descricao or "Não informada")
            st.write("**Arquivo original:**", doc.nome_original)
            st.write("**Tamanho:**", formatar_tamanho(doc.tamanho_bytes))
            st.write("**SHA-256:**", doc.sha256)
    with tab3:
        st.markdown(DICAS_CADERNO)


DICAS_CADERNO = """
**Rotina sugerida**
- **Depois de cada atendimento (2 min):** 1 registro com a produção do aluno ou a atividade feita, com uma mensagem curta.
- **Toda semana:** 1 *Tarefa para casa* com instrução clara para os pais (o que fazer, quanto tempo, como ajudar).
- **Todo mês:** 1 *Devolutiva / relatório* com a evolução (combine com os indicadores de 📈 Desempenho).

**Como transformar papel em PDF pelo celular**
- Google Drive → **+ → Digitalizar**, ou o app de câmera/Notas do celular → "Digitalizar documento". Junte várias páginas num PDF só.

**Mensagem para a família — modelo**
> *O que fizemos:* … · *O que observei:* … (comece por um avanço) · *Em casa:* uma ação simples.

**Boas práticas (LGPD)**
- A família vê **só** o que tem 👪. Anotações internas, hipóteses e laudos ficam 🔒.
- Laudos, contratos e comprovantes pedem confirmação extra para serem compartilhados.
- Um registro por arquivo, com título que diga o conteúdo e a data correta da atividade.
- Errou? Desmarque o compartilhamento ou arquive: sai do portal na hora.
"""


VALORES_VAZIOS = {"", "nan", "none", "-", "—", "não informado", "nao informado"}


def limpar_respostas(serie):
    texto = serie.astype(str).str.strip()
    return texto[~texto.str.casefold().isin(VALORES_VAZIOS)]


def obter_link_planilha(db):
    cfg = db.query(ConfiguracaoSistema).filter_by(chave="link_planilha_mestre").first()
    return (cfg.valor or "").strip() if cfg else ""


# Escala da planilha (qualitativa, com ordem): usada só para posicionar cores, nunca como nota.
NIVEIS_INDICADOR = (("necessita", 0), ("aten", 0), ("desenvolv", 1), ("satisf", 2))
NIVEIS_COMPREENSAO = (("não", 0), ("nao", 0), ("parcial", 1), ("sim", 2))
CORES_NIVEL = {"N": "#f6cdc7", "N/D": "#f8dcc1", "D": "#f7eaa9", "D/S": "#d3ebe4", "S": "#a9dacd"}
# Texto de cada nível: tom escuro da própria cor (contraste suave, mais nítido que preto).
TEXTO_NIVEL = {"N": "#9f3a31", "N/D": "#94561c", "D": "#7a6510", "D/S": "#3b7a6b", "S": "#1f6656"}
ROTULO_NIVEL = {"N": "Necessita de atenção", "N/D": "Necessita de atenção / Em desenvolvimento",
                "D": "Em desenvolvimento", "D/S": "Em desenvolvimento / Satisfatório", "S": "Satisfatório"}


def nivel_da_resposta(valor, niveis=NIVEIS_INDICADOR):
    """Converte a resposta (pode ter duas marcações) para 0..2; None se vazia/desconhecida."""
    texto = str(valor or "").strip().casefold()
    if not texto or texto in VALORES_VAZIOS:
        return None
    achados = []
    for parte in re.split(r"[,;\n]+", texto):
        parte = parte.strip()
        for chave, nivel in niveis:
            if chave in parte:
                achados.append(nivel)
                break
    return sum(achados) / len(achados) if achados else None


def sigla_do_nivel(nivel):
    if nivel is None:
        return None
    return {0: "N", 0.5: "N/D", 1: "D", 1.5: "D/S", 2: "S"}.get(round(nivel * 2) / 2)


def nome_curto_indicador(coluna):
    """'Participação e comportamento [Autonomia]' -> 'Autonomia'."""
    m = re.search(r"\[(.+?)\]", str(coluna))
    return (m.group(1) if m else str(coluna)).strip()


def montar_mapa_pontos(df_aluno, indicadores, col_data, col_compreensao):
    """Linhas = pontos avaliados; colunas = atendimentos em ordem. Retorna (linhas, datas)."""
    datas = (pd.to_datetime(df_aluno[col_data], dayfirst=True, errors="coerce").dt.strftime("%d/%m").fillna("?")
             if col_data else pd.Series([f"#{i}" for i in range(1, len(df_aluno) + 1)], index=df_aluno.index))
    linhas = []
    for col in indicadores:
        linhas.append((nome_curto_indicador(col), [nivel_da_resposta(v) for v in df_aluno[col]], "indicador"))
    if col_compreensao:
        linhas.append(("Compreendeu o conteúdo",
                       [nivel_da_resposta(v, NIVEIS_COMPREENSAO) for v in df_aluno[col_compreensao]], "compreensao"))
    return linhas, list(datas)


def grafico_mapa_pontos(linhas, datas, chave):
    """Mapa de evolução: cada quadrado é um ponto avaliado num atendimento."""
    escala = [[0.0, CORES_NIVEL["N"]], [0.125, CORES_NIVEL["N"]], [0.125, CORES_NIVEL["N/D"]], [0.375, CORES_NIVEL["N/D"]],
              [0.375, CORES_NIVEL["D"]], [0.625, CORES_NIVEL["D"]], [0.625, CORES_NIVEL["D/S"]], [0.875, CORES_NIVEL["D/S"]],
              [0.875, CORES_NIVEL["S"]], [1.0, CORES_NIVEL["S"]]]
    z, textos, dicas = [], [], []
    for nome, niveis, tipo in reversed(linhas):  # primeira linha no topo
        z.append([n for n in niveis])
        linha_txt, linha_dica = [], []
        for n in niveis:
            sigla = sigla_do_nivel(n)
            if tipo == "compreensao":
                rot = {"N": "Não", "D": "Parc.", "S": "Sim"}.get(sigla, sigla or "")
                completo = {"N": "Não", "D": "Parcialmente", "S": "Sim"}.get(sigla, "Não registrado")
            else:
                rot = sigla or ""
                completo = ROTULO_NIVEL.get(sigla, "Não registrado")
            linha_txt.append(rot)
            linha_dica.append(completo)
        textos.append(linha_txt)
        dicas.append(linha_dica)
    nomes = [n for n, _, _ in reversed(linhas)]
    x = list(range(len(datas)))
    fig = go.Figure(go.Heatmap(
        z=z, x=x, y=nomes, zmin=0, zmax=2, colorscale=escala, showscale=False, xgap=3, ygap=3,
        customdata=[[[d, datas[i]] for i, d in enumerate(linha)] for linha in dicas],
        hovertemplate="<b>%{y}</b><br>%{customdata[1]}: %{customdata[0]}<extra></extra>", hoverongaps=False))
    for iy, (linha_txt, linha_z) in enumerate(zip(textos, z)):
        for ix, (rot, nivel) in enumerate(zip(linha_txt, linha_z)):
            if rot:
                fig.add_annotation(x=ix, y=nomes[iy], text=rot, showarrow=False,
                                   font={"size": 12, "color": TEXTO_NIVEL.get(sigla_do_nivel(nivel), "#475569")})
    passo = max(1, len(datas) // 14)  # muitos atendimentos: rótulo de data a cada N colunas
    fig.update_layout(
        height=max(230, 42 * len(nomes) + 70), margin={"l": 8, "r": 8, "t": 8, "b": 40},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Arial, sans-serif", "size": 11, "color": "#334155"},
        xaxis={"tickmode": "array", "tickvals": x[::passo], "ticktext": datas[::passo], "showgrid": False,
               "zeroline": False, "tickangle": 0, "side": "bottom"},
        yaxis={"showgrid": False, "zeroline": False, "automargin": True, "tickfont": {"size": 12, "color": "#142b4a"}},
        hoverlabel={"bgcolor": "#142b4a", "font": {"color": "#ffffff"}})
    st.plotly_chart(fig, width="stretch", key=chave, config={"displayModeBar": False, "responsive": True})
    legenda = " ".join(
        f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px">'
        f'<span style="width:12px;height:12px;border-radius:3px;background:{CORES_NIVEL[s]};display:inline-block"></span>'
        f'{html.escape(r)}</span>'
        for s, r in (("N", "N · Necessita de atenção"), ("D", "D · Em desenvolvimento"), ("S", "S · Satisfatório"),
                     ("N/D", "N/D ou D/S · duas marcações no dia")))
    st.markdown(f'<div style="font-size:.82rem;color:#64748b;margin:-6px 0 6px 0">{legenda}</div>',
                unsafe_allow_html=True)


def tendencia_do_ponto(niveis):
    """Compara os 3 primeiros com os 3 últimos registros (ordem da escala, não nota)."""
    validos = [n for n in niveis if n is not None]
    if len(validos) < 4:
        return "poucos", "▬ poucos registros"
    k = min(3, len(validos) // 2)
    inicio, fim = sum(validos[:k]) / k, sum(validos[-k:]) / k
    if fim - inicio > 0.3:
        return "up", "▲ avançando"
    if fim - inicio < -0.3:
        return "down", "▼ atenção"
    return "eq", "▬ estável"


def grafico_retrato_pontos(linhas, chave):
    """Retrato de cada ponto (todos os atendimentos) + tendência recente."""
    indicadores = [(nome, niveis) for nome, niveis, tipo in linhas if tipo == "indicador"]
    if not indicadores:
        return
    nomes, perc = [], {"S": [], "D": [], "N": []}
    for nome, niveis in reversed(indicadores):
        validos = [n for n in niveis if n is not None]
        total = len(validos) or 1
        conta = {"S": 0.0, "D": 0.0, "N": 0.0}
        for n in validos:  # duas marcações dividem o peso entre os dois níveis
            if n == 0.5:
                conta["N"] += .5; conta["D"] += .5
            elif n == 1.5:
                conta["D"] += .5; conta["S"] += .5
            else:
                conta[{0: "N", 1: "D", 2: "S"}[int(n)]] += 1
        tendencia = tendencia_do_ponto(niveis)[1]
        nomes.append(f"{nome}   {tendencia}")
        for k in perc:
            perc[k].append(round(conta[k] / total * 100))
    fig = go.Figure()
    for k, rotulo in (("S", "Satisfatório"), ("D", "Em desenvolvimento"), ("N", "Necessita de atenção")):
        fig.add_bar(y=nomes, x=perc[k], orientation="h", name=rotulo, marker_color=CORES_NIVEL[k],
                    marker_line_color="#ffffff", marker_line_width=2,
                    text=[f"{v}%" if v >= 8 else "" for v in perc[k]], textposition="inside",
                    insidetextanchor="middle", textfont={"size": 12, "color": TEXTO_NIVEL[k]},
                    hovertemplate="<b>%{y}</b><br>" + rotulo + ": %{x}%<extra></extra>")
    fig.update_layout(
        barmode="stack", height=max(220, 40 * len(nomes) + 80), bargap=0.35,
        margin={"l": 8, "r": 8, "t": 8, "b": 8}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Arial, sans-serif", "size": 11, "color": "#334155"},
        xaxis={"range": [0, 100], "showgrid": False, "showticklabels": False, "zeroline": False},
        yaxis={"automargin": True, "tickfont": {"size": 12, "color": "#142b4a"}},
        legend={"orientation": "h", "y": -0.08, "x": 0, "traceorder": "normal"},
        hoverlabel={"bgcolor": "#142b4a", "font": {"color": "#ffffff"}})
    st.plotly_chart(fig, width="stretch", key=chave, config={"displayModeBar": False, "responsive": True})
    st.caption("Tendência: compara os 3 primeiros com os 3 últimos atendimentos de cada ponto, pela ordem da "
               "escala (Necessita de atenção → Em desenvolvimento → Satisfatório). Não é nota.")


def grafico_dificuldades(df_aluno, col_dificuldades, prefixo):
    """Em quantos atendimentos cada dificuldade apareceu, com as cores da logo.

    Anotações livres que aparecem uma única vez são agrupadas em "Outras" para não
    poluir o gráfico (quando já existem dificuldades recorrentes).
    """
    contagem = dividir_categorias(df_aluno[col_dificuldades])
    if contagem.empty:
        return
    total = int(limpar_respostas(df_aluno[col_dificuldades]).shape[0]) or len(df_aluno)
    if (contagem >= 2).any():
        unicas = contagem[contagem < 2]
        contagem = contagem[contagem >= 2]
        if not unicas.empty:
            contagem = pd.concat([contagem, pd.Series({"Outras": int(unicas.sum())})])
    df_dif = contagem.rename_axis("Dificuldade").reset_index(name="Atendimentos")
    df_dif["Rótulo"] = df_dif["Atendimentos"].map(lambda n: f"{n} de {total} · {round(n / total * 100)}%")
    st.subheader("🎯 Dificuldades apresentadas")
    exibir_grafico_barras_fino(df_dif, "Dificuldade", "Atendimentos",
                               f"Em quantos atendimentos cada dificuldade apareceu (de {total})",
                               f"{prefixo}_graf_dif", cores=PALETA_LOGO, texto="Rótulo")


def renderizar_analise_desempenho(df_aluno, indicadores, nome_aluno, prefixo, publico=False):
    """Análise qualitativa reutilizada na tela interna e no portal da família.

    publico=True oculta a tabela bruta da planilha e a exportação CSV, para que
    a família veja apenas os indicadores consolidados.
    """
    col_data = localizar_coluna(df_aluno, ("data",), excluir=("carimbo",))
    # Coluna "Aprendizagem - demonstrou compreensão do CONTEÚDO?". Antes a busca só por "compreensão"
    # pegava "[Compreensão das orientações]" (um dos 6 pontos) e o gráfico mostrava dados errados.
    col_compreensao = (localizar_coluna(df_aluno, ("compreens", "conte"), excluir=("orienta",))
                       or localizar_coluna(df_aluno, ("demonstrou",))
                       or localizar_coluna(df_aluno, ("compreens",), excluir=("orienta", "[")))
    col_dificuldades = localizar_coluna(df_aluno, ("dificuldades",))
    col_conteudo = localizar_coluna(df_aluno, ("conteúdo trabalhado",)) or localizar_coluna(df_aluno, ("conteudo trabalhado",))

    datas = (pd.to_datetime(df_aluno[col_data], dayfirst=True, errors="coerce").dropna()
             if col_data else pd.Series(dtype="datetime64[ns]"))
    c1, c2, c3 = st.columns(3)
    c1.metric("Atendimentos registrados", len(df_aluno))
    c2.metric("Primeiro atendimento", datas.min().strftime("%d/%m/%Y") if not datas.empty else "—")
    c3.metric("Atendimento mais recente", datas.max().strftime("%d/%m/%Y") if not datas.empty else "—")

    if not publico:
        with st.expander("📋 Registros importados do aluno", expanded=False):
            tabela = preparar_datas_planilha(df_aluno)
            st.dataframe(tabela, width="stretch", hide_index=True)
            nome_arquivo = re.sub(r"[^0-9A-Za-z]+", "_", nome_aluno).strip("_").lower() or "aluno"
            st.download_button("Exportar registros deste aluno (CSV)",
                               data=tabela.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"desempenho_{nome_arquivo}.csv", mime="text/csv",
                               key=f"{prefixo}_csv")

    escolhas = [c for c in indicadores if not limpar_respostas(df_aluno[c]).empty]
    if escolhas or col_compreensao:
        linhas, datas_mapa = montar_mapa_pontos(df_aluno, escolhas, col_data, col_compreensao)
        st.subheader("🗺️ Mapa dos pontos avaliados")
        st.caption("Cada quadrado é um ponto avaliado num atendimento, em ordem de data.")
        grafico_mapa_pontos(linhas, datas_mapa, f"{prefixo}_mapa")
        if escolhas:
            st.subheader("📊 Retrato de cada ponto")
            grafico_retrato_pontos(linhas, f"{prefixo}_retrato")
    else:
        st.info("Ainda não há indicadores de participação preenchidos.")

    if col_dificuldades:
        grafico_dificuldades(df_aluno, col_dificuldades, prefixo)

    if escolhas:
        with st.expander("🔎 Detalhar um ponto"):
            indicador_sel = st.selectbox("Ponto avaliado", escolhas, key=f"{prefixo}_indicador",
                                         format_func=nome_curto_indicador)
            contagem = (limpar_respostas(df_aluno[indicador_sel]).value_counts()
                        .rename_axis("Classificação").reset_index(name="Quantidade"))
            exibir_grafico_barras_fino(contagem, "Classificação", "Quantidade",
                                       f"Classificações — {nome_curto_indicador(indicador_sel)}", f"{prefixo}_graf_class")
        if col_data and not publico:
            with st.expander("📋 Tabela de evolução por atendimento"):
                df_ev = df_aluno.copy()
                df_ev["Data do atendimento"] = pd.to_datetime(df_ev[col_data], dayfirst=True, errors="coerce")
                df_ev = df_ev.dropna(subset=["Data do atendimento"]).sort_values("Data do atendimento")
                tabela_ev = df_ev[["Data do atendimento"] + escolhas].copy()
                tabela_ev["Data do atendimento"] = tabela_ev["Data do atendimento"].dt.strftime("%d/%m/%Y")
                tabela_ev.columns = ["Data do atendimento"] + [nome_curto_indicador(c) for c in escolhas]
                st.dataframe(tabela_ev, width="stretch", hide_index=True)

    if col_compreensao:
        comp = limpar_respostas(df_aluno[col_compreensao])
        if not comp.empty:
            st.subheader("🧠 Compreensão do conteúdo")
            comp_count = comp.value_counts().rename_axis("Resposta").reset_index(name="Quantidade")
            exibir_grafico_barras_fino(comp_count, "Resposta", "Quantidade",
                                       "Respostas sobre compreensão", f"{prefixo}_graf_comp")

    if col_conteudo:
        conteudos = limpar_respostas(df_aluno[col_conteudo])
        if not conteudos.empty:
            with st.expander("📚 Conteúdos trabalhados"):
                for idx, conteudo in enumerate(conteudos, start=1):
                    st.markdown(f"**Atendimento {idx}:** {conteudo}")


def _analise_interna(alunos, link_planilha):
    mapa = {rotulo_aluno(a): a for a in alunos}
    selecionado = st.selectbox("Aluno para análise", list(mapa), key="desempenho_aluno")
    aluno = mapa[selecionado]
    if st.button("🔄 Atualizar dados da planilha"):
        carregar_planilha_observacao_atendimento.clear()
    with st.spinner("Lendo a planilha mestre..."):
        df = carregar_planilha_observacao_atendimento(link_planilha)
    if df is None:
        st.error("Não foi possível ler a planilha. Confira se o link está correto e se a planilha permite leitura pelo link.")
        return
    if df.empty:
        st.warning("A aba foi lida, mas não contém registros.")
        return
    df_aluno, indicadores = filtrar_e_analisar_aluno(df, aluno.nome)
    if df_aluno.empty:
        col_nome = localizar_coluna(df, ("nome", "aluno")) or localizar_coluna(df, ("nome",))
        st.warning(f"Nenhum registro encontrado para {aluno.nome}. Confira a grafia do nome na coluna '{col_nome or 'Nome'}'.")
        with st.expander("Diagnóstico da importação"):
            st.write(f"Linhas importadas: {len(df)}")
            st.code("\n".join(str(c) for c in df.columns))
        return
    st.success(f"{len(df_aluno)} registro(s) encontrado(s) para {aluno.nome}.")
    renderizar_analise_desempenho(df_aluno, indicadores, aluno.nome, "interno")


def tela_links_familiares(db, usuario, alunos):
    cfg = carregar_configuracoes(db)
    # Usa a URL cadastrada; se não houver, detecta o endereço pelo qual o sistema está aberto.
    app_url = cfg.get("app_url", "") or detectar_url_base()
    local = eh_endereco_local(app_url)
    st.markdown(
        "Gere um **link individual por aluno** para a família acompanhar, sem login. Você escolhe o que ela vê: "
        "**📓 Caderno Digital** (só registros marcados com 👪), **📈 Desempenho** (mapa dos pontos, retrato, "
        "dificuldades, compreensão) e **📁 Atividades**. "
        "**Prontuário, hipóteses, anotações internas e financeiro nunca aparecem.**"
    )
    if not app_url:
        st.warning("Não foi possível identificar o endereço do sistema. Cadastre a URL pública em ⚙️ Configurações "
                   "(ex.: https://espacodinamico.streamlit.app).")
    elif local:
        st.warning(f"O sistema está rodando no seu computador ({app_url}). Os links gerados aqui servem para **testar**, "
                   "mas só abrem nesta máquina. Para a família acessar, publique o app (Streamlit Cloud) e gere o link por lá.")

    mapa = {f"{a.id} — {a.nome}": a for a in alunos}
    with st.form("f_gerar_link_familiar"):
        aluno_sel = st.selectbox("Aluno", list(mapa))
        validade = st.selectbox("Validade", [30, 90, 180, 365], index=2, format_func=lambda d: f"{d} dias")
        st.markdown("**O que a família vê neste link**")
        s1, s2, s3 = st.columns(3)
        escolha_secoes = {"ver_caderno": s1.checkbox(SECOES_PORTAL["ver_caderno"], value=True),
                          "ver_desempenho": s2.checkbox(SECOES_PORTAL["ver_desempenho"], value=True),
                          "ver_atividades": s3.checkbox(SECOES_PORTAL["ver_atividades"], value=True)}
        revogar = st.checkbox("Revogar links anteriores deste aluno", value=True)
        gerar = st.form_submit_button("Gerar link", type="primary")
    if gerar and not any(escolha_secoes.values()):
        st.error("Marque pelo menos uma seção para a família ver.")
        gerar = False
    if gerar:
        aluno = mapa[aluno_sel]
        try:
            token = gerar_link_familiar(db, aluno.id, validade, usuario.nome, revogar, escolha_secoes)
        except SQLAlchemyError as exc:
            db.rollback()
            mensagem_erro(exc, "geração do link")
        else:
            st.session_state["ultimo_link_gerado"] = {
                "aluno_id": aluno.id, "aluno": aluno.nome,
                "url": montar_url_portal(app_url, token),
                "validade": para_str_br(date.today() + timedelta(days=validade)),
            }
            registrar_auditoria("link_familiar_gerado", f"aluno_id={aluno.id}; validade={validade} dias; secoes="
                                + ",".join(c for c, v in escolha_secoes.items() if v), usuario.nome)

    gerado = st.session_state.get("ultimo_link_gerado")
    if gerado:
        st.success(f"Link gerado para {gerado['aluno']} — válido até {gerado['validade']}.")
        st.code(gerado["url"], language=None)
        st.caption("Copie agora (ícone no canto do quadro): por segurança o sistema guarda apenas uma impressão "
                   "criptográfica do link e não consegue exibi-lo de novo. Se perder, gere outro.")
        aluno_obj = db.get(Aluno, gerado["aluno_id"])
        telefone = aluno_obj.responsavel.telefone if aluno_obj and aluno_obj.responsavel else ""
        if gerado["url"].startswith("http"):
            st.link_button("👁️ Abrir o portal da família (testar)", gerado["url"])
        if app_url and not local:
            texto = (f"Olá! Segue o link para acompanhar o desenvolvimento de {gerado['aluno']} "
                     f"no {cfg['nome_instituicao']}: {gerado['url']} (válido até {gerado['validade']}). "
                     "Este link é pessoal, por favor não compartilhe.")
            wa = link_whatsapp(telefone, texto)
            if wa:
                st.link_button("📲 Enviar ao responsável pelo WhatsApp", wa)

    st.divider()
    st.subheader("Links emitidos")
    links = (db.query(LinkFamiliar).options(joinedload(LinkFamiliar.aluno))
             .order_by(LinkFamiliar.criado_em.desc()).limit(200).all())
    if not links:
        st.info("Nenhum link emitido até agora.")
        return
    hoje = date.today()

    def situacao(link):
        if not link.ativo:
            return "Revogado"
        return "Expirado" if link.expira_em < hoje else "Ativo"

    st.dataframe(pd.DataFrame([{
        "ID": l.id, "Aluno": l.aluno.nome if l.aluno else "-", "Criado em": formatar_data_hora(l.criado_em),
        "Válido até": para_str_br(l.expira_em), "Situação": situacao(l), "Acessos": l.acessos or 0,
        "Último acesso": formatar_data_hora(l.ultimo_acesso) if l.ultimo_acesso else "-",
        "Família vê": " · ".join(r.split(" ", 1)[1] for r in secoes_do_link(l)) or "-",
        "Criado por": l.criado_por or "-",
    } for l in links]), width="stretch", hide_index=True)
    ativos = [l for l in links if situacao(l) == "Ativo"]
    if ativos:
        st.markdown("##### ⚙️ Mudar o que a família vê (sem gerar novo link)")
        op_edit = {f"#{l.id} — {l.aluno.nome if l.aluno else '-'} — até {para_str_br(l.expira_em)}": l.id for l in ativos}
        link_ed = db.get(LinkFamiliar, op_edit[st.selectbox("Link ativo", list(op_edit), key="secoes_link_sel")])
        with st.form(f"f_secoes_link_{link_ed.id}"):
            e1, e2, e3 = st.columns(3)
            novas = {"ver_caderno": e1.checkbox(SECOES_PORTAL["ver_caderno"], value=bool(link_ed.ver_caderno)),
                     "ver_desempenho": e2.checkbox(SECOES_PORTAL["ver_desempenho"], value=bool(link_ed.ver_desempenho)),
                     "ver_atividades": e3.checkbox(SECOES_PORTAL["ver_atividades"], value=bool(link_ed.ver_atividades))}
            salvar_secoes = st.form_submit_button("Salvar o que a família vê", type="primary")
        if salvar_secoes:
            if not any(novas.values()):
                st.error("Marque pelo menos uma seção.")
            else:
                try:
                    for campo, valor in novas.items():
                        setattr(link_ed, campo, 1 if valor else 0)
                    db.commit()
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "alteração do link")
                else:
                    registrar_auditoria("link_familiar_secoes", f"link_id={link_ed.id}; secoes="
                                        + ",".join(c for c, v in novas.items() if v), usuario.nome)
                    st.success("Pronto: a família já vê a nova configuração no mesmo link.")
                    st.rerun()
        st.markdown("##### 🚫 Revogar um link")
        opcoes = {f"#{l.id} — {l.aluno.nome if l.aluno else '-'} — até {para_str_br(l.expira_em)}": l.id for l in ativos}
        escolha = st.selectbox("Revogar um link ativo", list(opcoes), key="revogar_link_sel")
        if st.button("Revogar link selecionado", key="revogar_link_btn"):
            link = db.get(LinkFamiliar, opcoes[escolha])
            try:
                link.ativo = 0
                db.commit()
            except SQLAlchemyError as exc:
                db.rollback()
                mensagem_erro(exc, "revogação do link")
            else:
                registrar_auditoria("link_familiar_revogado", f"link_id={link.id}", usuario.nome)
                st.success("Link revogado. A família deixa de ter acesso imediatamente.")
                st.rerun()


def tela_desempenho(db, usuario):
    st.title("Desempenho e acompanhamento")
    st.caption("Análise qualitativa por aluno e links individuais para as famílias.")
    link_atual = obter_link_planilha(db)
    with st.expander("⚙️ Planilha mestre (Google Sheets)", expanded=not link_atual):
        with st.form("f_mestre"):
            st.write("Link da planilha mestre do Google Sheets. A aba esperada é OBSERVAÇÃO DO ATENDIMENTO.")
            novo_link = st.text_input("Link da planilha", value=link_atual or "")
            salvar = st.form_submit_button("Salvar configuração", type="primary")
        if salvar:
            if novo_link.strip() and "docs.google.com/spreadsheets" not in novo_link:
                st.error("Informe um link válido do Google Sheets.")
            else:
                try:
                    cfg = db.query(ConfiguracaoSistema).filter_by(chave="link_planilha_mestre").first()
                    if cfg:
                        cfg.valor = novo_link.strip()
                    else:
                        db.add(ConfiguracaoSistema(chave="link_planilha_mestre", valor=novo_link.strip()))
                    db.commit()
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "configuração da planilha")
                else:
                    carregar_planilha_observacao_atendimento.clear()
                    st.success("Configuração salva.")
                    st.rerun()
    todos = db.query(Aluno).order_by(Aluno.ativo.desc(), Aluno.nome).all()
    alunos = [a for a in todos if a.ativo]   # links para famílias: só alunos ativos
    if not todos:
        st.info("Cadastre alunos antes de consultar indicadores.")
        return
    tab_analise, tab_links = st.tabs(["📊 Análise por aluno", "🔗 Links para as famílias"])
    with tab_analise:
        incluir = st.checkbox("Incluir alunos inativos", key="desempenho_inativos")
        lista = todos if incluir else alunos
        if not lista:
            st.info("Não há alunos ativos. Marque “Incluir alunos inativos” para consultar o histórico.")
        elif link_atual:
            _analise_interna(lista, link_atual)
        else:
            st.info("Configure a planilha mestre para consultar os indicadores.")
    with tab_links:
        if alunos:
            tela_links_familiares(db, usuario, alunos)
        else:
            st.info("Links para as famílias só podem ser gerados para alunos ativos.")


MAX_PAGINAS_VISUALIZACAO = 15


def visualizar_pdf_inline(caminho, sha256, nome_arquivo, prefixo):
    """Mostra as páginas do PDF como imagens DENTRO do sistema e oferece o download.

    Não depende de link externo nem de nova aba (que celulares e o navegador do WhatsApp
    costumam bloquear). O arquivo é lido do Storage privado só no servidor.
    """
    try:
        with st.spinner("Abrindo o arquivo…"):
            conteudo = pdf_do_material(caminho, sha256)
            total = contar_paginas_pdf(conteudo)
    except Exception as exc:
        print(f"[ERRO] visualização do PDF {caminho}: {exc}")
        st.warning("Não foi possível abrir o arquivo agora. Tente novamente em instantes.")
        return False
    st.download_button("⬇️ Baixar o PDF", data=conteudo, file_name=nome_arquivo or "documento.pdf",
                       mime="application/pdf", key=f"{prefixo}_baixar", width="stretch")
    for n in range(1, min(total, MAX_PAGINAS_VISUALIZACAO) + 1):
        try:
            jpeg, _, _ = imagem_pagina(caminho, sha256, n)
        except Exception as exc:
            print(f"[ERRO] página {n} de {caminho}: {exc}")
            st.warning(f"Não foi possível mostrar a página {n}. Use o botão de download.")
            break
        st.image(jpeg, caption=f"Página {n} de {total}" if total > 1 else None, width="stretch")
    if total > MAX_PAGINAS_VISUALIZACAO:
        st.caption(f"Mostrando {MAX_PAGINAS_VISUALIZACAO} de {total} páginas. Baixe o PDF para ver todas.")
    return True


def links_ativos_do_aluno(db, aluno_id):
    hoje = date.today()
    return (db.query(LinkFamiliar).filter(LinkFamiliar.aluno_id == aluno_id, LinkFamiliar.ativo == 1,
                                          LinkFamiliar.expira_em >= hoje)
            .order_by(LinkFamiliar.criado_em.desc()).all())


def bloco_link_familia(db, usuario, aluno, prefixo):
    """Situação do acesso da família ao portal + gerar/enviar link sem sair da tela."""
    cfg = carregar_configuracoes(db)
    app_url = cfg.get("app_url", "") or detectar_url_base()
    ativos = links_ativos_do_aluno(db, aluno.id)
    if ativos:
        l = ativos[0]
        secoes = " · ".join(secoes_do_link(l)) or "nada"
        st.success(f"🔗 A família de {aluno.nome} tem link ativo até {para_str_br(l.expira_em)} "
                   f"(aberto {l.acessos or 0} vez(es)). Ela vê: {secoes}.")
        if not l.ver_caderno:
            st.warning("Este link **não mostra o Caderno Digital**. Para liberar: 📈 Desempenho → 🔗 Links para as "
                       "famílias → Mudar o que a família vê.")
        rotulo = "Gerar um novo link (a família perdeu o anterior)"
    else:
        st.warning(f"⚠️ A família de {aluno.nome} ainda **não tem link** para o portal: sem ele, ela não vê nada.")
        rotulo = "🔗 Gerar link da família (180 dias)"
    chave = f"{prefixo}_link_gerado_{aluno.id}"
    if st.button(rotulo, key=f"{prefixo}_gerar_link_{aluno.id}", type="secondary" if ativos else "primary"):
        try:
            token = gerar_link_familiar(db, aluno.id, 180, usuario.nome, revogar_anteriores=True)
        except SQLAlchemyError as exc:
            db.rollback()
            mensagem_erro(exc, "geração do link")
        else:
            registrar_auditoria("link_familiar_gerado", f"aluno_id={aluno.id}; validade=180 dias; origem=caderno",
                                usuario.nome)
            st.session_state[chave] = {"url": montar_url_portal(app_url, token),
                                       "validade": para_str_br(date.today() + timedelta(days=180))}
            st.rerun()
    gerado = st.session_state.get(chave)
    if gerado:
        st.code(gerado["url"], language=None)
        st.caption("Copie agora (ícone no canto): por segurança o sistema não consegue mostrar este link de novo.")
        b1, b2 = st.columns(2)
        if gerado["url"].startswith("http"):
            b1.link_button("👁️ Abrir o portal (testar)", gerado["url"], width="stretch")
        telefone = aluno.responsavel.telefone if aluno.responsavel else ""
        texto = (f"Olá! Segue o link para acompanhar o caderno e o desenvolvimento de {aluno.nome} no "
                 f"{cfg['nome_instituicao']}: {gerado['url']} (válido até {gerado['validade']}). "
                 "Este link é pessoal, por favor não compartilhe.")
        wa = link_whatsapp(telefone, texto) if not eh_endereco_local(gerado["url"]) else None
        if wa:
            b2.link_button("📲 Enviar pelo WhatsApp", wa, width="stretch")
        elif eh_endereco_local(gerado["url"]):
            b2.caption("Link de teste (endereço local): só abre neste computador.")
        else:
            b2.caption("Cadastre o telefone do responsável para enviar pelo WhatsApp.")


def renderizar_caderno_portal(db, link, aluno):
    """Caderno Digital no portal: SOMENTE registros ativos marcados como visíveis à família."""
    st.subheader("📓 Caderno Digital")
    registros = (db.query(DocumentoAluno)
                 .filter(DocumentoAluno.aluno_id == aluno.id, DocumentoAluno.status == "Ativo",
                         DocumentoAluno.visivel_familia == 1)
                 .order_by(DocumentoAluno.criado_em.desc(), DocumentoAluno.id.desc())
                 .limit(100).all())
    if not registros:
        st.info("Ainda não há registros no caderno. Assim que a profissional compartilhar, eles aparecem aqui.")
        return
    storage_ok = obter_config_storage() is not None
    categorias = sorted({r.categoria for r in registros})
    filtro = st.selectbox("Mostrar", ["Tudo"] + categorias, key="portal_caderno_filtro") if len(categorias) > 1 else "Tudo"
    for reg in registros:
        if filtro != "Tudo" and reg.categoria != filtro:
            continue
        with st.container(border=True):
            st.markdown(f"**{html.escape(reg.titulo)}**")
            st.caption(f"{para_str_br(reg.criado_em)} · {reg.categoria}")
            if reg.mensagem_familia:
                st.markdown(html.escape(reg.mensagem_familia).replace("\n", "  \n"))
            if not storage_ok:
                continue
            chave = f"portal_ver_doc_{reg.id}"
            aberto = bool(st.session_state.get(chave))
            if st.button("🔼 Fechar" if aberto else "📄 Ver a atividade", key=f"btn_{chave}"):
                st.session_state[chave] = not aberto
                if not aberto and not st.session_state.get(f"{chave}_contado"):
                    # Conta uma visualização por sessão (não a cada clique).
                    try:
                        reg.visualizacoes_familia = (reg.visualizacoes_familia or 0) + 1
                        db.commit()
                    except SQLAlchemyError:
                        db.rollback()
                    registrar_auditoria("portal_caderno_aberto", f"link_id={link.id}; documento_id={reg.id}",
                                        usuario="Família")
                    st.session_state[f"{chave}_contado"] = True
                st.rerun()
            if aberto:
                visualizar_pdf_inline(reg.caminho_storage, reg.sha256, reg.nome_original, f"portal_doc_{reg.id}")


def renderizar_portal_familiar(db, token, logo, cfg):
    """Página pública acessada pelo link individual (?portal=TOKEN), sem login."""
    aplicar_estilo_global()
    st.markdown(
        "<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl'],"
        "[data-testid='collapsedControl']{display:none !important;}</style>",
        unsafe_allow_html=True)
    cabecalho(logo, cfg)
    link = validar_token_portal(db, token)
    if not link:
        st.error("Este link é inválido, expirou ou foi revogado.")
        st.info(f"Solicite um novo link a {cfg['profissional_responsavel']}.")
        return
    aluno = link.aluno
    chave_acesso = f"portal_acesso_registrado_{link.id}"
    if not st.session_state.get(chave_acesso):
        try:
            link.acessos = (link.acessos or 0) + 1
            link.ultimo_acesso = datetime.now()
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        registrar_auditoria("portal_familiar_acesso", f"link_id={link.id}; aluno_id={aluno.id}", usuario="Família")
        st.session_state[chave_acesso] = True

    st.header(f"Acompanhamento de {aluno.nome}")  # header: título menor, sem quebrar palavra no celular
    st.caption(f"Link pessoal válido até {para_str_br(link.expira_em)}. Por favor, não compartilhe.")

    # Só as seções liberadas para ESTE link (parametrizado por aluno na tela de links).
    secoes = [(campo, rot) for campo, rot in SECOES_PORTAL.items() if getattr(link, campo, 1)]
    if not secoes:
        st.info("Nada foi liberado neste link ainda. Fale com a profissional.")
    abas = st.tabs([rot for _, rot in secoes]) if len(secoes) > 1 else [st.container() for _ in secoes]
    for (campo, _), aba in zip(secoes, abas):
        with aba:
            if campo == "ver_caderno":
                renderizar_caderno_portal(db, link, aluno)
            elif campo == "ver_desempenho":
                st.subheader("📈 Desempenho nos atendimentos")
                link_planilha = obter_link_planilha(db)
                df = carregar_planilha_observacao_atendimento(link_planilha) if link_planilha else None
                df_aluno, indicadores = (filtrar_e_analisar_aluno(df, aluno.nome)
                                         if df is not None and not df.empty else (pd.DataFrame(), []))
                if df_aluno.empty:
                    st.info("Os registros de atendimento ainda não estão disponíveis. Volte em breve.")
                else:
                    renderizar_analise_desempenho(df_aluno, indicadores, aluno.nome, "portal", publico=True)
            elif campo == "ver_atividades":
                st.subheader("📁 Atividades pedagógicas")
                atividades = (db.query(AtividadeAluno)
                              # "status != 'Cancelada'" descarta NULL no SQL; o or_ mantém esses registros.
                              .filter(AtividadeAluno.aluno_id == aluno.id,
                                      or_(AtividadeAluno.status.is_(None), AtividadeAluno.status != "Cancelada"))
                              .order_by(AtividadeAluno.data_atividade.desc(), AtividadeAluno.id.desc())
                              .limit(50).all())
                if atividades:
                    st.dataframe(pd.DataFrame([{
                        "Data": para_str_br(a.data_atividade), "Atividade": a.titulo,
                        "Área": a.area or a.categoria or "-", "Situação": normalizar_status_atividade(a.status),
                        "Objetivo": a.objetivo or "-",
                    } for a in atividades]), width="stretch", hide_index=True)
                else:
                    st.info("Ainda não há atividades registradas.")
    st.divider()
    st.caption(f"{cfg['nome_instituicao']} · {cfg['profissional_responsavel']} · {cfg['titulo_profissional']}. "
               "Em caso de dúvidas, fale diretamente com a profissional.")


MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def numero_br(valor, casas=2):
    return f"{float(valor or 0):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def lancamentos_do_ano(db, ano, regime):
    """DataFrame dos lançamentos não cancelados do ano.

    regime "caixa": pagos, pela data de pagamento. "competencia": todos, pela data de vencimento.
    """
    L = LancamentoFinanceiro
    inicio, fim = date(ano, 1, 1), date(ano, 12, 31)
    q = db.query(L).options(joinedload(L.aluno)).filter(or_(L.status.is_(None), L.status != "Cancelado"))
    if regime == "caixa":
        q = q.filter(L.status == "Pago", L.data_pagamento.between(inicio, fim))
    else:
        q = q.filter(L.data_vencimento.between(inicio, fim))
    linhas = []
    for l in q.all():
        data_ref = l.data_pagamento if regime == "caixa" else l.data_vencimento
        linhas.append({
            "id": l.id, "tipo": l.tipo or "-", "categoria": (l.categoria or "").strip() or "Geral",
            "servico": (l.servico or "").strip() or "Não informado", "aluno": l.aluno.nome if l.aluno else "Sem aluno",
            "descricao": l.descricao, "valor": float(l.valor or 0), "mes": data_ref.month, "status": l.status or "Pendente",
            "vencimento": l.data_vencimento, "pagamento": l.data_pagamento,
        })
    return pd.DataFrame(linhas, columns=["id", "tipo", "categoria", "servico", "aluno", "descricao", "valor", "mes",
                                         "status", "vencimento", "pagamento"])


def pivo_mensal(df, tipo):
    """Categoria × mês (1..12) para um tipo (Receita/Despesa)."""
    base = df[df["tipo"] == tipo]
    if base.empty:
        return pd.DataFrame(columns=list(range(1, 13)))
    pv = base.pivot_table(index="categoria", columns="mes", values="valor", aggfunc="sum", fill_value=0.0)
    pv = pv.reindex(columns=range(1, 13), fill_value=0.0)
    return pv.loc[pv.sum(axis=1).sort_values(ascending=False).index]


def html_dre_anual(rec, desp, ano, regime_txt, ate_mes=12):
    """DRE anual em tabela: categorias nas linhas, meses nas colunas, total e participação."""
    esc = html.escape
    tot_r = rec.sum(axis=0) if not rec.empty else pd.Series(0.0, index=range(1, 13))
    tot_d = desp.sum(axis=0) if not desp.empty else pd.Series(0.0, index=range(1, 13))
    resultado = tot_r - tot_d
    acumulado = resultado.cumsum()
    total_r, total_d = float(tot_r.sum()), float(tot_d.sum())

    def cel(v, classe=""):
        v = float(v or 0)
        txt = "–" if abs(v) < 0.005 else numero_br(v)
        cls = classe + (" neg" if v < -0.005 else "")
        return f'<td class="{cls.strip()}">{txt}</td>'

    cab = "".join(f"<th>{m}</th>" for m in MESES_ABREV)
    linhas = [f'<tr class="cab"><th class="cat">Categoria</th>{cab}<th>Total</th><th>%</th></tr>']

    def bloco(titulo, pv, total, classe_total):
        out = [f'<tr class="grupo"><td class="cat" colspan="15">{esc(titulo)}</td></tr>']
        for cat, linha in pv.iterrows():
            t = float(linha.sum())
            pct = f"{t / total * 100:.1f}%".replace(".", ",") if total else "–"
            out.append(f'<tr><td class="cat det">{esc(str(cat))}</td>' + "".join(cel(v) for v in linha)
                       + cel(t, "tot") + f"<td>{pct}</td></tr>")
        tot = pv.sum(axis=0) if not pv.empty else pd.Series(0.0, index=range(1, 13))
        out.append(f'<tr class="{classe_total}"><td class="cat">Total</td>' + "".join(cel(v) for v in tot)
                   + cel(total, "tot") + "<td>100%</td></tr>")
        return out

    linhas += bloco("RECEITAS", rec, total_r, "subtotal")
    linhas += bloco("(−) DESPESAS", desp, total_d, "subtotal menos")
    linhas.append('<tr class="resultado"><td class="cat">(=) RESULTADO</td>' + "".join(cel(v) for v in resultado)
                  + cel(total_r - total_d, "tot") + "<td></td></tr>")
    # Meses que ainda não chegaram (ano corrente) não recebem acumulado nem margem.
    linhas.append('<tr class="acum"><td class="cat">Resultado acumulado</td>'
                  + "".join(cel(v) if m <= ate_mes else "<td></td>" for m, v in zip(range(1, 13), acumulado))
                  + "<td></td><td></td></tr>")
    margens = "".join(f"<td>{(f'{(r - d) / r * 100:.0f}%'.replace('.', ',')) if r and m <= ate_mes else '–'}</td>"
                      for m, r, d in zip(range(1, 13), tot_r, tot_d))
    margem_ano = f"{(total_r - total_d) / total_r * 100:.1f}%".replace(".", ",") if total_r else "–"
    linhas.append(f'<tr class="acum"><td class="cat">Margem</td>{margens}<td class="tot">{margem_ano}</td><td></td></tr>')
    return (f'<div class="ed-dre-anual"><div class="ed-dre-titulo">DRE {ano} — {esc(regime_txt)}</div>'
            f'<div class="rolagem"><table>{"".join(linhas)}</table></div></div>')


def grafico_mensal_resultado(rec, desp, chave, ate_mes=12):
    tot_r = (rec.sum(axis=0) if not rec.empty else pd.Series(0.0, index=range(1, 13))).tolist()
    tot_d = (desp.sum(axis=0) if not desp.empty else pd.Series(0.0, index=range(1, 13))).tolist()
    tot_r, tot_d, meses = tot_r[:ate_mes], tot_d[:ate_mes], MESES_ABREV[:ate_mes]
    resultado = [r - d for r, d in zip(tot_r, tot_d)]
    fig = go.Figure()
    fig.add_bar(x=meses, y=tot_r, name="Receita", marker_color="#7cc2b2",
                hovertemplate="%{x}: R$ %{y:,.2f}<extra>Receita</extra>")
    fig.add_bar(x=meses, y=tot_d, name="Despesa", marker_color="#e7776c",
                hovertemplate="%{x}: R$ %{y:,.2f}<extra>Despesa</extra>")
    fig.add_scatter(x=meses, y=resultado, name="Resultado do mês", mode="lines+markers",
                    line={"color": "#142b4a", "width": 2}, marker={"size": 7},
                    hovertemplate="%{x}: R$ %{y:,.2f}<extra>Resultado</extra>")
    fig.update_layout(barmode="group", height=330, bargap=0.3, bargroupgap=0.08,
                      margin={"l": 8, "r": 8, "t": 10, "b": 8}, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", separators=",.",
                      font={"family": "Arial, sans-serif", "size": 12, "color": "#5b6b80"},
                      legend={"orientation": "h", "y": 1.08, "x": 0},
                      yaxis={"gridcolor": "#e8edf4", "zeroline": True, "zerolinecolor": "#c3cad5", "tickprefix": "R$ "},
                      xaxis={"showgrid": False}, hoverlabel={"bgcolor": "#142b4a", "font": {"color": "#ffffff"}})
    st.plotly_chart(fig, width="stretch", key=chave, config={"displayModeBar": False, "responsive": True})


def tabela_participacao(df, coluna, rotulo, total):
    agg = (df.groupby(coluna)["valor"].agg(["sum", "count"]).sort_values("sum", ascending=False).reset_index())
    agg.columns = [rotulo, "Valor", "Lançamentos"]
    agg["Participação"] = agg["Valor"].map(lambda v: f"{v / total * 100:.1f}%".replace(".", ",") if total else "–")
    agg["Rótulo"] = [f"R$ {numero_br(v)} · {p}" for v, p in zip(agg["Valor"], agg["Participação"])]
    return agg


def previsto_realizado(db, ano):
    """Receitas com vencimento no mês (previsto) x quanto delas já foi pago (recebido)."""
    df = lancamentos_do_ano(db, ano, "competencia")
    df = df[df["tipo"] == "Receita"]
    linhas = []
    hoje = date.today()
    for m in range(1, 13):
        doma = df[df["mes"] == m]
        previsto = float(doma["valor"].sum())
        recebido = float(doma.loc[doma["status"] == "Pago", "valor"].sum())
        atrasado = float(doma.loc[(doma["status"] != "Pago") & (doma["vencimento"] < hoje), "valor"].sum())
        linhas.append({"Mês": MESES_ABREV[m - 1], "Previsto": previsto, "Recebido": recebido,
                       "Em aberto": previsto - recebido, "Em atraso": atrasado,
                       "% recebido": (recebido / previsto * 100) if previsto else None})
    return pd.DataFrame(linhas)


def inadimplencia_atual(db):
    L = LancamentoFinanceiro
    hoje = date.today()
    itens = (db.query(L).options(joinedload(L.aluno))
             .filter(L.tipo == "Receita", L.status == "Pendente", L.data_vencimento < hoje).all())
    por_aluno = {}
    for l in itens:
        nome = l.aluno.nome if l.aluno else "Sem aluno"
        d = por_aluno.setdefault(nome, {"Aluno": nome, "Valor em atraso": 0.0, "Lançamentos": 0, "Mais antigo": l.data_vencimento})
        d["Valor em atraso"] += float(l.valor or 0)
        d["Lançamentos"] += 1
        d["Mais antigo"] = min(d["Mais antigo"], l.data_vencimento)
    df = pd.DataFrame(sorted(por_aluno.values(), key=lambda x: -x["Valor em atraso"]))
    if not df.empty:
        df["Dias de atraso"] = df["Mais antigo"].map(lambda d: (hoje - d).days)
        df["Mais antigo"] = df["Mais antigo"].map(para_str_br)
    return df


def leituras_para_decisao(df, rec, desp, ano, total_r, total_d, recorrente, desp_media, ant, periodo_ant=None):
    """Frases objetivas a partir dos números (sem inventar: só o que os dados mostram)."""
    frases = []
    if total_r or total_d:
        res = total_r - total_d
        frases.append(f"{'Lucro' if res >= 0 else 'Prejuízo'} de **R$ {numero_br(abs(res))}** no período"
                      + (f", margem de **{res / total_r * 100:.1f}%**".replace(".", ",", 1) if total_r else "") + ".")
    tot_r = rec.sum(axis=0) if not rec.empty else None
    if tot_r is not None and tot_r.sum() > 0:
        m = int(tot_r.idxmax())
        frases.append(f"Mês de maior receita: **{MESES[m - 1]}** (R$ {numero_br(tot_r.max())}).")
    if not desp.empty and total_d:
        cat = desp.sum(axis=1).idxmax()
        v = float(desp.sum(axis=1).max())
        frases.append(f"Maior despesa: **{cat}**, {v / total_d * 100:.0f}% de tudo o que saiu (R$ {numero_br(v)}).")
    rec_df = df[df["tipo"] == "Receita"]
    if not rec_df.empty and rec_df["aluno"].nunique() > 1:
        top = rec_df.groupby("aluno")["valor"].sum().sort_values(ascending=False)
        pct = top.iloc[0] / top.sum() * 100
        if pct >= 40:
            frases.append(f"Concentração: **{top.index[0]}** responde por {pct:.0f}% da receita. "
                          "Perder esse aluno teria impacto grande no caixa.")
    if recorrente:
        cobertura = recorrente / desp_media * 100 if desp_media else None
        txt = f"Receita recorrente dos contratos ativos: **R$ {numero_br(recorrente)}/mês**"
        if cobertura is not None:
            txt += (f", cobrindo **{cobertura:.0f}%** da despesa média mensal (R$ {numero_br(desp_media)})."
                    + (" Abaixo de 100%: os contratos sozinhos não pagam as despesas." if cobertura < 100 else ""))
        frases.append(txt + ("" if cobertura is not None else "."))
    if ant and (ant["receita"] or ant["despesa"]):
        def var(a, b):
            return f"{(a - b) / b * 100:+.0f}%" if b else "novo"
        frases.append(f"Comparado a {periodo_ant or ano - 1}: receita {var(total_r, ant['receita'])}, "
                      f"despesa {var(total_d, ant['despesa'])}.")
    return frases


def tela_relatorio_anual(db):
    hoje = date.today()
    c1, c2, c3 = st.columns([1, 2, 2])
    ano = int(c1.number_input("Ano", min_value=2020, max_value=2100, value=hoje.year, step=1, key="rel_ano"))
    regime_txt = c2.radio("Visão", ["Caixa (o que foi pago)", "Competência (o que venceu)"], horizontal=True,
                          key="rel_regime",
                          help="Caixa: pela data de pagamento, só pagos. Competência: pela data de vencimento, "
                               "pagos e pendentes (sem cancelados).")
    regime = "caixa" if regime_txt.startswith("Caixa") else "competencia"
    df = lancamentos_do_ano(db, ano, regime)
    if df.empty:
        st.info(f"Não há lançamentos em {ano} nesta visão.")
        return
    rec, desp = pivo_mensal(df, "Receita"), pivo_mensal(df, "Despesa")
    total_r = float(df.loc[df["tipo"] == "Receita", "valor"].sum())
    total_d = float(df.loc[df["tipo"] == "Despesa", "valor"].sum())
    resultado = total_r - total_d
    meses_mov = int(df["mes"].nunique()) or 1
    desp_media = total_d / meses_mov
    recorrente = float(db.query(func.coalesce(func.sum(Contrato.valor_mensalidade), 0))
                       .filter(Contrato.status == "Ativo").scalar() or 0)
    ano_corrente = ano == hoje.year
    ate_mes = hoje.month if (ano_corrente and regime == "caixa") else 12
    df_ant = lancamentos_do_ano(db, ano - 1, regime)
    if ano_corrente and not df_ant.empty:
        # Ano em andamento: compara jan..mês atual com o mesmo intervalo do ano anterior.
        df_ant = df_ant[df_ant["mes"] <= hoje.month]
    periodo_ant = (f"jan–{MESES_ABREV[hoje.month - 1].lower()}/{ano - 1}" if ano_corrente else str(ano - 1))
    ant = {"receita": float(df_ant.loc[df_ant["tipo"] == "Receita", "valor"].sum()) if not df_ant.empty else 0.0,
           "despesa": float(df_ant.loc[df_ant["tipo"] == "Despesa", "valor"].sum()) if not df_ant.empty else 0.0}

    def delta(atual, anterior):
        return f"{(atual - anterior) / anterior * 100:+.0f}% vs {periodo_ant}" if anterior else None

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Receita do ano", moeda(total_r), delta(total_r, ant["receita"]))
    k2.metric("Despesa do ano", moeda(total_d), delta(total_d, ant["despesa"]), delta_color="inverse")
    k3.metric("Resultado", moeda(resultado),
              delta(resultado, ant["receita"] - ant["despesa"]) if (ant["receita"] - ant["despesa"]) > 0 else None)
    k4.metric("Margem", f"{resultado / total_r * 100:.1f}%".replace(".", ",") if total_r else "–")
    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Receita média/mês", moeda(total_r / meses_mov), help="Média dos meses com movimento.")
    k6.metric("Despesa média/mês", moeda(desp_media))
    mens = df[(df["tipo"] == "Receita") & (df["categoria"] == "Mensalidade")]
    k7.metric("Ticket médio da mensalidade", moeda(mens["valor"].mean()) if not mens.empty else "–")
    k8.metric("Receita recorrente (contratos)", moeda(recorrente), help="Soma das mensalidades dos contratos ativos.")

    st.markdown("##### 💡 Leituras para decisão")
    for frase in leituras_para_decisao(df, rec, desp, ano, total_r, total_d, recorrente, desp_media, ant,
                                       periodo_ant):
        # "$" escapado: dois "R$" na mesma linha viravam fórmula matemática no Markdown do Streamlit.
        st.markdown("- " + frase.replace("$", "\\$"))

    st.markdown("##### Receita, despesa e resultado por mês")
    grafico_mensal_resultado(rec, desp, f"rel_mensal_{ano}_{regime}", ate_mes)

    st.markdown("##### DRE anual por categoria")
    st.markdown(html_dre_anual(rec, desp, ano, regime_txt, ate_mes), unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        receitas = df[df["tipo"] == "Receita"]
        if not receitas.empty:
            por_serv = tabela_participacao(receitas, "servico", "Serviço", total_r)
            exibir_grafico_barras_fino(por_serv, "Serviço", "Valor", "Receita por serviço", f"rel_serv_{ano}",
                                       cores=PALETA_LOGO, texto="Rótulo")
            if (receitas["servico"] == "Não informado").any():
                st.caption("“Não informado”: receitas sem serviço. Mensalidades novas herdam o serviço do contrato; "
                           "nas antigas, informe em ✏️ Consultar e editar.")
    with col_b:
        despesas = df[df["tipo"] == "Despesa"]
        if not despesas.empty:
            por_cat = tabela_participacao(despesas, "categoria", "Categoria", total_d)
            exibir_grafico_barras_fino(por_cat, "Categoria", "Valor", "Despesas por categoria", f"rel_desp_{ano}",
                                       cores=PALETA_LOGO, texto="Rótulo")

    receitas = df[df["tipo"] == "Receita"]
    por_aluno = pd.DataFrame()
    if not receitas.empty:
        st.markdown("##### Receita por aluno")
        por_aluno = tabela_participacao(receitas, "aluno", "Aluno", total_r).drop(columns=["Rótulo"])
        st.dataframe(por_aluno.assign(Valor=por_aluno["Valor"].map(moeda)), width="stretch", hide_index=True)

    st.markdown("##### Previsto × recebido (receitas pelo vencimento)")
    pr = previsto_realizado(db, ano)
    st.dataframe(pr.assign(**{c: pr[c].map(moeda) for c in ("Previsto", "Recebido", "Em aberto", "Em atraso")},
                           **{"% recebido": pr["% recebido"].map(lambda v: f"{v:.0f}%" if pd.notna(v) else "–")}),
                 width="stretch", hide_index=True)

    inad = inadimplencia_atual(db)
    st.markdown("##### Inadimplência hoje")
    if inad.empty:
        st.success("Nenhuma receita em atraso.")
    else:
        st.warning(f"{int(inad['Lançamentos'].sum())} lançamento(s) em atraso, total de "
                   f"{moeda(inad['Valor em atraso'].sum())}.")
        st.dataframe(inad.assign(**{"Valor em atraso": inad["Valor em atraso"].map(moeda)}),
                     width="stretch", hide_index=True)

    # Exportação: uma planilha por seção, com números (não texto) para a contadora/planilhas.
    from io import BytesIO
    saida = BytesIO()
    nomes_meses = dict(zip(range(1, 13), MESES_ABREV))
    with pd.ExcelWriter(saida, engine="openpyxl") as xl:
        rec.rename(columns=nomes_meses).assign(Total=rec.sum(axis=1)).to_excel(xl, sheet_name="Receitas por mês")
        desp.rename(columns=nomes_meses).assign(Total=desp.sum(axis=1)).to_excel(xl, sheet_name="Despesas por mês")
        tot_r = rec.sum(axis=0) if not rec.empty else pd.Series(0.0, index=range(1, 13))
        tot_d = desp.sum(axis=0) if not desp.empty else pd.Series(0.0, index=range(1, 13))
        pd.DataFrame({"Mês": MESES_ABREV, "Receita": tot_r.values, "Despesa": tot_d.values,
                      "Resultado": (tot_r - tot_d).values, "Acumulado": (tot_r - tot_d).cumsum().values}
                     ).to_excel(xl, sheet_name="Resultado mensal", index=False)
        if not por_aluno.empty:
            por_aluno.to_excel(xl, sheet_name="Receita por aluno", index=False)
        pr.to_excel(xl, sheet_name="Previsto x recebido", index=False)
        if not inad.empty:
            inad.to_excel(xl, sheet_name="Inadimplência", index=False)
        df.drop(columns=["mes"]).to_excel(xl, sheet_name="Lançamentos", index=False)
    st.download_button("⬇️ Baixar relatório completo (Excel)", data=saida.getvalue(),
                       file_name=f"relatorio_financeiro_{ano}_{regime}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=f"rel_excel_{ano}_{regime}", width="stretch")


def tela_financeiro(db):
    st.title("Financeiro — lançamentos")
    resumo = resumo_financeiro(db)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("A receber (em dia)", moeda(resumo["a_receber"]))
    k2.metric("Em atraso", moeda(resumo["em_atraso"]), f"{resumo['qtd_atraso']} lançamento(s)",
              delta_color="inverse" if resumo["qtd_atraso"] else "off")
    k3.metric("Recebido no mês", moeda(resumo["recebido_mes"]))
    k4.metric("Despesas pagas no mês", moeda(resumo["despesas_mes"]))
    alunos = db.query(Aluno).order_by(Aluno.nome).all()
    mapa = {"Sem vínculo com aluno": None}
    mapa.update({f"{a.id} — {a.nome}{'' if a.ativo else ' (inativo)'}": a.id for a in alunos})
    categorias = ["Mensalidade", "Atendimento", "Material", "Aluguel", "Serviços", "Impostos", "Transporte", "Outro"]
    status_opcoes = ["Pendente", "Pago", "Cancelado"]
    servicos = lista_servicos(carregar_configuracoes(db))
    tab1, tab2, tab3 = st.tabs(["➕ Novo lançamento", "✏️ Consultar e editar lançamentos", "📊 Relatório anual"])
    # tab3 primeiro: tab2 encerra a função quando ainda não há lançamentos.
    with tab3:
        tela_relatorio_anual(db)
    with tab1:
        with st.form("f_financeiro_novo", clear_on_submit=True):
            tipo = st.selectbox("Tipo", ["Receita", "Despesa"])
            descricao = st.text_input("Descrição *")
            c_cat, c_serv = st.columns(2)
            categoria = c_cat.selectbox("Categoria", categorias)
            servico = c_serv.selectbox("Serviço (receitas)", servicos, index=None, placeholder="Não se aplica",
                                       help="Usado no relatório anual para separar a receita por serviço.")
            valor = st.number_input("Valor (R$) *", min_value=0.01, value=None, step=10.0, placeholder="Ex.: 350,00")
            vencimento = st.date_input("Data de vencimento", value=date.today(), format="DD/MM/YYYY")
            aluno_label = st.selectbox("Aluno (opcional)", list(mapa))
            c_pag1, c_pag2 = st.columns(2)
            ja_pago = c_pag1.checkbox("Já foi pago", value=False)
            data_pag = c_pag2.date_input("Data do pagamento (se já pago)", value=date.today(), format="DD/MM/YYYY")
            observacao = st.text_area("Observação")
            salvar = st.form_submit_button("Registrar lançamento", type="primary")
        if salvar:
            if not descricao.strip() or not valor:
                st.error("Informe a descrição e o valor.")
            else:
                try:
                    db.add(LancamentoFinanceiro(tipo=tipo, descricao=descricao.strip(), categoria=categoria,
                        servico=servico if tipo == "Receita" else None,
                        valor=float(valor), data_vencimento=vencimento, aluno_id=mapa[aluno_label],
                        observacao=observacao.strip(), status="Pago" if ja_pago else "Pendente",
                        data_pagamento=data_pag if ja_pago else None))
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
        hoje = date.today()

        def situacao_exibida(l):
            if l.status == "Pendente" and l.data_vencimento and l.data_vencimento < hoje:
                return "Em atraso"
            return l.status

        filtro = st.selectbox("Filtrar situação", ["Todas", "Em atraso"] + status_opcoes, key="financeiro_filtro_status")
        if filtro == "Todas":
            filtrados = todos
        elif filtro == "Em atraso":
            filtrados = [l for l in todos if situacao_exibida(l) == "Em atraso"]
        else:
            filtrados = [l for l in todos if l.status == filtro]
        st.dataframe(pd.DataFrame([{
            "ID": l.id, "Tipo": l.tipo, "Descrição": l.descricao, "Categoria": l.categoria,
            "Serviço": l.servico or "-", "Valor": moeda(l.valor), "Vencimento": para_str_br(l.data_vencimento),
            "Pagamento": para_str_br(l.data_pagamento), "Situação": situacao_exibida(l),
            "Aluno": l.aluno.nome if l.aluno else "-"
        } for l in filtrados]), width="stretch", hide_index=True)
        if filtrados:
            opcoes = {f"#{l.id} — {l.tipo} — {l.descricao} — {moeda(l.valor)} — {l.status}": l.id for l in filtrados}
            sel = st.selectbox("Selecione o lançamento para editar", list(opcoes), key="financeiro_editar_sel")
            lanc = db.get(LancamentoFinanceiro, opcoes[sel])
            atual_aluno = next((k for k, v in mapa.items() if v == lanc.aluno_id), "Sem vínculo com aluno")
            with st.form(f"f_editar_lancamento_{lanc.id}"):
                tipo_e = st.selectbox("Tipo", ["Receita", "Despesa"], index=["Receita", "Despesa"].index(lanc.tipo if lanc.tipo in ["Receita", "Despesa"] else "Receita"))
                descricao_e = st.text_input("Descrição", value=lanc.descricao)
                cat_atual = lanc.categoria if lanc.categoria in categorias else "Outro"
                c_cat_e, c_serv_e = st.columns(2)
                categoria_e = c_cat_e.selectbox("Categoria", categorias, index=categorias.index(cat_atual))
                opcoes_serv = opcoes_com_atual(servicos, lanc.servico)
                servico_e = c_serv_e.selectbox("Serviço (receitas)", opcoes_serv,
                                               index=opcoes_serv.index(lanc.servico) if lanc.servico in opcoes_serv else None,
                                               placeholder="Não se aplica")
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
                    lanc.servico = servico_e if tipo_e == "Receita" else None
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
            if lanc.tipo == "Receita" and lanc.status == "Pago":
                try:
                    pdf_recibo = gerar_recibo_pdf(lanc, carregar_configuracoes(db), obter_logo())
                except Exception as exc:
                    mensagem_erro(exc, "geração do recibo")
                else:
                    st.download_button(
                        "🧾 Baixar recibo (PDF)", data=pdf_recibo, file_name=f"recibo_{lanc.id:06d}.pdf",
                        mime="application/pdf", key=f"recibo_{lanc.id}",
                        on_click=registrar_auditoria, args=("recibo_emitido", f"lancamento_id={lanc.id}"))
            elif lanc.tipo == "Receita":
                st.caption("O recibo fica disponível quando a receita estiver com situação **Pago**.")
            st.caption("Não exclua lançamentos pagos para preservar a trilha financeira. Se necessário, marque como Cancelado e registre a justificativa na observação.")
        csv = pd.DataFrame([{
            "ID": l.id, "Tipo": l.tipo, "Descrição": l.descricao, "Categoria": l.categoria,
            "Serviço": l.servico or "", "Valor": l.valor, "Vencimento": para_str_br(l.data_vencimento),
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
        with st.form(f"f_editar_usuario_{usuario.id}"):
            nome = st.text_input("Nome", value=usuario.nome)
            perfil_novo = st.selectbox("Perfil", ["Admin", "Profissional", "Financeiro"],
                index=["Admin", "Profissional", "Financeiro"].index(usuario.perfil if usuario.perfil in ["Admin","Profissional","Financeiro"] else "Admin"))
            ativo = st.checkbox("Usuário ativo", value=bool(usuario.ativo))
            nova_senha = st.text_input("Nova senha (deixe em branco para manter)", type="password")
            salvar = st.form_submit_button("Salvar usuário", type="primary")
        if salvar:
            admins_ativos = db.query(func.count(Usuario.id)).filter(Usuario.perfil == "Admin", Usuario.ativo == 1).scalar() or 0
            deixa_de_ser_admin = usuario.perfil == "Admin" and usuario.ativo and (perfil_novo != "Admin" or not ativo)
            if not nome.strip():
                st.error("Informe o nome.")
            elif nova_senha and len(nova_senha) < 8:
                st.error("A nova senha deve ter pelo menos 8 caracteres.")
            elif deixa_de_ser_admin and admins_ativos <= 1:
                st.error("Este é o único administrador ativo. Cadastre outro administrador antes de inativá-lo ou mudar o perfil.")
            else:
                usuario.nome = nome.strip()
                usuario.perfil = perfil_novo
                usuario.ativo = 1 if ativo else 0
                if nova_senha:
                    usuario.senha_hash = gerar_hash_senha(nova_senha)
                try:
                    db.commit()
                except SQLAlchemyError as exc:
                    db.rollback()
                    mensagem_erro(exc, "edição do usuário")
                    return
                registrar_auditoria("usuario_alterado", f"usuario_id={usuario.id}; perfil={perfil_novo}; "
                                    f"ativo={int(bool(ativo))}; senha_redefinida={bool(nova_senha)}")
                if usuario.id == st.session_state.get("usuario_id") and not usuario.ativo:
                    st.session_state.clear()
                st.success("Usuário atualizado.")
                st.rerun()


def tela_minha_senha(db, usuario, obrigatoria=False):
    st.title("Alterar minha senha")
    if obrigatoria:
        st.warning("Por segurança, defina uma nova senha antes de continuar: a senha atual é a senha padrão ou tem menos de 8 caracteres.")
    with st.form("f_minha_senha", clear_on_submit=True):
        atual = st.text_input("Senha atual", type="password")
        nova = st.text_input("Nova senha (mínimo 8 caracteres)", type="password")
        confirma = st.text_input("Confirme a nova senha", type="password")
        enviar = st.form_submit_button("Salvar nova senha", type="primary")
    if not enviar:
        return
    if not verificar_senha(atual, usuario.senha_hash):
        st.error("A senha atual não confere.")
    elif len(nova) < 8:
        st.error("A nova senha deve ter pelo menos 8 caracteres.")
    elif nova != confirma:
        st.error("A confirmação não confere com a nova senha.")
    elif nova in (atual, SENHA_PADRAO_ADMIN):
        st.error("Escolha uma senha diferente da atual e da senha padrão.")
    else:
        try:
            usuario.senha_hash = gerar_hash_senha(nova)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            mensagem_erro(exc, "alteração da senha")
            return
        st.session_state.pop("trocar_senha_obrigatoria", None)
        registrar_auditoria("senha_alterada", usuario=usuario.nome)
        st.success("Senha alterada.")
        st.rerun()


def tela_configuracoes(db):
    st.title("Configurações institucionais")
    atual = carregar_configuracoes(db)
    with st.form("f_config_institucional"):
        nome_instituicao = st.text_input("Nome da instituição", value=atual["nome_instituicao"])
        profissional = st.text_input("Profissional responsável", value=atual["profissional_responsavel"])
        titulo = st.text_input("Título profissional", value=atual["titulo_profissional"])
        app_url = st.text_input("URL pública da aplicação", value=atual["app_url"],
                                placeholder="https://espacodinamico.streamlit.app",
                                help="Usada para montar os links individuais das famílias.")
        c_doc, c_cid = st.columns(2)
        documento_prof = c_doc.text_input("CPF/CNPJ ou registro profissional (recibos)", value=atual["documento_profissional"],
                                          placeholder="ex.: CNPJ 00.000.000/0001-00")
        cidade = c_cid.text_input("Cidade/UF (recibos)", value=atual["cidade"], placeholder="ex.: Vitória/ES")
        servicos_txt = st.text_area("Serviços oferecidos (um por linha)", value=atual["servicos"],
                                    help="Aparecem como lista suspensa em Contratos e no Financeiro.")
        salvar = st.form_submit_button("Salvar configurações", type="primary")
    if salvar:
        app_url_limpa = app_url.strip().rstrip("/")
        if app_url_limpa and not (app_url_limpa.startswith("https://") or eh_endereco_local(app_url_limpa)):
            st.error("A URL pública deve começar com https://")
        else:
            valores = {
                "nome_instituicao": nome_instituicao.strip(),
                "profissional_responsavel": profissional.strip(),
                "titulo_profissional": titulo.strip(),
                "app_url": app_url_limpa,
                "documento_profissional": documento_prof.strip(),
                "cidade": cidade.strip(),
                "servicos": "\n".join(lista_servicos({"servicos": servicos_txt})),
            }
            try:
                for chave, valor in valores.items():
                    item = db.query(ConfiguracaoSistema).filter_by(chave=chave).first()
                    if item:
                        item.valor = valor
                    else:
                        db.add(ConfiguracaoSistema(chave=chave, valor=valor))
                db.commit()
            except SQLAlchemyError as exc:
                db.rollback()
                mensagem_erro(exc, "gravação das configurações")
            else:
                registrar_auditoria("configuracoes_alteradas")
                st.success("Configurações salvas no banco.")
                st.rerun()
    st.caption("Campos deixados em branco voltam ao valor padrão.")

    with st.expander("🧾 Registro de auditoria (últimos 300 eventos)"):
        logs = db.query(LogAuditoria).order_by(LogAuditoria.data_hora.desc()).limit(300).all()
        if logs:
            st.dataframe(pd.DataFrame([{
                "Data/hora": formatar_data_hora(l.data_hora), "Usuário": l.usuario or "-",
                "Ação": l.acao, "Detalhe": l.detalhe or "",
            } for l in logs]), width="stretch", hide_index=True)
        else:
            st.info("Nenhum evento registrado ainda.")


def main():
    try:
        inicializar_banco(versao_esquema())
    except SQLAlchemyError as exc:
        st.error("Não foi possível inicializar o banco de dados. Verifique a conexão com o PostgreSQL e os Secrets.")
        print(f"[ERRO DATABASE] {exc}")
        st.stop()

    logo = obter_logo()
    db = SessionLocal()
    try:
        cfg = carregar_configuracoes(db)

        # Portal da família: link individual com token aleatório, validade e revogação.
        token_portal = st.query_params.get("portal")
        if token_portal:
            renderizar_portal_familiar(db, token_portal, logo, cfg)
            return

        # Portal legado por nome na URL continua desativado.
        if st.query_params.get("aluno"):
            aplicar_estilo_global()
            st.title("Portal familiar")
            st.warning("O acesso por nome na URL foi desativado por segurança. Solicite à profissional o seu link individual.")
            return

        usuario_id = st.session_state.get("usuario_id")
        usuario = db.get(Usuario, usuario_id) if usuario_id else None
        if not usuario or not usuario.ativo:
            encerrar_sessao()
            renderizar_tela_login(db, logo, cfg)
            return

        st.session_state["usuario_logado"] = usuario.nome
        st.session_state["perfil_usuario"] = usuario.perfil
        aplicar_estilo_global()

        if st.session_state.get("trocar_senha_obrigatoria"):
            cabecalho(logo, cfg)
            tela_minha_senha(db, usuario, obrigatoria=True)
            if st.button("🚪 Sair", key="sair_troca_senha"):
                encerrar_sessao()
                st.rerun()
            return

        permitidas = PERMISSOES.get(usuario.perfil, set())
        menu_opcoes = [p for p in MENU_PAGINAS if p in permitidas] + ["🔑 Minha senha"]

        with st.sidebar:
            if logo:
                st.image(logo, width=104)
            st.markdown(f"## {cfg['nome_instituicao']}")
            st.caption(f"{cfg['profissional_responsavel']} · {cfg['titulo_profissional']}")
            st.divider()
            # Tela guardada que este perfil não pode ver (ex.: troca de usuário) volta para a primeira.
            if st.session_state.get("menu_principal") not in menu_opcoes:
                st.session_state.pop("menu_principal", None)
            pagina = st.radio("MENU PRINCIPAL", menu_opcoes, label_visibility="visible", key="menu_principal")
            st.divider()
            st.write(f"Conectado: **{usuario.nome}**")
            st.caption(f"Perfil: {usuario.perfil}")
            if st.button("🚪 Sair", width="stretch", key="sair_sistema"):
                registrar_auditoria("logout", usuario=usuario.nome)
                encerrar_sessao()
                st.rerun()

        cabecalho(logo, cfg)
        telas = {
            "📊 Painel": lambda: tela_painel(db, usuario.perfil),
            "👥 Alunos e responsáveis": lambda: tela_cadastros(db, usuario.perfil),
            "📄 Contratos": lambda: tela_contratos(db),
            "📂 Prontuários": lambda: tela_prontuario(db),
            "📁 Atividades": lambda: tela_atividades(db, usuario),
            "✍️ Atividade com caneta": lambda: tela_atividade_caneta(db, usuario),
            "📓 Caderno Digital": lambda: tela_caderno_digital(db, usuario),
            "💰 Financeiro": lambda: tela_financeiro(db),
            "📈 Desempenho": lambda: tela_desempenho(db, usuario),
            "👤 Usuários": lambda: tela_usuarios(db, usuario.perfil),
            "⚙️ Configurações": lambda: tela_configuracoes(db),
            "🔑 Minha senha": lambda: tela_minha_senha(db, usuario),
        }
        telas[pagina]()
    except SQLAlchemyError as exc:
        db.rollback()
        # Rede de segurança: coluna/tabela ausente = migração não aplicada. Refaz UMA vez e recarrega.
        if erro_de_esquema(exc) and not st.session_state.get("_migracao_refeita"):
            print(f"[AVISO] Esquema desatualizado, refazendo migrações: {str(exc)[:300]}")
            st.session_state["_migracao_refeita"] = True
            inicializar_banco.clear()
            try:
                inicializar_banco(versao_esquema())
            except SQLAlchemyError as exc2:
                print(f"[ERRO DATABASE] migração falhou: {exc2}")
            else:
                st.rerun()
        mensagem_erro(exc, "acesso ao banco de dados")
    finally:
        db.close()


if __name__ == "__main__":
    main()