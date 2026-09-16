# -*- coding: utf-8 -*-
"""Configuracoes centrais do projeto, carregadas do arquivo .env.

Compartilhado pelo site (app.py) e pelo robo (robo.py) para evitar duplicacao.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

# Este modulo vive em src/; a raiz do projeto (onde ficam .env e o JSON de
# credenciais) e a pasta acima.
PASTA_SRC = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(PASTA_SRC)

load_dotenv(os.path.join(RAIZ, ".env"))


def _abs(caminho: str) -> str:
    """Resolve um caminho relativo em relacao a raiz do projeto."""
    return caminho if os.path.isabs(caminho) else os.path.join(RAIZ, caminho)


@dataclass(frozen=True)
class Config:
    """Todas as configuracoes do sistema, tipadas e num so lugar."""

    # --- Flask / login ---
    secret_key: str = os.getenv("FLASK_SECRET_KEY", "troque-esta-chave")

    # --- Google Sheets ---
    google_credentials_file: str = _abs(
        os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials_google.json")
    )
    # Alternativa ao arquivo: o JSON da conta de servico inteiro numa variavel
    # de ambiente (usado na nuvem, onde o arquivo nao existe / nao vai no Git).
    google_credentials_json: str = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    sheet_credenciais_id: str = os.getenv("SHEET_CREDENCIAIS_ID", "")
    sheet_registros_id: str = os.getenv("SHEET_REGISTROS_ID", "")

    aba_senha: str = os.getenv("ABA_SENHA", os.getenv("ABA_USUARIOS", "senha"))
    aba_emails: str = os.getenv("ABA_EMAILS", "emails")
    aba_mapa: str = os.getenv("ABA_MAPA", "mapa_projeto")
    aba_portal: str = os.getenv("ABA_PORTAL", "cadastros")
    aba_fila: str = os.getenv("ABA_FILA", "fila")

    # Credenciais dos portais — ficam no .env (nao na planilha, nao no Git)
    usuario_crmligo: str = os.getenv("LIGO_USER", "")
    senha_crmligo: str = os.getenv("LIGO_PASSWORD", "")
    usuario_ayty: str = os.getenv("AYTY_USER", "")
    senha_ayty: str = os.getenv("AYTY_PASSWORD", "")

    # --- SMTP (notificacoes) ---
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    email_from: str = os.getenv("EMAIL_FROM", "") or os.getenv("SMTP_USER", "")

    # --- Portais (URLs) ---
    url_ligo: str = os.getenv(
        "URL_LIGO", "https://crm.digitalcontact.cloud/authentication"
    )
    url_ayty: str = os.getenv(
        "URL_AYTY",
        "https://app33.digitalcontact.cloud/Ayty/AppTECHBRASILCCPAAS/"
        "AytyPortalExFrontEndWeb/Views/Default.aspx",
    )

    # --- Dominio ---
    projetos: tuple = ("CPFL", "ENELSP", "NEOENERGIA", "BANCO", "RECEPTIVO BRASIL",
                       "ATIVO CHILE", "RECEPTIVO CHILE")
    niveis_acesso: tuple = ("Operador", "Supervisor", "Auditor")

    # Supervisor para o qual o AYTY realoca o usuario ao distratar
    ayty_supervisor_distrato: str = os.getenv("AYTY_SUPERVISOR_DISTRATO", "teste code7")

    # --- Execucao / ambiente ---
    # Chrome sem interface: obrigatorio na nuvem (container sem tela). Local fica
    # visivel por padrao, para voce acompanhar o robo.
    headless: bool = os.getenv("HEADLESS", "").strip().lower() in ("1", "true", "yes", "on")
    # No container usamos o Chromium do sistema; local deixa vazio e o Selenium
    # Manager resolve o Chrome/driver sozinho.
    chrome_binary: str = os.getenv("CHROME_BINARY", "")
    chromedriver_path: str = os.getenv("CHROMEDRIVER_PATH", "")
    # Debug do Flask: NUNCA ligar em producao (expoe o debugger no navegador).
    flask_debug: bool = os.getenv("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")

    # Escopos OAuth do Google
    scopes: tuple = (
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    )

    # Colunas da aba 'senha': acesso geral ao site e acesso a tela de distrato
    col_senha_formulario: str = "senha_formulario"
    col_senha_distrato: str = "senha_distrato"


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Devolve a instancia unica de configuracao (memorizada)."""
    return Config()
