import os
import time
import win32com.client as win32

# 1. Definir caminhos das pastas
pasta_downloads = r"C:\Users\joaovitorsantos\Downloads"

# --- NOVA PASTA DE DESTINO ---
pasta_destino = r"C:\Users\joaovitorsantos\Documents\GFES - JOAO VITOR\RELATÓRIO_GERAL\FES24"

# Caminho do segundo arquivo que será aberto e atualizado
caminho_arquivo2 = r"\\fileserver\sesa$\FES\NEOF\JOAO VITOR\MONITORAMENTO GFES\EMPENHO EM ABERTO - REDE SESA\SALDO DE EMPENHO EM ABERTO - REDE SAÚDE.xls


# --- PASSO 1: Localizar o arquivo Excel mais recente em Downloads ---
arquivos_excel = [
    os.path.join(pasta_downloads, f) 
    for f in os.listdir(pasta_downloads) 
    if f.endswith('.xlsx') or f.endswith('.xls')
]

if not arquivos_excel:
    print("Nenhum arquivo Excel encontrado na pasta Downloads.")
else:
    # Seleciona o arquivo mais recente baixado na pasta Downloads
    arquivo_original_caminho = max(arquivos_excel, key=os.path.getmtime)
    nome_do_arquivo = os.path.basename(arquivo_original_caminho)
    caminho_arquivo1_destino = os.path.join(pasta_destino, nome_do_arquivo)
    
    print(f"Arquivo recente identificado em Downloads: {nome_do_arquivo}")

    # --- PASSO 2: Limpar arquivos velhos de dados na pasta destino ---
    print(f"Limpando arquivos velhos na pasta de destino ({pasta_destino})...")
    if os.path.exists(pasta_destino):
        for item in os.listdir(pasta_destino):
            caminho_item = os.path.join(pasta_destino, item)
            # Evita apagar a própria planilha principal de análise caso esteja na mesma pasta
            if os.path.isfile(caminho_item) and (item.endswith('.xlsx') or item.endswith('.xls')):
                if caminho_item.lower() != caminho_arquivo2.lower():
                    try:
                        os.remove(caminho_item)
                        print(f"Arquivo antigo removido: {item}")
                    except Exception as error_rem:
                        print(f"Não foi possível remover {item}: {error_rem}")

    # --- PASSO 3: Iniciar a aplicação do Excel via Python ---
    excel = win32.Dispatch("Excel.Application")
    excel.Visible = True         # Exibe a janela do Excel
    excel.DisplayAlerts = False  # Desativa alertas de substituição
    excel.EnableEvents = False   # Desativa macros automáticas na abertura

    try:
        # Abrir o arquivo baixado em Downloads
        workbook1 = excel.Workbooks.Open(arquivo_original_caminho)
        print("Primeiro arquivo aberto no Excel.")

        # Salvar no novo caminho de destino mantendo o nome original
        workbook1.SaveAs(caminho_arquivo1_destino, FileFormat=51)
        print(f"Novo arquivo salvo com sucesso em: {caminho_arquivo1_destino}")

        # Fechar o primeiro arquivo
        workbook1.Close(SaveChanges=True)
        print("Primeiro arquivo fechado.")

        # --- PASSO 4: Abrir o segundo arquivo na rede ---
        print(f"Abrindo o segundo arquivo: {caminho_arquivo2}")
        workbook2 = excel.Workbooks.Open(caminho_arquivo2)
        print("Segundo arquivo aberto com sucesso!")

        # --- PASSO 5: Atualizar todas as conexões de dados ---
        print("Atualizando todas as conexões de dados (Dados > Atualizar Tudo)...")
        workbook2.RefreshAll()
        
        # Aguarda 15 segundos para dar tempo ao Power Query/Conexões de carregarem
        print("Aguardando o Excel concluir o processamento dos dados...")
        time.sleep(15)

        # Loop de verificação de liberação da instância do Excel
        atualizado = False
        tentativas = 0
        while not atualizado and tentativas < 10:
            try:
                excel.StatusBar = "Conexões atualizadas pelo Python."
                atualizado = True
            except:
                tentativas += 1
                print(f"Excel processando... aguardando 5 segundos (Tentativa {tentativas}/10)")
                time.sleep(5)

        print("Todas as conexões foram atualizadas com sucesso!")

    except Exception as e:
        print(f"Ocorreu um erro durante o processo: {e}")

    finally:
        # Reativa configurações padrões do Excel
        try:
            excel.DisplayAlerts = True
            excel.EnableEvents = True
            excel.StatusBar = False
        except:
            pass