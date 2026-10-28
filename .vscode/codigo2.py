import os
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

class RoboConformidade:
    def __init__(self):

        import os
        import urllib.parse
        import zipfile

        #configuração do proxy
        PROXY_USER = "joaovitorsantos"
        PROXY_PASS = "Jll@097531"
        PROXY_HOST = "sesa3.proxy.dcpr.es.gov.br"
        PROXY_PORT = "1894"

        # Codifica o usuário e senha para evitar problemas com caracteres especiais
        user_encoded = urllib.parse.quote_plus(PROXY_USER)
        pass_encoded = urllib.parse.quote_plus(PROXY_PASS)

        # Configura o Proxy para o ChromeDriverManager (via variáveis de ambiente temporárias)
        proxy_url = f"http://{user_encoded}:{pass_encoded}@{PROXY_HOST}:{PROXY_PORT}"
        os.environ["HTTP_PROXY"] = proxy_url
        os.environ["HTTPS_PROXY"] = proxy_url
        os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"

        

        chrome_options = Options()
        chrome_options.add_experimental_option("detach", True)
        
        # Argumentos adicionais para maior estabilidade do driver
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Caminho absoluto da pasta Downloads
        self.download_dir = str(Path.home() / "Downloads")

        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True 
        }
        chrome_options.add_experimental_option("prefs", prefs)

        # Configura a Autenticação do Proxy para o Navegador Chrome (via Extensão Temporária)
        # O Chrome não aceita usuário:senha na URL do proxy nativamente, então criamos um plugin em tempo de execução
        
        manifest_json = """
        {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Chrome Proxy",
            "permissions": [
                "proxy",
                "tabs",
                "unlimitedStorage",
                "storage",
                "<all_urls>",
                "webRequest",
                "webRequestBlocking"
            ],
            "background": {
                "scripts": ["background.js"]
            },
            "minimum_chrome_version":"22.0.0"
        }
        """

        background_js = f"""
        var config = {{
            mode: "fixed_servers",
            rules: {{
              singleProxy: {{
                scheme: "http",
                host: "{PROXY_HOST}",
                port: parseInt({PROXY_PORT})
              }},
              bypassList: ["localhost", "127.0.0.1"]
            }}
          }};

        chrome.proxy.settings.set({{value: config, scope: "regular"}}, function({{}});

        chrome.webRequest.onAuthRequired.addListener(
            function(details) {{
                return {{
                    authCredentials: {{
                        username: "{PROXY_USER}",
                        password: "{PROXY_PASS}"
                    }}
                }};
            }},
            {{urls: ["<all_urls>"]}},
            ['blocking']
        );
        """

        # Salva o plugin de autenticação em um arquivo zip temporário
        plugin_path = os.path.join(os.getcwd(), "proxy_auth_plugin.zip")
        with zipfile.ZipFile(plugin_path, 'w') as zp:
            zp.writestr("manifest.json", manifest_json)
            zp.writestr("background.js", background_js)
        
        # Adiciona a extensão de autenticação ao Chrome
        chrome_options.add_extension(plugin_path)

        # Inicializa o driver com as configurações prontas
        try:
            driver_path = ChromeDriverManager().install()
            self.driver = webdriver.Chrome(service=Service(driver_path), options=chrome_options)
        finally:
            # Remove o arquivo zip temporário do plugin após iniciar o navegador
            if os.path.exists(plugin_path):
                try:
                    os.remove(plugin_path)
                except Exception:
                    pass

    def clicar(self, xpath: str, timeout: int = 20):
        """Tenta clicar normalmente via Selenium; se houver interceptação, força via JavaScript."""
        wait = WebDriverWait(self.driver, timeout)
        try:
            elemento = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            # Rola a tela até o elemento para evitar que menus ou cabeçalhos o cubram
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
            elemento.click()
        except Exception:
            # Fallback caso haja sobreposição de elementos na tela
            elemento = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            self.driver.execute_script("arguments[0].click();", elemento)

    def aguardar_download(self, timeout: int = 30):
        """Verifica na pasta se o arquivo terminou de baixar (remove arquivos provisórios .crdownload)."""
        tempo_inicio = time.time()
        while time.time() - tempo_inicio < timeout:
            # Verifica se há algum arquivo sendo baixado no momento
            baixando = any(f.endswith(".crdownload") or f.endswith(".tmp") for f in os.listdir(self.download_dir))
            if not baixando:
                return True
            time.sleep(1)
        return False

    def etapa_1_analise_documental(self):
        try:
            print("📂 Localizando pasta 'JOAO VITOR - LEITOS'...")
            xpath_pasta = "//a[contains(text(), 'JOAO VITOR - LEITOS')]"
            self.clicar(xpath_pasta)
            
            print("📄 Abrindo o primeiro processo para análise...")
            xpath_primeiro_processo = "//table//tbody/tr[1]//a" 
            self.clicar(xpath_primeiro_processo)

            print("🔍 Concluindo análise documental (baixando documento base)...")
            xpath_download_pdf = "//a[contains(@id, 'download') or contains(text(), 'PDF')]" 
            self.clicar(xpath_download_pdf)
            
            if self.aguardar_download():
                print("✅ Análise Documental Concluída e Download Finalizado!")
            else:
                print("⚠️ O tempo limite do download expirou.")

        except Exception as e:
            print(f"❌ Erro na Etapa 1: {e}")

if __name__ == "__main__":
    bot = RoboConformidade()
    print("\n" + "="*50)
    print("SISTEMA INICIADO")
    print("1. Faça o login no E-Docs")
    print("2. Navegue até a tela inicial das pastas")
    print("3. Volte aqui e pressione ENTER")
    print("="*50 + "\n")
    
    input("Aguardando login... Pressione ENTER para iniciar a análise...")
    bot.etapa_1_analise_documental()