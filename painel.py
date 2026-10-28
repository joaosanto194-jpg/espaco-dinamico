# -*- coding: utf-8 -*-

# ============================================================
# KPI GESTÃO PÚBLICA — SESA
# Painel Executivo de Gestão Orçamentária e Empenhos
#
# VERSÃO 1.0
#
# FUNCIONALIDADES:
#   1. Leitura da base de dados em rede.
#   2. Limpeza de linhas de totalização e cabeçalhos repetidos.
#   3. Restrição às UGs 440901 até 440929.
#   4. Filtros interdependentes:
#      UG, Fonte, Natureza, Ação e PO.
#   5. Indicadores financeiros.
#   6. Gráfico de barras com todas as 29 UGs.
#   7. Destaque para a UG com maior saldo.
#   8. Gráficos de distribuição por Fonte e Natureza.
#   9. Tabela gerencial detalhada.
#  10. Diagnóstico de qualidade dos dados.
#
# IMPORTANTE:
#   A coluna financeira deve ser validada antes da utilização
#   definitiva dos valores para fins de controle orçamentário.
# ============================================================


# ============================================================
# 1. IMPORTAÇÕES
# ============================================================

import os
import re
import unicodedata
import logging

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ============================================================
# 2. CONFIGURAÇÕES GERAIS
# ============================================================

