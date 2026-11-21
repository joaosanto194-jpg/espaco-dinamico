# Espaço Dinâmico — Sistema de Gestão Neuropsicopedagógica

Contexto do projeto para o Claude Code. Responda e escreva comentários em português.

## O que é

App Streamlit de gestão da clínica Espaço Dinâmico (profissional: Larissa Lyrio, Neuropsicopedagoga). Arquivo único: `app.py`. Ambiente: Windows, VS Code, venv em `.venv`, Python 3.15.

**Como rodar:** `streamlit run app.py` (ou `python -m streamlit run app.py`). Nunca `python app.py` / `py app.py`: isso gera só avisos "missing ScriptRunContext" e não abre nada.

## Stack

- Streamlit (versão recente: usar `width="stretch"`, NÃO `use_container_width`)
- SQLAlchemy ORM. Banco: PostgreSQL/Supabase via `st.secrets["database"]`; sem secrets cai para SQLite local `espaco_dinamico.db`
- Supabase Storage (bucket privado `documentos-clinicos`) para PDFs da guarda documental, via `st.secrets["supabase"]`
- Google Sheets (planilha mestre, aba "OBSERVAÇÃO DO ATENDIMENTO") lida como CSV público para os indicadores de desempenho
- pandas, plotly

## Telas e permissões

Menu e acesso definidos em `MENU_PAGINAS` e `PERMISSOES`:

- **Admin:** tudo
- **Profissional:** Painel, Alunos e responsáveis, Prontuários, Atividades, Guarda documental, Desempenho
- **Financeiro:** Painel, Alunos e responsáveis, Contratos, Financeiro (sem prontuários/documentos: LGPD)
- **Todos:** 🔑 Minha senha

## Regras do projeto (manter)

- Migrações somente aditivas (`aplicar_migracoes_aditivas`): nunca apagar/reescrever dados existentes. Tabelas novas via `Base.metadata.create_all`.
- Engine e inicialização do banco ficam em `@st.cache_resource` (`criar_engine`, `inicializar_banco`), não rodar a cada rerun.
- `inicializar_banco(versao_esquema())`: a assinatura do esquema é o argumento do cache. O Streamlit Cloud atualiza o código sem reiniciar o processo, então, sem isso, colunas novas não eram criadas (erro "acesso ao banco de dados"). No `main`, `erro_de_esquema` refaz a migração uma vez como rede de segurança.
- Toda gravação em `try/except SQLAlchemyError` com `db.rollback()` e `mensagem_erro(...)`; não exibir detalhes técnicos na tela.
- Ações relevantes registradas com `registrar_auditoria(acao, detalhe)` (tabela `log_auditoria`).
- Senhas: PBKDF2-SHA256 com sal (`gerar_hash_senha` / `verificar_senha`); hashes SHA-256 legados são convertidos no login. Senha padrão `admin123` ou < 8 caracteres força troca.
- Status de atividade: usar `normalizar_status_atividade` (registros antigos têm "Realizado").
- Nunca colocar chaves (service_role, senha do banco) no código; só em `.streamlit/secrets.toml` (fora do git) ou Secrets do Streamlit Cloud.

## Já implementado (sessão de 19–20/11/2026)

- Portal da família: tabela `links_familiares` (guarda só o SHA-256 do token), tela 📈 Desempenho → 🔗 Links para as famílias: gerar (validade 30/90/180/365 dias), revogar, contagem de acessos, envio por WhatsApp, botão "Abrir o portal (testar)". Página pública em `?portal=TOKEN` (`renderizar_portal_familiar`) mostra só indicadores, evolução, compreensão, dificuldades, conteúdos e atividades — nunca prontuário, documentos ou financeiro.
- URL do link: usa `app_url` de ⚙️ Configurações; se vazia, detecta pelo navegador (`detectar_url_base`). Em localhost avisa que o link só funciona na máquina.
- Contratos → 🧾 Gerar mensalidades do mês (sem duplicar; dia 31 vira último dia do mês).
- Indicadores financeiros (a receber, em atraso, recebido, saldo) no Painel e no Financeiro; filtro "Em atraso".
- Configurações institucionais lidas do banco; registro de auditoria visível em Configurações.
- Correções: data de nascimento sobrescrita com hoje ao editar aluno; status "Realizado" virando "Planejada"; proteção do último Admin; link de PDF gerado só sob demanda.

