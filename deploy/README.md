# Deploy no Railway — dois serviços separados

Este projeto vira **dois serviços independentes** no Railway, ambos a partir do
**mesmo repositório GitHub**, cada um com seu próprio `Dockerfile` e suas próprias
variáveis. A separação é de propósito: o **site** não recebe as senhas dos portais,
então elas nunca ficam na máquina exposta à internet.

| Serviço | Dockerfile | O que faz | Rede |
|---|---|---|---|
| **site** | `deploy/site.Dockerfile` | formulário Flask (gunicorn) | domínio público |
| **robo** | `deploy/robo.Dockerfile` | processa a fila nos portais (Selenium) | **sem** domínio; roda como **Cron** |

---

## 1. Serviço `site` (formulário)

1. **New Project → Deploy from GitHub repo** → escolha `projeto_cadastros`.
2. Em **Settings → Build**, defina **Dockerfile Path** = `deploy/site.Dockerfile`.
3. Em **Settings → Networking**, clique **Generate Domain** (gera o link do formulário).
4. Em **Variables**, adicione:

   ```
   FLASK_SECRET_KEY=<chave aleatoria longa>
   GOOGLE_CREDENTIALS_JSON=<cole o conteudo inteiro do credentials_google.json>
   SHEET_CREDENCIAIS_ID=...
   SHEET_REGISTROS_ID=...
   ABA_SENHA=senha
   ABA_EMAILS=emails
   ABA_MAPA=mapa_projeto
   ABA_PORTAL=cadastros
   ABA_FILA=fila
   # Notificacao (opcional)
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=...
   SMTP_PASSWORD=...
   EMAIL_FROM=...
   ```

   > **Não** coloque `FLASK_DEBUG` (fica desligado) nem `LIGO_*`/`AYTY_*` aqui —
   > o site não precisa das senhas dos portais.

---

## 2. Serviço `robo` (Cron diário)

1. No **mesmo projeto**, **New → GitHub Repo** → o mesmo `projeto_cadastros`.
2. Em **Settings → Build**, defina **Dockerfile Path** = `deploy/robo.Dockerfile`.
3. Em **Settings → Deploy → Cron Schedule**, defina o horário (UTC). Configurado
   para **17:00 de Brasília** = **20:00 UTC** (UTC−3):

   ```
   0 20 * * *
   ```

   O container roda `robo.py --portal ambos`, processa a fila nos dois portais e
   **encerra**. Nos dias sem ninguém na fila ele sai em segundos, sem abrir o Chrome.
4. **Não** gere domínio público (é um worker, não um site).
5. Em **Variables**, adicione:

   ```
   GOOGLE_CREDENTIALS_JSON=<mesmo JSON do credentials_google.json>
   SHEET_CREDENCIAIS_ID=...
   SHEET_REGISTROS_ID=...
   ABA_SENHA=senha
   ABA_EMAILS=emails
   ABA_MAPA=mapa_projeto
   ABA_PORTAL=cadastros
   ABA_FILA=fila
   # Credenciais dos portais (SO aqui, no robo)
   LIGO_USER=...
   LIGO_PASSWORD=...
   AYTY_USER=...
   AYTY_PASSWORD=...
   # Opcional
   AYTY_SUPERVISOR_DISTRATO=teste code7
   ```

   > `HEADLESS`, `CHROME_BINARY` e `CHROMEDRIVER_PATH` **já vêm definidos** pelo
   > `deploy/robo.Dockerfile` — não precisa repetir aqui.

---

## Observações

- **`GOOGLE_CREDENTIALS_JSON`**: cole o conteúdo do `credentials_google.json`
  inteiro (o Railway aceita valor multilinha). É o mesmo em ambos os serviços.
- **Fuso do Cron**: o Railway usa **UTC**. Brasília = UTC−3.
- **Rodar sob demanda**: no serviço `robo`, use **Deploy → Redeploy** para forçar
  uma execução fora do horário do cron.
- **Testar o robô sem tocar nos portais**: `python src/robo.py --portal ambos --dry-run`.
- **Chave nova de sessão**: gere `FLASK_SECRET_KEY` com
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