st.set_page_config(
    page_title="KPI Gestão Pública | SESA",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


CAMINHO_REDE = (
    r"\\fileserver\sesa$\FES\NEOF\JOAO VITOR"
    r"\MONITORAMENTO GFES\EMPENHO EM ABERTO - REDE SESA"
    r"\SALDO DE EMPENHO EM ABERTO - REDE SAÚDE.xlsx"
)

NOME_ABA = "Base_Dados"

# Mantém o cabeçalho da planilha conforme o código original.
LINHA_CABECALHO = 1

# Intervalo de unidades gestoras autorizado.
UG_INICIAL = 440901
UG_FINAL = 440929

# Atualização automática do cache em segundos.
TEMPO_CACHE = 300

# Quantidade máxima de registros exibidos na tabela.
LIMITE_TABELA = 1000

# Paleta visual.
AZUL_ESCURO = "#103B66"
AZUL_PRINCIPAL = "#145DA0"
AZUL_CLARO = "#36A5D6"
VERDE = "#10A77A"
LARANJA = "#F59E0B"
VERMELHO = "#DC4C4C"
CINZA = "#718096"


# ============================================================
# 3. ESTILIZAÇÃO VISUAL
# ============================================================

st.markdown(
    """
    <style>

    .stApp {
        background-color: #F3F6FA;
    }

    .block-container {
        padding-top: 1.1rem;
        padding-bottom: 2rem;
        max-width: 100%;
    }

    section[data-testid="stSidebar"] {
        background-color: #103052;
    }

    section[data-testid="stSidebar"] * {
        color: #FFFFFF;
    }

    .cabecalho-executivo {
        background: linear-gradient(
            110deg,
            #103052 0%,
            #145DA0 65%,
            #1D75BB 100%
        );
        padding: 22px 26px;
        border-radius: 13px;
        margin-bottom: 20px;
        color: white;
        box-shadow: 0 4px 14px rgba(16, 48, 82, 0.15);
    }

    .cabecalho-executivo h1 {
        font-size: 1.8rem;
        margin: 0;
        color: white;
        font-weight: 750;
    }

    .cabecalho-executivo p {
        margin: 7px 0 0 0;
        color: #EAF3FF;
        font-size: 0.95rem;
    }

    .secao-titulo {
        color: #103B66;
        font-size: 1.12rem;
        font-weight: 750;
        margin-top: 12px;
        margin-bottom: 12px;
    }

    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #DCE6F1;
        border-top: 5px solid #145DA0;
        border-radius: 12px;
        padding: 18px 15px;
        min-height: 142px;
        box-shadow: 0 4px 12px rgba(16, 47, 80, 0.06);
    }

    div[data-testid="stMetricLabel"] {
        color: #52647A;
        font-size: 0.86rem;
        line-height: 1.35;
        min-height: 39px;
        white-space: normal;
    }

    div[data-testid="stMetricValue"] {
        color: #103B66;
        font-size: clamp(1rem, 1.35vw, 1.65rem);
        font-weight: 750;
        line-height: 1.35;
        white-space: normal;
        overflow-wrap: anywhere;
    }

    div[data-testid="stMetricDelta"] {
        font-size: 0.78rem;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px;
    }

    div[data-testid="stAlert"] {
        border-radius: 9px;
    }

    .rodape-painel {
        color: #718096;
        font-size: 0.78rem;
        text-align: center;
        padding-top: 18px;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# 4. FUNÇÕES AUXILIARES
# ============================================================

def normalizar_texto(valor):
    """
    Padroniza textos para comparação de nomes de colunas.
    Remove acentos, converte para maiúsculas e normaliza espaços.
    """

    texto = str(valor).strip().upper()

    texto = unicodedata.normalize("NFKD", texto)

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    texto = re.sub(r"\s+", " ", texto)

    return texto


def extrair_codigo_ug(valor):
    """
    Extrai o código da UG.

    Exemplos:
        440901
        440901.0
        440901 - HOSPITAL
        440901 - SESA
    """

    if pd.isna(valor):
        return None

    texto = str(valor).strip()

    resultado = re.match(
        r"^\s*(\d{6})(?:\.0)?(?:\s|$|-)",
        texto
    )

    if resultado:
        return resultado.group(1)

    resultado = re.fullmatch(
        r"\s*(\d{6})(?:\.0)?\s*",
        texto
    )

    if resultado:
        return resultado.group(1)

    return None


def converter_valor_financeiro(valor):
    """
    Converte números e valores monetários para float.

    Exemplos:
        1234.56       -> 1234.56
        1.234,56      -> 1234.56
        R$ 1.234,56   -> 1234.56
        (1.234,56)    -> -1234.56

    Valores inválidos permanecem como NaN para permitir
    a identificação de registros problemáticos.
    """

    if pd.isna(valor):
        return float("nan")

    if isinstance(valor, bool):
        return float("nan")

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()

    if texto in ("", "-", "—", "–", "N/A", "n/a", "None"):
        return float("nan")

    texto = texto.replace("R$", "").strip()

    negativo_parenteses = (
        texto.startswith("(") and texto.endswith(")")
    )

    if negativo_parenteses:
        texto = texto[1:-1].strip()

    texto = texto.replace(" ", "")

    # Formato brasileiro:
    # 1.234.567,89
    if "," in texto:
        texto = texto.replace(".", "")
        texto = texto.replace(",", ".")

    # Formato internacional:
    # 1234.56
    # Quando não existe vírgula, o ponto é preservado.

    texto = re.sub(r"[^0-9.\-+]", "", texto)

    try:
        numero = float(texto)

        if negativo_parenteses:
            numero = -abs(numero)

        return numero

    except (ValueError, TypeError):
        return float("nan")


def formatar_moeda(valor):
    """
    Formatação monetária brasileira.
    """

    if pd.isna(valor):
        valor = 0.0

    valor = float(valor)

    texto = f"{valor:,.2f}"

    texto = (
        texto.replace(",", "TEMP")
        .replace(".", ",")
        .replace("TEMP", ".")
    )

    return f"R$ {texto}"


def formatar_inteiro(valor):
    """
    Formatação de inteiros no padrão brasileiro.
    """

    return f"{int(valor):,}".replace(",", ".")


def identificar_coluna(colunas, candidatos, termos_obrigatorios=None):
    """
    Identifica uma coluna por nomes preferenciais e alternativas.

    A correspondência exata normalizada tem prioridade.
    """

    mapa = {
        normalizar_texto(coluna): coluna
        for coluna in colunas
    }

    candidatos_normalizados = [
        normalizar_texto(candidato)
        for candidato in candidatos
    ]

    for candidato in candidatos_normalizados:
        if candidato in mapa:
            return mapa[candidato]

    # Busca parcial controlada.
    for coluna in colunas:

        nome = normalizar_texto(coluna)

        if termos_obrigatorios:

            if not all(
                normalizar_texto(termo) in nome
                for termo in termos_obrigatorios
            ):
                continue

        for candidato in candidatos_normalizados:

            if candidato in nome:
                return coluna

    return None


def coluna_financeira(coluna):
    """
    Verifica se o nome de uma coluna sugere conteúdo financeiro.
    """

    nome = normalizar_texto(coluna)

    termos = [
        "VALOR",
        "SALDO",
        "EMPENHADO",
        "LIQUIDADO",
        "PAGO",
        "ORCADO",
        "AUTORIZADO",
        "A LIQUIDAR",
        "A PAGAR",
        "A EMPENHAR",
        "DISPONIVEL",
        "DESPESA"
    ]

    return any(termo in nome for termo in termos)


def coluna_parece_codigo_ou_identificacao(coluna):
    """
    Evita sugerir códigos numéricos como métricas financeiras.
    """

    nome = normalizar_texto(coluna)

    termos = [
        "CODIGO",
        "CNPJ",
        "CPF",
        "PROCESSO",
        "NUMERO",
        "NUMERO DO EMPENHO",
        "EMPENHO",
        "FONTE",
        "NATUREZA",
        "ACAO",
        "PO",
        "UG",
        "EXERCICIO",
        "ANO",
        "SEQUENCIAL",
        "IDENTIFICADOR"
    ]

    return any(termo in nome for termo in termos)


def eh_linha_total(linha, colunas_textuais):
    """
    Detecta linhas explícitas de totalização.

    A exclusão é baseada em rótulos encontrados nas colunas
    textuais, sem eliminar lançamentos somente por repetirem
    valores ou identificadores.
    """

    padrao = (
        r"^\s*(?:"
        r"TOTAL(?:\s+GERAL)?"
        r"|SUBTOTAL"
        r"|TOTALIZACAO"
        r"|GRAND TOTAL"
        r")\s*:?$"
    )

    for coluna in colunas_textuais:

        valor = linha.get(coluna)

        if pd.isna(valor):
            continue

        texto = normalizar_texto(valor)

        if re.fullmatch(padrao, texto):
            return True

    return False


# ============================================================
# 5. LEITURA E TRATAMENTO DA BASE
# ============================================================

@st.cache_data(ttl=TEMPO_CACHE, show_spinner=False)
def carregar_dados_executivos(caminho, aba, linha_cabecalho):

    if not os.path.exists(caminho):
        return None, {
            "erro": (
                "Caminho de rede inacessível. "
                "Verifique a conexão com o servidor e as permissões."
            )
        }

    try:

        df_original = pd.read_excel(
            caminho,
            sheet_name=aba,
            header=linha_cabecalho,
            dtype=object
        )

        total_original = len(df_original)

        # Remove colunas completamente vazias.
        df_original = df_original.dropna(
            axis=1,
            how="all"
        )

        # Normaliza os nomes das colunas.
        df_original.columns = [
            str(coluna).strip()
            for coluna in df_original.columns
        ]

        # Elimina nomes de colunas vazios.
        df_original = df_original.loc[
            :,
            [
                coluna
                for coluna in df_original.columns
                if coluna and coluna.lower() != "nan"
            ]
        ]

        if df_original.empty:
            return None, {
                "erro": "A planilha não possui registros utilizáveis."
            }

        colunas = df_original.columns.tolist()

        # ----------------------------------------------------
        # MAPEAMENTO DAS COLUNAS
        # ----------------------------------------------------

        col_ug = identificar_coluna(
            colunas,
            [
                "UG",
                "Código UG",
                "Codigo UG",
                "Unidade Gestora",
                "Código Unidade Gestora",
                "UG Executora"
            ]
        )

        col_nome = identificar_coluna(
            colunas,
            [
                "Nome UG",
                "Nome da UG",
                "Nome Unidade Gestora",
                "Unidade Gestora",
                "Nome"
            ]
        )

        col_fonte = identificar_coluna(
            colunas,
            [
                "Fonte",
                "Fonte de Recursos",
                "Código Fonte",
                "Fonte Recurso"
            ]
        )

        col_natureza = identificar_coluna(
            colunas,
            [
                "Natureza",
                "Natureza da Despesa",
                "Nome Natureza",
                "Natureza Despesa",
                "ND"
            ]
        )

        col_acao = identificar_coluna(
            colunas,
            [
                "Ação",
                "Acao",
                "Código Ação",
                "Ação Orçamentária"
            ]
        )

        col_po = identificar_coluna(
            colunas,
            [
                "PO",
                "Plano Orçamentário",
                "Plano Orcamentario",
                "Nome PO"
            ]
        )

        # A coluna financeira é priorizada por significado.
        # Evita escolher automaticamente a primeira coluna numérica.
        col_saldo = identificar_coluna(
            colunas,
            [
                "Saldo em Aberto",
                "Saldo de Empenho em Aberto",
                "Empenho a Liquidar",
                "Empenhos a Liquidar",
                "Saldo Empenho",
                "Saldo de Empenho",
                "Despesas a Pagar",
                "Saldo"
            ]
        )

        # ----------------------------------------------------
        # VALIDAÇÃO DA COLUNA DA UG
        # ----------------------------------------------------

        if col_ug is None:

            return None, {
                "erro": (
                    "Não foi possível identificar a coluna da UG. "
                    "Confira os nomes dos cabeçalhos da planilha."
                )
            }

        # ----------------------------------------------------
        # PADRONIZAÇÃO DA IDENTIFICAÇÃO
        # ----------------------------------------------------

        df = df_original.copy()

        df["_CODIGO_UG"] = df[col_ug].map(extrair_codigo_ug)

        codigos_permitidos = {
            str(codigo)
            for codigo in range(UG_INICIAL, UG_FINAL + 1)
        }

        mascara_ug_valida = df["_CODIGO_UG"].isin(
            codigos_permitidos
        )

        total_fora_escopo = int(
            (~mascara_ug_valida).sum()
        )

        df = df.loc[mascara_ug_valida].copy()

        if df.empty:

            return None, {
                "erro": (
                    "Nenhum registro foi encontrado para as UGs "
                    f"{UG_INICIAL} a {UG_FINAL}. "
                    "Verifique o formato da coluna da UG."
                )
            }

        # ----------------------------------------------------
        # LIMPEZA DE TOTALIZAÇÕES
        # ----------------------------------------------------

        colunas_textuais = [
            coluna
            for coluna in df.columns
            if coluna != "_CODIGO_UG"
            and (
                pd.api.types.is_object_dtype(df[coluna])
                or pd.api.types.is_string_dtype(df[coluna])
            )
        ]

        mascara_total = df.apply(
            lambda linha: eh_linha_total(
                linha,
                colunas_textuais
            ),
            axis=1
        )

        total_linhas_totalizacao = int(
            mascara_total.sum()
        )

        df = df.loc[~mascara_total].copy()

        # ----------------------------------------------------
        # REMOÇÃO DE CABEÇALHOS REPETIDOS
        # ----------------------------------------------------

        mascara_cabecalho = pd.Series(
            False,
            index=df.index
        )

        for coluna in [
            col_ug,
            col_nome,
            col_fonte,
            col_natureza,
            col_acao,
            col_po
        ]:

            if coluna is None or coluna not in df.columns:
                continue

            valores = (
                df[coluna]
                .astype("string")
                .str.strip()
                .str.upper()
            )

            nome_cabecalho = str(coluna).strip().upper()

            mascara_cabecalho |= valores.eq(
                nome_cabecalho
            ).fillna(False)

        total_cabecalhos_repetidos = int(
            mascara_cabecalho.sum()
        )

        df = df.loc[~mascara_cabecalho].copy()

        # ----------------------------------------------------
        # CONVERSÃO DAS COLUNAS FINANCEIRAS
        # ----------------------------------------------------

        colunas_financeiras = [
            coluna
            for coluna in df.columns
            if coluna_financeira(coluna)
        ]

        for coluna in colunas_financeiras:

            df[coluna] = df[coluna].map(
                converter_valor_financeiro
            )

        # ----------------------------------------------------
        # IDENTIFICAÇÃO NOMINAL DA UG
        # ----------------------------------------------------

        if col_nome is not None and col_nome in df.columns:

            df[col_nome] = (
                df[col_nome]
                .astype("string")
                .str.strip()
            )

            df[col_nome] = df[col_nome].replace(
                {
                    "": pd.NA,
                    "nan": pd.NA,
                    "None": pd.NA
                }
            )

            # Se o campo de nome estiver ausente, utiliza o código.
            df[col_nome] = df[col_nome].fillna(
                df["_CODIGO_UG"]
            )

        else:

            col_nome = "_NOME_UG"

            df[col_nome] = df["_CODIGO_UG"]

        # ----------------------------------------------------
        # VALIDAÇÃO DA MÉTRICA FINANCEIRA
        # ----------------------------------------------------

        if col_saldo is not None:

            if col_saldo not in df.columns:

                col_saldo = None

            elif not pd.api.types.is_numeric_dtype(
                df[col_saldo]
            ):

                col_saldo = None

        # Identifica métricas numéricas sem sugerir códigos.
        colunas_numericas = [
            coluna
            for coluna in df.columns
            if coluna != "_CODIGO_UG"
            and pd.api.types.is_numeric_dtype(df[coluna])
            and not coluna_parece_codigo_ou_identificacao(coluna)
        ]

        metrica_padrao = (
            col_saldo
            if col_saldo in colunas_numericas
            else None
        )

        if metrica_padrao is None:

            metrica_padrao = next(
                (
                    coluna
                    for coluna in colunas_numericas
                    if coluna_financeira(coluna)
                ),
                None
            )

        diagnostico = {
            "total_original": total_original,
            "total_fora_escopo": total_fora_escopo,
            "total_linhas_totalizacao": total_linhas_totalizacao,
            "total_cabecalhos_repetidos": total_cabecalhos_repetidos,
            "total_final": len(df),
            "col_ug": col_ug,
            "col_nome": col_nome,
            "col_fonte": col_fonte,
            "col_natureza": col_natureza,
            "col_acao": col_acao,
            "col_po": col_po,
            "col_saldo": col_saldo,
            "colunas_numericas": colunas_numericas,
            "metrica_padrao": metrica_padrao,
            "colunas_originais": colunas
        }

        return df, diagnostico

    except Exception as erro:

        logging.exception(
            "Falha na leitura da base orçamentária."
        )

        return None, {
            "erro": (
                f"Falha na leitura da planilha: {erro}"
            )
        }


# ============================================================
# 6. CARREGAMENTO DA BASE
# ============================================================

with st.spinner("Carregando e validando a base orçamentária..."):

    df, diagnostico = carregar_dados_executivos(
        CAMINHO_REDE,
        NOME_ABA,
        LINHA_CABECALHO
    )


# ============================================================
# 7. CABEÇALHO DO PAINEL
# ============================================================

st.markdown(
    """
    <div class="cabecalho-executivo">
        <h1>SESA | KPI GESTÃO PÚBLICA</h1>
        <p>
            Painel Executivo de Gestão Orçamentária e Empenhos
            <br>
            Cubo de Valores por Unidade Gestora — UGs 440901 a 440929
        </p>
    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# 8. TRATAMENTO DE ERROS DE CONEXÃO
# ============================================================

if df is None:

    st.error(
        "Não foi possível carregar a base de dados."
    )

    st.warning(
        diagnostico.get(
            "erro",
            "Erro não identificado."
        )
    )

    st.info(
        "Confira o acesso à pasta de rede, o nome da aba "
        "e a estrutura dos cabeçalhos."
    )

    if st.button("Tentar novamente", type="primary"):

        st.cache_data.clear()

        st.rerun()

    st.stop()


# ============================================================
# 9. IDENTIFICAÇÃO DAS COLUNAS
# ============================================================

col_ug = diagnostico["col_ug"]
col_nome = diagnostico["col_nome"]
col_fonte = diagnostico["col_fonte"]
col_natureza = diagnostico["col_natureza"]
col_acao = diagnostico["col_acao"]
col_po = diagnostico["col_po"]

colunas_numericas = diagnostico["colunas_numericas"]

metrica_padrao = diagnostico["metrica_padrao"]


# ============================================================
# 10. BARRA LATERAL
# ============================================================

with st.sidebar:

    st.markdown("## 🏛️ SESA")

    st.caption(
        "Secretaria de Estado da Saúde"
    )

    st.divider()

    st.markdown("### Navegação")

    pagina = st.radio(
        "Selecione a área",
        [
            "Visão Geral",
            "Cubo de Valores",
            "Qualidade dos Dados"
        ],
        index=0
    )

    st.divider()

    st.markdown("### Base carregada")

    st.metric(
        "Registros válidos",
        formatar_inteiro(len(df))
    )

    st.caption(
        "Intervalo de UGs: 440901 a 440929"
    )

    if st.button(
        "🔄 Sincronizar dados",
        use_container_width=True
    ):

        st.cache_data.clear()

        st.rerun()

    st.divider()

    st.caption(
        "KPI Gestão Pública | SESA"
    )


# ============================================================
# 11. SELEÇÃO DA MÉTRICA FINANCEIRA
# ============================================================

st.markdown(
    '<div class="secao-titulo">⚙️ Configuração da Análise</div>',
    unsafe_allow_html=True
)

if not colunas_numericas:

    st.error(
        "Nenhuma coluna financeira ou numérica válida foi identificada."
    )

    st.stop()


if metrica_padrao is not None:

    indice_metrica = colunas_numericas.index(
        metrica_padrao
    )

else:

    indice_metrica = 0


metrica_ativa = st.selectbox(
    "Métrica financeira utilizada nos indicadores e gráficos",
    options=colunas_numericas,
    index=indice_metrica,
    help=(
        "Selecione a coluna que representa o saldo ou valor "
        "financeiro que deseja analisar."
    )
)


if diagnostico["col_saldo"] is None:

    st.warning(
        "A coluna de saldo em aberto não foi identificada "
        "automaticamente. Confirme se a métrica selecionada "
        "corresponde ao valor financeiro que deseja monitorar."
    )


# ============================================================
# 12. LISTA DE UGS E FILTROS DINÂMICOS
# ============================================================

st.markdown(
    '<div class="secao-titulo">🎛️ Filtros do Cubo Gerencial</div>',
    unsafe_allow_html=True
)

st.caption(
    "Os filtros são interdependentes: cada lista considera "
    "as seleções realizadas nos demais campos."
)


# Lista fixa das 29 UGs.
codigos_ugs = [
    f"{codigo:06d}"
    for codigo in range(UG_INICIAL, UG_FINAL + 1)
]


# Mapa dos nomes disponíveis.
mapa_nomes_ug = (
    df.groupby("_CODIGO_UG")[col_nome]
    .first()
    .to_dict()
)


# Exibe as 29 UGs mesmo quando algumas não possuem registros.
opcoes_ug = []

for codigo in codigos_ugs:

    nome = mapa_nomes_ug.get(
        codigo,
        codigo
    )

    if pd.isna(nome):
        nome = codigo

    opcoes_ug.append(
        f"{codigo} - {str(nome)}"
    )


mapa_rotulo_codigo = {
    rotulo: codigo
    for rotulo, codigo in zip(
        opcoes_ug,
        codigos_ugs
    )
}


def valores_distintos(serie):

    valores = (
        serie.dropna()
        .astype(str)
        .str.strip()
    )

    valores = valores[
        valores.ne("")
    ]

    return sorted(
        valores.unique().tolist(),
        key=lambda valor: normalizar_texto(valor)
    )


def aplicar_filtros(
    base,
    codigos_ug=None,
    fontes=None,
    naturezas=None,
    acoes=None,
    pos=None
):

    resultado = base.copy()

    if codigos_ug:

        resultado = resultado[
            resultado["_CODIGO_UG"].isin(
                codigos_ug
            )
        ]

    if fontes and col_fonte:

        resultado = resultado[
            resultado[col_fonte]
            .astype(str)
            .isin(fontes)
        ]

    if naturezas and col_natureza:

        resultado = resultado[
            resultado[col_natureza]
            .astype(str)
            .isin(naturezas)
        ]

    if acoes and col_acao:

        resultado = resultado[
            resultado[col_acao]
            .astype(str)
            .isin(acoes)
        ]

    if pos and col_po:

        resultado = resultado[
            resultado[col_po]
            .astype(str)
            .isin(pos)
        ]

    return resultado


# Estado dos filtros.
# A sessão preserva as seleções durante as interações.

if "filtro_ugs" not in st.session_state:
    st.session_state["filtro_ugs"] = []

if "filtro_fontes" not in st.session_state:
    st.session_state["filtro_fontes"] = []

if "filtro_naturezas" not in st.session_state:
    st.session_state["filtro_naturezas"] = []

if "filtro_acoes" not in st.session_state:
    st.session_state["filtro_acoes"] = []

if "filtro_pos" not in st.session_state:
    st.session_state["filtro_pos"] = []


# Botão de limpeza.
col_limpar, col_status = st.columns(
    [1, 5]
)

with col_limpar:

    if st.button(
        "🧹 Limpar filtros",
        use_container_width=True
    ):

        for chave in [
            "filtro_ugs",
            "filtro_fontes",
            "filtro_naturezas",
            "filtro_acoes",
            "filtro_pos"
        ]:

            st.session_state[chave] = []

        st.rerun()


with col_status:

    st.caption(
        "A seleção de uma UG restringe todos os indicadores "
        "e gráficos aos registros daquela unidade."
    )


# ------------------------------------------------------------
# FILTRO UG
# ------------------------------------------------------------

selecoes_atuais = {
    "ugs": st.session_state["filtro_ugs"],
    "fontes": st.session_state["filtro_fontes"],
    "naturezas": st.session_state["filtro_naturezas"],
    "acoes": st.session_state["filtro_acoes"],
    "pos": st.session_state["filtro_pos"]
}


# ------------------------------------------------------------
# FILTRO FONTE
# ------------------------------------------------------------

base_fonte = aplicar_filtros(
    df,
    codigos_ug=selecoes_atuais["ugs"] or None,
    naturezas=selecoes_atuais["naturezas"] or None,
    acoes=selecoes_atuais["acoes"] or None,
    pos=selecoes_atuais["pos"] or None
)

opcoes_fonte = (
    valores_distintos(base_fonte[col_fonte])
    if col_fonte
    else []
)


# ------------------------------------------------------------
# FILTRO NATUREZA
# ------------------------------------------------------------

base_natureza = aplicar_filtros(
    df,
    codigos_ug=selecoes_atuais["ugs"] or None,
    fontes=selecoes_atuais["fontes"] or None,
    acoes=selecoes_atuais["acoes"] or None,
    pos=selecoes_atuais["pos"] or None
)

opcoes_natureza = (
    valores_distintos(base_natureza[col_natureza])
    if col_natureza
    else []
)


# ------------------------------------------------------------
# FILTRO AÇÃO
# ------------------------------------------------------------

base_acao = aplicar_filtros(
    df,
    codigos_ug=selecoes_atuais["ugs"] or None,
    fontes=selecoes_atuais["fontes"] or None,
    naturezas=selecoes_atuais["naturezas"] or None,
    pos=selecoes_atuais["pos"] or None
)

opcoes_acao = (
    valores_distintos(base_acao[col_acao])
    if col_acao
    else []
)


# ------------------------------------------------------------
# FILTRO PO
# ------------------------------------------------------------

base_po = aplicar_filtros(
    df,
    codigos_ug=selecoes_atuais["ugs"] or None,
    fontes=selecoes_atuais["fontes"] or None,
    naturezas=selecoes_atuais["naturezas"] or None,
    acoes=selecoes_atuais["acoes"] or None
)

opcoes_po = (
    valores_distintos(base_po[col_po])
    if col_po
    else []
)


# ------------------------------------------------------------
# EXIBIÇÃO DOS FILTROS
# ------------------------------------------------------------

f1, f2, f3, f4, f5 = st.columns(
    [1.4, 1.2, 1.3, 1.1, 1.0],
    gap="medium"
)


with f1:

    filtro_ugs = st.multiselect(
        "Unidade Gestora (UG)",
        options=opcoes_ug,
        key="filtro_ugs",
        help="Selecione uma ou mais unidades gestoras."
    )


with f2:

    if col_fonte:

        filtro_fontes = st.multiselect(
            "Fonte",
            options=opcoes_fonte,
            key="filtro_fontes"
        )

    else:

        st.warning(
            "Coluna Fonte não identificada."
        )

        filtro_fontes = []


with f3:

    if col_natureza:

        filtro_naturezas = st.multiselect(
            "Natureza",
            options=opcoes_natureza,
            key="filtro_naturezas"
        )

    else:

        st.warning(
            "Coluna Natureza não identificada."
        )

        filtro_naturezas = []


with f4:

    if col_acao:

        filtro_acoes = st.multiselect(
            "Ação",
            options=opcoes_acao,
            key="filtro_acoes"
        )

    else:

        st.warning(
            "Coluna Ação não identificada."
        )

        filtro_acoes = []


with f5:

    if col_po:

        filtro_pos = st.multiselect(
            "PO",
            options=opcoes_po,
            key="filtro_pos"
        )

    else:

        st.warning(
            "Coluna PO não identificada."
        )

        filtro_pos = []


# ------------------------------------------------------------
# FILTROS SELECIONADOS
# ------------------------------------------------------------

codigos_ugs_selecionadas = [
    mapa_rotulo_codigo[rotulo]
    for rotulo in filtro_ugs
    if rotulo in mapa_rotulo_codigo
]


# ------------------------------------------------------------
# APLICAÇÃO DEFINITIVA DOS FILTROS
# ------------------------------------------------------------

df_f = aplicar_filtros(
    df,
    codigos_ug=codigos_ugs_selecionadas or None,
    fontes=filtro_fontes or None,
    naturezas=filtro_naturezas or None,
    acoes=filtro_acoes or None,
    pos=filtro_pos or None
)


# ============================================================
# 13. VALIDAÇÃO DO RESULTADO DOS FILTROS
# ============================================================

st.divider()

if df_f.empty:

    st.warning(
        "Nenhum registro foi encontrado para a combinação "
        "de filtros selecionada."
    )

    st.info(
        "Altere ou limpe os filtros para consultar outros "
        "registros. Os KPIs não serão preenchidos com valores "
        "da base geral enquanto houver uma seleção sem resultados."
    )


# ============================================================
# 14. INDICADORES ESTRATÉGICOS
# ============================================================

st.markdown(
    '<div class="secao-titulo">📌 Indicadores Estratégicos</div>',
    unsafe_allow_html=True
)


if not df_f.empty:

    total_registros = len(df_f)

    montante_total = float(
        df_f[metrica_ativa].sum()
    )

    media_lancamento = float(
        df_f[metrica_ativa].mean()
    )

    maior_valor = float(
        df_f[metrica_ativa].max()
    )

    total_unidades = int(
        df_f["_CODIGO_UG"].nunique()
    )

else:

    total_registros = 0

    montante_total = 0.0

    media_lancamento = 0.0

    maior_valor = 0.0

    total_unidades = 0


k1, k2, k3, k4, k5 = st.columns(
    5,
    gap="medium"
)


with k1:

    st.metric(
        "Saldo Total em Aberto",
        formatar_moeda(montante_total)
    )


with k2:

    st.metric(
        "Registros Selecionados",
        formatar_inteiro(total_registros)
    )


with k3:

    st.metric(
        "Unidades Gestoras",
        f"{total_unidades} de 29"
    )


with k4:

    st.metric(
        "Saldo Médio por Registro",
        formatar_moeda(media_lancamento)
    )


with k5:

    st.metric(
        "Maior Saldo Individual",
        formatar_moeda(maior_valor)
    )


st.caption(
    f"Métrica utilizada: {metrica_ativa} | "
    f"Registros após filtros: {formatar_inteiro(total_registros)}"
)


# ============================================================
# 15. PREPARAÇÃO DA BASE DAS 29 UGs
# ============================================================

df_ug_grafico = pd.DataFrame(
    {
        "Código UG": codigos_ugs
    }
)


# Nomes disponíveis na base.
nomes_disponiveis = (
    df.groupby("_CODIGO_UG")[col_nome]
    .first()
    .to_dict()
)


df_ug_grafico["Unidade Gestora"] = (
    df_ug_grafico["Código UG"]
    .map(nomes_disponiveis)
    .fillna(df_ug_grafico["Código UG"])
)


# Quando há filtros, a soma considera somente os registros filtrados.
if not df_f.empty:

    df_saldo_ug = (
        df_f.groupby("_CODIGO_UG")[metrica_ativa]
        .sum()
        .reset_index()
        .rename(
            columns={
                "_CODIGO_UG": "Código UG",
                metrica_ativa: "Saldo"
            }
        )
    )

else:

    df_saldo_ug = pd.DataFrame(
        columns=[
            "Código UG",
            "Saldo"
        ]
    )


df_ug_grafico = df_ug_grafico.merge(
    df_saldo_ug,
    on="Código UG",
    how="left"
)


df_ug_grafico["Saldo"] = (
    df_ug_grafico["Saldo"]
    .fillna(0.0)
)


df_ug_grafico["Rótulo"] = (
    df_ug_grafico["Código UG"]
    + " - "
    + df_ug_grafico["Unidade Gestora"].astype(str)
)


# ------------------------------------------------------------
# RESPEITAR A SELEÇÃO DE UG
# ------------------------------------------------------------

if codigos_ugs_selecionadas:

    df_ug_grafico = df_ug_grafico[
        df_ug_grafico["Código UG"].isin(
            codigos_ugs_selecionadas
        )
    ].copy()


# ------------------------------------------------------------
# IDENTIFICAR MAIOR SALDO
# ------------------------------------------------------------

if not df_ug_grafico.empty:

    maior_saldo_ug = df_ug_grafico["Saldo"].max()

    df_ug_grafico["Destaque"] = df_ug_grafico[
        "Saldo"
    ].apply(
        lambda valor: (
            "Maior saldo"
            if valor == maior_saldo_ug and valor > 0
            else "Demais UGs"
        )
    )

else:

    df_ug_grafico["Destaque"] = []


# ============================================================
# 16. GRÁFICO DE BARRAS — SALDO POR UG
# ============================================================

st.divider()

st.markdown(
    '<div class="secao-titulo">📊 Saldo por Unidade Gestora</div>',
    unsafe_allow_html=True
)


st.caption(
    "A barra de maior saldo recebe destaque. "
    "Todas as UGs do intervalo autorizado permanecem visíveis "
    "quando nenhum filtro de UG é aplicado."
)


if not df_ug_grafico.empty:

    df_barra = df_ug_grafico.sort_values(
        "Saldo",
        ascending=True
    ).copy()

    fig_bar = px.bar(
        df_barra,
        x="Saldo",
        y="Rótulo",
        orientation="h",
        color="Destaque",
        color_discrete_map={
            "Maior saldo": AZUL_ESCURO,
            "Demais UGs": AZUL_CLARO
        },
        text="Saldo",
        custom_data=[
            "Código UG",
            "Unidade Gestora"
        ]
    )

    fig_bar.update_traces(
        texttemplate="R$ %{x:,.2f}",
        textposition="outside",
        cliponaxis=False,
        width=0.78,
        hovertemplate=(
            "<b>UG %{customdata[0]}</b><br>"
            "%{customdata[1]}<br>"
            "Saldo: R$ %{x:,.2f}"
            "<extra></extra>"
        )
    )

    fig_bar.update_layout(
        template="plotly_white",
        height=max(
            650,
            len(df_barra) * 30
        ),
        showlegend=False,
        bargap=0.18,
        xaxis_title="Saldo financeiro (R$)",
        yaxis_title="",
        margin=dict(
            l=15,
            r=150,
            t=20,
            b=45
        ),
        font=dict(
            size=12,
            color=AZUL_ESCURO
        ),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF"
    )

    fig_bar.update_xaxes(
        tickformat=",.0f",
        showgrid=True,
        gridcolor="#E6EDF5",
        zeroline=False
    )

    fig_bar.update_yaxes(
        categoryorder="array",
        categoryarray=df_barra["Rótulo"].tolist(),
        automargin=True
    )

    st.plotly_chart(
        fig_bar,
        use_container_width=True
    )


# ============================================================
# 17. DISTRIBUIÇÃO POR FONTE E NATUREZA
# ============================================================

g1, g2 = st.columns(
    2,
    gap="medium"
)


# ------------------------------------------------------------
# FONTE
# ------------------------------------------------------------

with g1:

    st.markdown(
        "#### Distribuição por Fonte de Recursos"
    )

    if col_fonte and not df_f.empty:

        df_fonte = (
            df_f.groupby(
                col_fonte,
                dropna=False
            )[metrica_ativa]
            .sum()
            .reset_index()
            .rename(
                columns={
                    col_fonte: "Fonte",
                    metrica_ativa: "Saldo"
                }
            )
            .sort_values(
                "Saldo",
                ascending=False
            )
        )

        df_fonte["Fonte"] = (
            df_fonte["Fonte"]
            .fillna("Não informado")
            .astype(str)
        )

        fig_fonte = px.bar(
            df_fonte,
            x="Saldo",
            y="Fonte",
            orientation="h",
            text="Saldo",
            color="Saldo",
            color_continuous_scale=[
                "#DCEBFA",
                "#36A5D6",
                "#103B66"
            ]
        )

        fig_fonte.update_traces(
            texttemplate="R$ %{x:,.2f}",
            textposition="outside",
            cliponaxis=False
        )

        fig_fonte.update_layout(
            template="plotly_white",
            height=420,
            coloraxis_showscale=False,
            xaxis_title="Valor (R$)",
            yaxis_title="",
            margin=dict(
                l=10,
                r=120,
                t=15,
                b=35
            )
        )

        fig_fonte.update_yaxes(
            categoryorder="total ascending"
        )

        st.plotly_chart(
            fig_fonte,
            use_container_width=True
        )

    else:

        st.info(
            "Sem registros para apresentar a distribuição por Fonte."
        )


# ------------------------------------------------------------
# NATUREZA
# ------------------------------------------------------------

with g2:

    st.markdown(
        "#### Distribuição por Natureza da Despesa"
    )

    if col_natureza and not df_f.empty:

        df_natureza = (
            df_f.groupby(
                col_natureza,
                dropna=False
            )[metrica_ativa]
            .sum()
            .reset_index()
            .rename(
                columns={
                    col_natureza: "Natureza",
                    metrica_ativa: "Saldo"
                }
            )
            .sort_values(
                "Saldo",
                ascending=False
            )
        )

        df_natureza["Natureza"] = (
            df_natureza["Natureza"]
            .fillna("Não informada")
            .astype(str)
        )

        fig_natureza = px.pie(
            df_natureza,
            names="Natureza",
            values="Saldo",
            hole=0.55
        )

        fig_natureza.update_traces(
            textposition="inside",
            textinfo="percent",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Saldo: R$ %{value:,.2f}<br>"
                "Participação: %{percent}"
                "<extra></extra>"
            )
        )

        fig_natureza.update_layout(
            template="plotly_white",
            height=420,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.08,
                xanchor="center",
                x=0.5
            ),
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=70
            )
        )

        st.plotly_chart(
            fig_natureza,
            use_container_width=True
        )

    else:

        st.info(
            "Sem registros para apresentar a distribuição por Natureza."
        )