## Já implementado (20/11/2026, tarde)

- Publicado no Streamlit Cloud; o app publicado usa o PostgreSQL do Supabase (`[database]` nos Secrets do Cloud). Backup CSV antes de publicar fica em `backups_banco/` (fora do git).
- Recibos em PDF (reportlab) para receitas pagas, em 💰 Financeiro; `documento_profissional` e `cidade` em Configurações.
- `painel_storage(usuario, prefixo)`: diagnóstico do Supabase Storage + botão para criar o bucket privado. Usado pela Guarda documental e pelos Materiais.
- 📁 Atividades → 📎 Materiais em PDF: tabela `materiais_pedagogicos`. Importa vários PDFs (Atividade / Material escolar / Avaliação), para um aluno ou o acervo geral (`aluno_id` NULL), e pode criar uma atividade planejada por arquivo. O texto é extraído com pypdf para a busca, sem `\x00`, que o Postgres recusa. Biblioteca com filtros, busca dentro do PDF, link temporário, edição, vínculo a uma atividade e arquivamento. Arquivos ficam em `materiais/...` no mesmo bucket.

## Caderno Digital (antiga Guarda documental)

- Menu "📓 Caderno Digital" (`tela_caderno_digital`), mesma tabela `documentos_alunos` e mesmo bucket. Abas: Adicionar ao caderno, Consultar e compartilhar, Como alimentar (`DICAS_CADERNO`).
- Colunas aditivas (`MIGRACOES_ADITIVAS`): `visivel_familia` (padrão 0: documentos antigos ficam privados), `mensagem_familia` (texto para os pais; `descricao` é anotação interna), `compartilhado_em`, `visualizacoes_familia`.
- Portal (`renderizar_caderno_portal`): mostra só registros do aluno do link, ativos e com `visivel_familia = 1`. O link do PDF é gerado só no clique e soma uma visualização. `CATEGORIAS_SENSIVEIS` (laudo, contrato, autorização, comprovante) só são compartilhadas com confirmação explícita.

- Visualização do PDF **dentro do sistema** (`visualizar_pdf_inline`: páginas como imagens + download), no Caderno ("👁️ Ver o PDF aqui") e no portal ("📄 Ver a atividade"). Não depende de link externo do Supabase, que celulares e o navegador do WhatsApp bloqueiam. Conta uma visualização da família por sessão.
- No Caderno, a seção de compartilhamento avisa quando o registro está 🔒 privado e mostra a situação do link da família (`bloco_link_familia`), com botão para gerar o link (180 dias) e enviar pelo WhatsApp sem sair da tela.

## ✍️ Atividade com caneta (folhas interativas, modo atendimento)

