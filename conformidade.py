import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ============================================================
# 1. FUNÇÃO AUXILIAR PARA ABRIR PEÇA E LER TEXTO NO IFRAME
# ============================================================
def extrair_texto_da_peca(driver, wait, xpath_peca, nome_peca):
    """Clica no ato processual, entra no iframe do PDF e extrai o texto."""
    print(f"   -> Lendo peça: {nome_peca}...")
    try:
        item = wait.until(EC.presence_of_element_located((By.XPATH, xpath_peca)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", item)
        time.sleep(2.5)  # Tempo para o PDF carregar no iframe

        texto = ""
        try:
            iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "iframe#iframe-arquivo, iframe.scd-frame-arquivo")))
            driver.switch_to.frame(iframe)
            texto = driver.find_element(By.TAG_NAME, "body").text
            driver.switch_to.default_content()
        except Exception:
            driver.switch_to.default_content()
            
        return texto

    except Exception:
        print(f"      [Aviso] Peça '{nome_peca}' não localizada.")
        return ""

# ============================================================
# 2. FUNÇÃO DE ANÁLISE DE CONFORMIDADE DO PROCESSO ABERTO
# ============================================================
def analisar_processo_atual(driver, wait):
    dados = {
        'credor': None,
        'nota_fiscal': None,
        'valor': None,
        'ateste_confirmado': False
    }

    # 1. VERDE (Último Despacho/Termo)
    xpath_verde = "//*[contains(text(), '#13') or contains(text(), 'enseada prime') or contains(text(), 'TERMO DE ENTRANHAMENTO')]"
    txt_verde = extrair_texto_da_peca(driver, wait, xpath_verde, "Último Despacho (Verde)")
    m_val = re.search(r'R\$\s?([\d\.]+\,\d{2})', txt_verde)
    m_nf = re.search(r'(?:Nota Fiscal|NF)[\:\s]+(\d+)', txt_verde, re.IGNORECASE)
    if m_val: dados['valor'] = m_val.group(1)
    if m_nf: dados['nota_fiscal'] = m_nf.group(1)

    # 2. AZUL (Despacho para Pagamento)
    xpath_azul = "//*[contains(text(), '#10') or contains(text(), 'Despacho para pagamento')]"
    txt_azul = extrair_texto_da_peca(driver, wait, xpath_azul, "Despacho Pagamento (Azul)")
    if "ENSEADA PRIME" in txt_azul.upper():
        dados['credor'] = "ENSEADA PRIME HOSPITAL LTDA"

    # 3. LARANJA (Despacho de Ateste)
    xpath_laranja = "//*[contains(text(), '#8') or contains(text(), 'DESPACHO DE ATESTE')]"
    txt_laranja = extrair_texto_da_peca(driver, wait, xpath_laranja, "Despacho de Ateste (Laranja)")
    if "ATESTO" in txt_laranja.upper() or "CONFORME" in txt_laranja.upper():
        dados['ateste_confirmado'] = True

    # 4. ROSA (Nota Fiscal)
    xpath_rosa = "//*[contains(text(), '#5') or contains(text(), 'NOTA FISCAL')]"
    txt_rosa = extrair_texto_da_peca(driver, wait, xpath_rosa, "Nota Fiscal (Rosa)")
    if not dados['nota_fiscal']:
        m_nf_rosa = re.search(r'(\d{3,8})', txt_rosa)
        if m_nf_rosa: dados['nota_fiscal'] = m_nf_rosa.group(1)

    return dados

# ============================================================
# 3. FLUXO PRINCIPAL DE EXECUÇÃO
# ============================================================
def executar_automacao_lote():
    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    service = Service()

    try:
        print("Conectando instantaneamente ao Chrome aberto...")
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 10)
        print("[OK] Chrome conectado com sucesso!")
        
        # Executa a análise na aba ativa do processo atual
        resultado = analisar_processo_atual(driver, wait)
        print("\n--- RESULTADO DA ANÁLISE DE CONFORMIDADE ---")
        for k, v in resultado.items():
            print(f"  {k}: {v}")
            
    except Exception as e:
        print(f"[ERRO] Falha na conexão ou execução: {e}")

if __name__ == "__main__":
    executar_automacao_lote()