# ============================================================
# 18. PARTICIPAÇÃO DAS UGs
# ============================================================

st.divider()

st.markdown(
    '<div class="secao-titulo">🏛️ Participação por Unidade Gestora</div>',
    unsafe_allow_html=True
)


df_participacao = df_ug_grafico.copy()

total_participacao = df_participacao["Saldo"].sum()

if total_participacao != 0:

    df_participacao["Participação (%)"] = (
        df_participacao["Saldo"]
        / total_participacao
        * 100
    )

else:

    df_participacao["Participação (%)"] = 0.0


df_participacao = df_participacao.sort_values(
    "Saldo",
    ascending=False
)


st.dataframe(
    df_participacao[
        [
            "Código UG",
            "Unidade Gestora",
            "Saldo",
            "Participação (%)"
        ]
    ].rename(
        columns={
            "Código UG": "UG",
            "Unidade Gestora": "Unidade Gestora",
            "Saldo": "Saldo financeiro (R$)"
        }
    ),
    column_config={
        "Saldo financeiro (R$)": st.column_config.NumberColumn(
            "Saldo financeiro (R$)",
            format="R$ %.2f"
        ),
        "Participação (%)": st.column_config.NumberColumn(
            "Participação (%)",
            format="%.2f%%"
        )
    },
    hide_index=True,
    use_container_width=True
)