- Fluxo: atividade pronta (Canva/Word/Excel exportada em PDF) importada em 📎 Materiais em PDF → "Começar a preencher" → o aluno escreve com mesa digitalizadora/caneta/dedo → "Concluir" gera um PDF (fundo + tinta) que vai para o Caderno Digital, privado por padrão.
- Componente próprio em `componentes/caderno_canvas/index.html` (`components.v1.declare_component`, protocolo postMessage sem build). Usa Pointer Events com pressão; o botão-borracha da caneta apaga; opção "Só caneta" ignora o toque da mão. Desfazer/refazer, marca-texto, salvamento automático 700 ms após cada traço. O componente só reinicia quando muda `chave` (folha-página).
- Tabelas: `folhas_interativas` (material, aluno, status Em andamento/Concluída/Cancelada, documento_id do PDF final) e `folhas_paginas` (tinta PNG base64 por página, no banco, porque o bucket aceita só PDF).
- Páginas renderizadas com pypdfium2 a 1100 px (`imagem_pagina`, em cache); PDF final montado com Pillow no tamanho físico original.
- Não alterar `st.session_state["modo_aluno"]` depois do toggle: o Streamlit proíbe (o toggle some sozinho quando a folha fecha).
- "✅ Concluir" (dois cliques) e "⏸️ Continuar depois" ficam DENTRO do componente e vão na mesma mensagem que a tinta mais recente (`acao` no valor). Python grava a tinta e só então executa a ação. Botões Python fora do componente perdiam o último traço (corrida com o salvamento automático de 700 ms). Barra com larguras fixas e status em linha própria, para os botões não se moverem.
- Após concluir: `aviso_folha_concluida` mostra a confirmação, e "Ver no Caderno Digital" (callback `ir_para_caderno`) troca `menu_principal` e pré-seleciona o registro. Na lista "Continuar de onde parou" há "✅ Concluir agora".
- Ideia futura: tarefas de casa pelo portal da família usando o mesmo componente.

## Painel e layout (21/11/2026)

- Painel: mini DRE (`dre_do_mes` + `html_mini_dre`; agrupa por `categoria` pura, porque `COALESCE` no GROUP BY quebra no PostgreSQL) em regime de caixa (Pago com data de pagamento no mês), com detalhe por categoria, margem e seletor de mês/ano. Ao lado ficam "A receber" e "Em atraso".
- Cabeçalho fixo: o sticky fica em `div[data-testid="stElementContainer"]:has(.ed-header)` (no `stMarkdown` interno não funcionava). Cabeçalho compacto.
- Menu lateral com 240 px: o seletor é `section[data-testid="stSidebar"][data-collapsed="false"]` (o Streamlit 1.66 não usa `aria-expanded`). Margens da página com 2rem.

## Desempenho (21/11/2026)

- `renderizar_analise_desempenho`: 🗺️ Mapa dos pontos avaliados (heatmap: linhas = 6 pontos + "Compreendeu o conteúdo"; colunas = atendimentos; N/D/S e duas marcações N/D, D/S), 📊 Retrato de cada ponto (barras 100% + tendência ▲▬▼ comparando os 3 primeiros com os 3 últimos, pela ordem da escala e não como nota), 🎯 Dificuldades apresentadas (`grafico_dificuldades`, cores da logo `PALETA_LOGO`, "N de total · %", itens únicos em "Outras"). "Detalhar um ponto" e a tabela de evolução ficam em painéis recolhíveis. A tabela não aparece no portal.
- Escala lida por `nivel_da_resposta` (Necessita=0, Em desenvolvimento=1, Satisfatório=2; compreensão Não/Parcialmente/Sim).
- A coluna de compreensão é localizada por ("compreens", "conte") excluindo "orienta". Antes pegava "[Compreensão das orientações]" por engano.

## Serviços, contratos e relatório anual (21/11/2026)

- Serviços oferecidos em ⚙️ Configurações (`servicos`, um por linha; `lista_servicos`). A lista suspensa aparece em Contratos (novo e edição) e no Financeiro. `opcoes_com_atual` preserva valores antigos fora da lista.
- `lancamentos_financeiros.servico` (migração aditiva). Mensalidades geradas herdam o `descricao_servico` do contrato.
- Novo contrato começa vazio (`index=None`, `value=None`); aluno, serviço, mensalidade e dia são obrigatórios.
- 💰 Financeiro → 📊 Relatório anual (`tela_relatorio_anual`), em visão Caixa (pagos, pela data de pagamento) ou Competência (pelo vencimento, sem cancelados):
  - indicadores com comparação ao mesmo período do ano anterior quando o ano está em andamento;
  - receita recorrente dos contratos ativos e cobertura da despesa média;
  - leituras para decisão (o "$" é escapado no Markdown);
  - gráfico mensal, DRE anual por categoria × mês (`html_dre_anual`, sem acumulado nos meses futuros);
  - receita por serviço e por aluno, despesas por categoria, previsto × recebido e inadimplência;
  - exportação em Excel (openpyxl), uma aba por seção.

