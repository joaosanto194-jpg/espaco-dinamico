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

## Pendências / próximos passos

1. Testar o portal da família localmente (gerar link → "Abrir o portal (testar)").
2. Publicar no Streamlit Cloud (app público) para a família abrir pelo celular; antes, migrar dados do SQLite local para o Supabase (no Cloud o SQLite se perde a cada reinício). Cadastrar a URL pública em Configurações.
3. Guarda documental: falta configurar `[supabase]` (url, service_role_key, bucket) nos secrets e criar o bucket privado `documentos-clinicos`.
4. Planilha Google aberta "a qualquer pessoa com o link" é risco LGPD → ler com conta de serviço (gspread) e fechar a planilha.
5. Valores em dinheiro estão em `Float` → avaliar `Numeric(10,2)` com migração e backup.
6. Ideias: relatórios, agenda de atendimentos, recibos.