# ============================================================
# 19. CUBO DE VALORES — DETALHAMENTO
# ============================================================

if pagina == "Cubo de Valores":

    st.divider()

    st.markdown(
        '<div class="secao-titulo">📋 Cubo de Valores — Detalhamento</div>',
        unsafe_allow_html=True
    )

    if not df_f.empty:

        st.caption(
            "A tabela apresenta os registros após aplicação "
            "dos filtros selecionados."
        )

        df_exibicao = df_f.copy()

        colunas_ocultas = [
            "_CODIGO_UG"
        ]

        df_exibicao = df_exibicao.drop(
            columns=colunas_ocultas,
            errors="ignore"
        )

        st.dataframe(
            df_exibicao.head(LIMITE_TABELA),
            hide_index=True,
            use_container_width=True,
            height=600
        )

        if len(df_exibicao) > LIMITE_TABELA:

            st.warning(
                f"A tabela exibe os primeiros {LIMITE_TABELA} "
                f"registros de um total de {len(df_exibicao):,}. "
                "O arquivo exportado conterá todos os registros filtrados."
            )

        csv = df_f.to_csv(
            index=False,
            sep=";",
            decimal=",",
            encoding="utf-8-sig"
        )

        st.download_button(
            label="📥 Exportar dados filtrados para CSV",
            data=csv,
            file_name="KPI_Gestao_Publica_SESA.csv",
            mime="text/csv"
        )

    else:

        st.info(
            "Não existem registros para a combinação de filtros selecionada."
        )