## Alunos inativos (21/11/2026)

- Inativar nunca apaga dados. Alunos e responsáveis → 🔎 Consultar alunos (`tela_consulta_alunos`) filtra Ativos / Inativos / Todos e busca por aluno ou responsável. Mostra o contrato, a contagem de lançamentos e, só para Admin e Profissional (LGPD), prontuários, atividades, caderno e último registro. Exporta em CSV.
- O Painel tem o filtro de situação e mostra a métrica de inativos. Prontuários e Desempenho (análise) têm a opção "Incluir alunos inativos". As telas de criação (novo contrato, nova atividade, atividade com caneta, links da família) continuam só com alunos ativos.
- Funções auxiliares: `SITUACOES_ALUNO`, `filtrar_por_situacao`, `rotulo_aluno` (sufixo "(inativo)").

## Portal da família por seções (21/11/2026)

- Cada link (`links_familiares`) guarda o que a família vê: `ver_caderno`, `ver_desempenho`, `ver_atividades` (colunas aditivas com padrão 1, então links antigos veem tudo). `SECOES_PORTAL` e `secoes_do_link`.
- A escolha é feita ao gerar o link (📈 Desempenho → 🔗 Links) e pode ser mudada depois em "Mudar o que a família vê", sem gerar novo link. O bloco do Caderno avisa quando o link não mostra o Caderno.
- O portal mostra só as seções liberadas, em abas quando há mais de uma.

## Exclusão definitiva (21/11/2026)

- Perfis Admin e Profissional (`pode_excluir`). Painel "🗑️ Excluir definitivamente" com confirmação (`confirmar_exclusao`) em: Caderno (registro + PDF), Materiais em PDF (material + folhas com caneta derivadas + PDF), Atividades pedagógicas e Atividade com caneta (folha + escrita).
- Funções `excluir_documento`, `excluir_material`, `excluir_folha` e `excluir_atividade`: apagam no banco primeiro (desfazem vínculos: `documento_id` e `atividade_id` viram NULL) e depois o arquivo no Storage, sem bloquear se o Storage falhar. Tudo vai para a auditoria (`*_excluido/a`).
- Testado com chaves estrangeiras verificadas (como no PostgreSQL). Arquivar/cancelar continuam existindo como opção sem perda.

## Situação (21/11/2026)

**Homologação DEFINITIVA pela usuária em 21/11/2026 (versão `b96237b`); em uso no Streamlit Cloud** (app publicado com PostgreSQL/Supabase e Storage configurados). Novos ajustes só quando ela acionar. Antes de cada publicação: backup CSV do Supabase em `backups_banco/`, testes locais (SQLite + Storage simulado) e conferência no PostgreSQL, que é mais rígido que o SQLite (ex.: GROUP BY).

## Pendências / próximos passos

1. Segurança: a senha do banco foi exposta numa conversa. Trocar no Supabase e atualizar os Secrets do Cloud.
2. Cadastrar a URL pública do app em ⚙️ Configurações (hoje vazia: o link da família usa o endereço detectado pelo navegador).
3. Fuso horário: o Cloud roda em UTC (3 h à frente de Brasília). Horários da auditoria, dos links e dos recibos, e o "hoje" depois das 21h, podem sair errados. Usar `America/Sao_Paulo`.
4. Planilha Google aberta "a qualquer pessoa com o link" é risco LGPD: ler com conta de serviço (gspread) e fechar a planilha.
5. Valores em dinheiro estão em `Float`: avaliar `Numeric(10,2)` com migração e backup.
6. Lançamentos antigos sem `servico` aparecem como "Não informado" no relatório anual (editar no Financeiro).
7. Limpeza: cópias antigas fora do git (`app - Copia*.py`, `teste/`, `streamlit`, scripts avulsos).
8. Ideias: tarefas de casa pelo portal da família com o componente de caneta; agenda de atendimentos.
