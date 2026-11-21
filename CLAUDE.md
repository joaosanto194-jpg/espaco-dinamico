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

## ✍️ Atividade com caneta (folhas interativas, modo atendimento)

- Fluxo: atividade pronta (Canva/Word/Excel exportada em PDF) importada em 📎 Materiais em PDF → "Começar a preencher" → o aluno escreve com mesa digitalizadora/caneta/dedo → "Concluir" gera um PDF (fundo + tinta) que vai para o Caderno Digital, privado por padrão.
- Componente próprio em `componentes/caderno_canvas/index.html` (`components.v1.declare_component`, protocolo postMessage sem build). Usa Pointer Events com pressão; o botão-borracha da caneta apaga; opção "Só caneta" ignora o toque da mão. Desfazer/refazer, marca-texto, salvamento automático 700 ms após cada traço. O componente só reinicia quando muda `chave` (folha-página).
- Tabelas: `folhas_interativas` (material, aluno, status Em andamento/Concluída/Cancelada, documento_id do PDF final) e `folhas_paginas` (tinta PNG base64 por página, no banco, porque o bucket aceita só PDF).
- Páginas renderizadas com pypdfium2 a 1100 px (`imagem_pagina`, em cache); PDF final montado com Pillow no tamanho físico original.
- Não alterar `st.session_state["modo_aluno"]` depois do toggle: o Streamlit proíbe (o toggle some sozinho quando a folha fecha).
- "✅ Concluir" (dois cliques) e "⏸️ Continuar depois" ficam DENTRO do componente e vão na mesma mensagem que a tinta mais recente (`acao` no valor). Python grava a tinta e só então executa a ação. Botões Python fora do componente perdiam o último traço (corrida com o salvamento automático de 700 ms). Barra com larguras fixas e status em linha própria, para os botões não se moverem.
- Após concluir: `aviso_folha_concluida` mostra a confirmação, e "Ver no Caderno Digital" (callback `ir_para_caderno`) troca `menu_principal` e pré-seleciona o registro. Na lista "Continuar de onde parou" há "✅ Concluir agora".
- Ideia futura: tarefas de casa pelo portal da família usando o mesmo componente.

## Pendências / próximos passos

1. Testar o portal da família localmente (gerar link → "Abrir o portal (testar)").
2. Publicar no Streamlit Cloud (app público) para a família abrir pelo celular; antes, migrar dados do SQLite local para o Supabase (no Cloud o SQLite se perde a cada reinício). Cadastrar a URL pública em Configurações.
3. Guarda documental: falta configurar `[supabase]` (url, service_role_key, bucket) nos secrets e criar o bucket privado `documentos-clinicos`.
4. Planilha Google aberta "a qualquer pessoa com o link" é risco LGPD → ler com conta de serviço (gspread) e fechar a planilha.
5. Valores em dinheiro estão em `Float` → avaliar `Numeric(10,2)` com migração e backup.
6. Ideias: relatórios, agenda de atendimentos, recibos.