# ============================================================
# 20. QUALIDADE DOS DADOS
# ============================================================

if pagina == "Qualidade dos Dados":

    st.divider()

    st.markdown(
        '<div class="secao-titulo">🔎 Qualidade e Auditoria dos Dados</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        "### Resultado da leitura e limpeza"
    )

    q1, q2, q3, q4 = st.columns(4)

    with q1:

        st.metric(
            "Registros originais",
            formatar_inteiro(
                diagnostico["total_original"]
            )
        )

    with q2:

        st.metric(
            "Fora do intervalo de UGs",
            formatar_inteiro(
                diagnostico["total_fora_escopo"]
            )
        )

    with q3:

        st.metric(
            "Totalizações removidas",
            formatar_inteiro(
                diagnostico["total_linhas_totalizacao"]
            )
        )

    with q4:

        st.metric(
            "Cabeçalhos repetidos removidos",
            formatar_inteiro(
                diagnostico["total_cabecalhos_repetidos"]
            )
        )

    st.divider()

    st.markdown(
        "### Mapeamento das colunas"
    )

    mapa_colunas = pd.DataFrame(
        [
            {
                "Campo": "Unidade Gestora",
                "Coluna identificada": col_ug or "Não identificada"
            },
            {
                "Campo": "Nome da UG",
                "Coluna identificada": col_nome or "Não identificada"
            },
            {
                "Campo": "Fonte",
                "Coluna identificada": col_fonte or "Não identificada"
            },
            {
                "Campo": "Natureza",
                "Coluna identificada": col_natureza or "Não identificada"
            },
            {
                "Campo": "Ação",
                "Coluna identificada": col_acao or "Não identificada"
            },
            {
                "Campo": "PO",
                "Coluna identificada": col_po or "Não identificada"
            },
            {
                "Campo": "Saldo identificado",
                "Coluna identificada": (
                    diagnostico["col_saldo"]
                    or "Não identificada automaticamente"
                )
            },
            {
                "Campo": "Métrica em uso",
                "Coluna identificada": metrica_ativa
            }
        ]
    )

    st.dataframe(
        mapa_colunas,
        hide_index=True,
        use_container_width=True
    )

    st.divider()

    st.markdown(
        "### Verificação de valores financeiros"
    )

    if colunas_numericas:

        resultados_validacao = []

        for coluna in colunas_numericas:

            serie = df[coluna]

            resultados_validacao.append(
                {
                    "Coluna": coluna,
                    "Registros": len(serie),
                    "Valores nulos": int(
                        serie.isna().sum()
                    ),
                    "Valores negativos": int(
                        (serie < 0).sum()
                    ),
                    "Soma": float(
                        serie.sum()
                    )
                }
            )

        df_validacao = pd.DataFrame(
            resultados_validacao
        )

        st.dataframe(
            df_validacao,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Soma": st.column_config.NumberColumn(
                    "Soma",
                    format="R$ %.2f"
                )
            }
        )

    else:

        st.info(
            "Não foram identificadas colunas numéricas para validação."
        )

    st.divider()

    st.markdown(
        "### Conferência de registros por UG"
    )

    contagem_ugs = (
        df.groupby("_CODIGO_UG")
        .size()
        .reindex(
            codigos_ugs,
            fill_value=0
        )
        .reset_index()
    )

    contagem_ugs.columns = [
        "Código UG",
        "Quantidade de registros"
    ]

    contagem_ugs["Situação"] = (
        contagem_ugs["Quantidade de registros"]
        .apply(
            lambda quantidade: (
                "Com registros"
                if quantidade > 0
                else "Sem registros válidos"
            )
        )
    )

    st.dataframe(
        contagem_ugs,
        hide_index=True,
        use_container_width=True
    )


