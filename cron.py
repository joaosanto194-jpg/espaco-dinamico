import os
import time
import socket
import subprocess
import win32com.client as win32
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# ============================================================
# VERIFICAÇÃO E ABERTURA AUTOMÁTICA DO CHROME (PORTA 9222)
# ============================================================
def verificar_ou_abrir_chrome():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    resultado = sock.connect_ex(('127.0.0.1', 9222))
    sock.close()
    
    url_sigefes = "https://sigefesmetro.sefaz.es.gov.br/Siplag4/faces/flexvision/flexvisionMain.jsp"
    
    if resultado == 0:
        print("[OK] O Google Chrome já está aberto na porta 9222.")
        return
    
    print("[Aviso] Chrome na porta 9222 não encontrado. Abrindo o navegador automaticamente...")
    caminho_chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(caminho_chrome):
        caminho_chrome = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        
    pasta_perfil = r"C:\ChromePython"
    os.makedirs(pasta_perfil, exist_ok=True)
    
    comando = [
        caminho_chrome,
        f"--remote-debugging-port=9222",
        f"--user-data-dir={pasta_perfil}",
        url_sigefes
    ]
    
    try:
        subprocess.Popen(comando)
        print("[OK] Chrome iniciado. Aguardando 6 segundos...")
        time.sleep(6.0)
    except Exception as e:
        print(f"[ERRO] Não foi possível iniciar o Chrome: {e}")

verificar_ou_abrir_chrome()

# ============================================================
# CONFIGURAÇÕES DE CAMINHOS E AMBIENTE
# ============================================================
URL_BASE = "sigefesmetro.sefaz.es.gov.br"
EXERCICIO = "2026"
UG = "440901"
DEBUGGER_ADDRESS = "127.0.0.1:9222"

pasta_downloads = r"C:\Users\joaovitorsantos\Downloads"
pasta_destino = r"\\fileserver\sesa$\FES\NEOF\JOAO VITOR\MONITORAMENTO GFES\diario cronologico"
caminho_arquivo2 = r"\\fileserver\sesa$\FES\NEOF\JOAO VITOR\MONITORAMENTO GFES\DATA CRONOLÓGICA\MONITORAMENTO ANALISE DATA CRONOLÓGICA_GFES.2026.xlsx"


def executar_com_retry(funcao, max_tentativas=15, pausa_segundos=3):
    for tentativa in range(1, max_tentativas + 1):
        try:
            return funcao()
        except Exception as err:
            if "-2147418111" in str(err) or "rejeitada" in str(err).lower():
                print(f"   [Aviso] Excel ocupado. Aguardando {pausa_segundos}s...")
                time.sleep(pausa_segundos)
            else:
                raise err
    raise Exception("O Excel permaneceu ocupado por muito tempo.")


# ============================================================
# PARTE 1: CONEXÃO E NAVEGAÇÃO
# ============================================================
print("\n--- [PARTE 1] CONECTANDO AO SIGEFES ---")

options = Options()
options.add_experimental_option("debuggerAddress", DEBUGGER_ADDRESS)
options.page_load_strategy = "eager"

try:
    driver = webdriver.Chrome(service=Service(), options=options)
    wait = WebDriverWait(driver, 25)
    print("[OK] Conectado ao Chrome.")
except Exception as erro:
    print(f"[ERRO CRÍTICO] Falha ao conectar ao Chrome: {erro}")
    raise SystemExit(1)

arquivos_antes_do_download = {p.name for p in Path(pasta_downloads).iterdir()} if Path(pasta_downloads).exists() else set()

try:
    aba_encontrada = False
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if URL_BASE in driver.current_url.lower():
            aba_encontrada = True
            break
            
    if not aba_encontrada:
        driver.get("https://sigefesmetro.sefaz.es.gov.br/Siplag4/faces/flexvision/flexvisionMain.jsp")
        time.sleep(4.0)

    driver.switch_to.default_content()

    # Navegação nos menus
    print("Acessando Relatórios -> Consultas...")
    driver.switch_to.default_content()
    
    el_rel = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[normalize-space(text())='Relatórios']")))
    driver.execute_script("arguments[0].click();", el_rel)
    time.sleep(1.2)

    el_cons = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[normalize-space(text())='Consultas']")))
    driver.execute_script("arguments[0].click();", el_cons)
    time.sleep(2.5)

    # Abrir pasta Controle por Ordem Cronológica
    print("Expandindo pasta 'Controle por Ordem Cronológica'...")
    pasta_cro = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Controle por Ordem Cronológica')]")))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", pasta_cro)
    try:
        ActionChains(driver).double_click(pasta_cro).perform()
    except Exception:
        driver.execute_script("var evt = document.createEvent('MouseEvents'); evt.initMouseEvent('dblclick', true, true, window, 2, 0,0,0,0, false,false,false,false, 0,null); arguments[0].dispatchEvent(evt);", pasta_cro)
    time.sleep(2.5)

    # Abrir relatório CRO.02
    print("Selecionando relatório 'CRO.02'...")
    cro02 = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'CRO.02 - Relatório cronológico - Pago') or contains(text(), 'CRO.02')]")))
    try:
        ActionChains(driver).double_click(cro02).perform()
    except Exception:
        driver.execute_script("var evt = document.createEvent('MouseEvents'); evt.initMouseEvent('dblclick', true, true, window, 2, 0,0,0,0, false,false,false,false, 0,null); arguments[0].dispatchEvent(evt);", cro02)
    time.sleep(2.0)

    # Clicar em Executar
    print("Clicando em 'Executar'...")
    btn_exec = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Executar') and not(contains(text(), 'Forçar'))]")))
    driver.execute_script("arguments[0].click();", btn_exec)
    time.sleep(2.0)

    # Tratar pop-up de dados online
    try:
        pop_ok = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((By.XPATH, "//button[text()='OK' or text()='Ok'] | //input[@value='OK' or @value='Ok']")))
        driver.execute_script("arguments[0].click();", pop_ok)
        time.sleep(1.5)
    except:
        pass

    # Preencher Exercício e UG
    print("Preenchendo Exercício (2026) e UG (440901)...")
    select_elem = wait.until(EC.presence_of_element_located((By.XPATH, "//tr[contains(., 'Exercício')]//select | //select[option[contains(text(), '2026')]]")))
    Select(select_elem).select_by_visible_text(EXERCICIO)
    time.sleep(0.5)

    input_ug = wait.until(EC.element_to_be_clickable((By.XPATH, "//tr[contains(., 'UG')]//input[@type='text'] | //input[contains(@id, 'UG')]")))
    input_ug.click()
    input_ug.clear()
    input_ug.send_keys(UG)
    driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles:true}));", input_ug)
    time.sleep(1.0)

    print("\n" + "="*70)
    print(" [AÇÃO NECESSÁRIA - 6 SEGUNDOS]")
    print(" O robô preencheu os parâmetros. Clique no botão 'Ok' verde")
    print(" do modal na tela do navegador agora mesmo!")
    print("="*70 + "\n")
    
    time.sleep(6.0)

