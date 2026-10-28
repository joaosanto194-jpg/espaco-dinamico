import datetime
import os
import time
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------
# 1. PARÂMETROS E DATAS
# ---------------------------------------------------------
ano_atual = str(datetime.datetime.now().year)  # "2026"
mes_atual = str(datetime.datetime.now().month)  # Mês numérico atual (Ex: "9" ou "09")


def baixar_relatorio_sigefes():
    print("Conectando ao navegador Chrome já aberto...")

    with sync_playwright() as p:
        # Conecta na janela do Chrome aberta na porta 9222
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]

        # Localiza a aba em que o SIGEFES está aberto
        page = None
        for p_aba in context.pages:
            if "sigefes" in p_aba.url.lower() or "sigefes" in p_aba.title().lower():
                page = p_aba
                break

        if not page:
            # Caso não encontre pelo título/URL, usa a aba ativa atual
            page = context.pages[0]

        print("Aba do SIGEFES localizada! Iniciando navegação...")

        # ---------------------------------------------------------
        # 2. NAVEGAÇÃO NOS MENUS
        # ---------------------------------------------------------
        # Clica na pasta/módulo ATENDIMENTO A UG'S
        print("Acessando 'ATENDIMENTO A UG'S'...")
        page.get_by_text("ATENDIMENTO A UG'S", exact=False).click()
        time.sleep(1.5)

        # Clica em Controle por Ordem Cronológica
        print("Acessando 'Controle por Ordem Cronológica'...")
        page.get_by_text("Controle por Ordem Cronológica", exact=False).click()
        time.sleep(1.5)

        # Clica no relatório CRO.02
        print("Selecionando 'CRO.02 - Relatório cronológico - Pago'...")
        page.get_by_text(
            "CRO.02 - Relatório cronológico - Pago", exact=False
        ).click()
        time.sleep(2.5)

        # ---------------------------------------------------------
        # 3. PREENCHIMENTO DOS FILTROS (Exercício e Mês)
        # ---------------------------------------------------------
        print(f"Preenchendo Exercício ({ano_atual}) e Mês ({mes_atual})...")

        # Preenche o campo de exercício (Ex: 2026)
        # Observação: Ajuste o seletor/nome do campo caso o formulário utilize rótulos específicos
        page.locator("input[name*='exercicio'], input[id*='exercicio']").fill(
            ano_atual
        )

        # Seleciona ou preenche o mês atual
        try:
            page.locator("select[name*='mes'], select[id*='mes']").select_option(
                mes_atual
            )
        except:
            page.locator("input[name*='mes'], input[id*='mes']").fill(mes_atual)

        time.sleep(1.5)

        # ---------------------------------------------------------
        # 4. EXECUTAR E BAIXAR EXCEL
        # ---------------------------------------------------------
        print("Executando o relatório...")
        page.get_by_role("button", name="Rodar") or page.get_by_text(
            "Executar"
        ).click()

        time.sleep(3)  # Aguarda o relatório processar na tela

        print("Iniciando o download do arquivo Excel...")
        # Captura o evento de download ao clicar no botão de exportar
        with page.expect_download() as download_info:
            # Clica no ícone/botão de exportar para Excel
            page.locator(
                "button:has-text('Excel'), a:has-text('Excel'), [title*='Excel']"
            ).click()

        download = download_info.value

        # Salva o arquivo diretamente na pasta Downloads do usuário
        pasta_downloads = r"C:\Users\joaovitorsantos\Downloads"
        caminho_final_download = os.path.join(pasta_downloads, download.suggested_filename)
        download.save_as(caminho_final_download)

        print(
            f"Download concluído com sucesso: {download.suggested_filename}"
        )


# ---------------------------------------------------------
# EXECUÇÃO DO FLUXO COMPLETO
# ---------------------------------------------------------
if __name__ == "__main__":
    try:
        # Etapa 1: Baixar do SIGEFES
        baixar_relatorio_sigefes()
        time.sleep(3)

        # Etapa 2: Executar o seu script de tratamento no Excel (cro02.py)
        print("\nIniciando o tratamento das planilhas no servidor...")
        # Aqui você pode chamar a função do seu script do Excel que já está pronta!

    except Exception as e:
        print(f"\nErro na automação do SIGEFES: {e}")