# ============================================================
# 21. VISÃO GERAL
# ============================================================

if pagina == "Visão Geral":

    st.divider()

    st.markdown(
        '<div class="secao-titulo">📌 Resumo Executivo</div>',
        unsafe_allow_html=True
    )

    if df_f.empty:

        st.info(
            "A visão geral está sem registros para os filtros atuais."
        )

    else:

        st.markdown(
            f"""
            **Escopo da análise:** UGs {UG_INICIAL} a {UG_FINAL}

            **Métrica financeira:** {metrica_ativa}

            **Registros considerados:** {formatar_inteiro(len(df_f))}

            **Saldo consolidado:** {formatar_moeda(montante_total)}

            **Unidades com registros no resultado:** {total_unidades}

            **Maior valor individual encontrado:** {formatar_moeda(maior_valor)}
            """
        )

        st.caption(
            "Os valores apresentados correspondem à métrica "
            "financeira selecionada e aos filtros atualmente aplicados."
        )


# ============================================================
# 22. RODAPÉ
# ============================================================

st.markdown(
    """
    <div class="rodape-painel">
        KPI Gestão Pública • Secretaria de Estado da Saúde — SESA
        <br>
        Painel Executivo de Gestão Orçamentária e Empenhos
    </div>
    """,
    unsafe_allow_html=True
)