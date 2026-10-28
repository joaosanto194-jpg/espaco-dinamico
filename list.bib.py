import importlib.metadata

def listar_pacotes_instalados():
    print("--- PACOTES INSTALADOS NO SEU AMBIENTE PYTHON ---")
    try:
        # Pega todas as distribuições instaladas
        distribuicoes = sorted(importlib.metadata.distributions(), key=lambda d: d.metadata['Name'].lower())
        
        for d in distribuicoes:
            nome = d.metadata['Name']
            versao = d.version
            print(f"{nome} == {versao}")
            
        print(f"\nTotal de pacotes encontrados: {len(list(importlib.metadata.distributions()))}")
    except Exception as e:
        print(f"Erro ao listar pacotes: {e}")

if __name__ == "__main__":
    listar_pacotes_instalados()