except Exception as e:
    print(f"[AVISO NA ETAPA WEB]: {e}")


# ============================================================
# PARTE 2: AGUARDAR DOWNLOAD E EXECUTAR O EXCEL/VBA
# ============================================================
print("\n--- [PARTE 2] MONITORANDO O DOWNLOAD DO RELATÓRIO ---")

caminho_arquivo_baixado = None
while True:
    if Path(pasta_downloads).exists():
        arquivos_atuais = {p.name for p in Path(pasta_downloads).iterdir()}
        novos = arquivos_atuais - arquivos_antes_do_download
        candidatos = [
            n for n in novos 
            if n.lower().endswith((".xlsx", ".xls")) and not n.endswith(".crdownload") and not n.endswith(".tmp")
        ]
        if candidatos:
            mais_recente = max(candidatos, key=lambda n: (Path(pasta_downloads) / n).stat().st_mtime)
            caminho_arquivo_baixado = Path(pasta_downloads) / mais_recente
            break
    time.sleep(2)

print(f"\n[OK] Arquivo baixado detectado: {caminho_arquivo_baixado.name}")
time.sleep(2)

# --- Limpeza e processamento via win32com ---
print("Limpando pasta de destino no servidor...")
if os.path.exists(pasta_destino):
    for item in os.listdir(pasta_destino):
        caminho_item = os.path.join(pasta_destino, item)
        if os.path.isfile(caminho_item) and (item.endswith('.xlsx') or item.endswith('.xls')):
            try:
                os.remove(caminho_item)
                print(f"   Removido antigo: {item}")
            except Exception as error_rem:
                print(f"   Não foi possível remover {item}: {error_rem}")

time.sleep(2)

print("Iniciando Microsoft Excel para processamento...")
excel = win32.Dispatch("Excel.Application")
excel.Visible = True         
excel.DisplayAlerts = False  
excel.EnableEvents = False   

time.sleep(2)

try:
    print(f"Abrindo arquivo baixado: {caminho_arquivo_baixado.name}")
    workbook1 = executar_com_retry(lambda: excel.Workbooks.Open(str(caminho_arquivo_baixado)))
    time.sleep(3)

    caminho_arquivo1_destino = os.path.join(pasta_destino, caminho_arquivo_baixado.name)
    print("Salvando no servidor...")
    executar_com_retry(lambda: workbook1.SaveAs(caminho_arquivo1_destino, FileFormat=51))
    time.sleep(3)

    print("Fechando primeiro arquivo...")
    executar_com_retry(lambda: workbook1.Close(SaveChanges=True))
    time.sleep(3)

    print(f"Abrindo segundo arquivo de análise: {os.path.basename(caminho_arquivo2)}")
    workbook2 = executar_com_retry(lambda: excel.Workbooks.Open(caminho_arquivo2))
    time.sleep(4)

    print("Configurando conexões de dados para modo síncrono...")
    try:
        for conn in workbook2.Connections:
            if conn.Type == 1:    
                conn.OLEDBConnection.BackgroundQuery = False
            elif conn.Type == 2:  
                conn.ODBCConnection.BackgroundQuery = False
    except Exception as e_conn:
        print(f"   [Nota] Conexões: {e_conn}")

    time.sleep(2)

    print("Atualizando conexões (Atualizar Tudo)...")
    executar_com_retry(lambda: workbook2.RefreshAll())
    
    print("Aguardando conclusão das atualizações (30 segundos)...")
    time.sleep(30)  

    print("Salvando alterações na planilha de análise...")
    executar_com_retry(lambda: workbook2.Save())
    time.sleep(2)

    print("\n========================================================")
    print(" [SUCESSO ABSOLUTO] PROCESSO CONCLUÍDO COM SUCESSO!")
    print("========================================================")

except Exception as e:
    print(f"[ERRO CRÍTICO NO PROCESSO DO EXCEL]: {e}")

finally:
    time.sleep(2)
    try:
        executar_com_retry(lambda: setattr(excel, 'DisplayAlerts', True))
        executar_com_retry(lambda: setattr(excel, 'EnableEvents', True))
    except:
        pass