# -*- coding: utf-8 -*-
"""Site de Cadastro / Distrato de operadores.

- Login validado contra a planilha de Credenciais (só senha).
- Cada solicitacao entra na aba 'fila' como 'pendente'; o robo local (robo.py)
  processa depois no portal e registra em 'cadastros'.
- Notificacao opcional por e-mail a cada solicitacao.

Reaproveita config.py, utils.py e planilhas.py (mesma base do robo).
"""

from __future__ import annotations

import hmac
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash
)

from config import get_config
from planilhas import (
    GoogleSheets, FilaRepository, CadastrosRepository, MapaProjetoRepository,
)
from utils import (
    limpar_cpf, cpf_valido, nome_invalido, data_nascimento_invalida,
)

cfg = get_config()
sheets = GoogleSheets(cfg)
fila_repo = FilaRepository(sheets)
cadastros_repo = CadastrosRepository(sheets)
mapa_repo = MapaProjetoRepository(sheets)

app = Flask(__name__)
app.secret_key = cfg.secret_key


# ---------------------------------------------------------------------------
# Credenciais e notificacoes (planilha de Credenciais)
# ---------------------------------------------------------------------------
def _checar_senha_coluna(coluna: str, senha: str) -> bool:
    """Confere a senha contra a coluna informada na aba 'senha'."""
    ws = sheets.aba(cfg.sheet_credenciais_id, cfg.aba_senha)
    registros = ws.get_all_records()
    if not registros:
        return False
    esperada = str(registros[0].get(coluna, "")).strip()
    return bool(esperada) and hmac.compare_digest(esperada, str(senha))


def checar_senha(senha: str) -> bool:
    """Senha de acesso geral ao site (coluna 'senha_formulario')."""
    return _checar_senha_coluna(cfg.col_senha_formulario, senha)


def checar_senha_distrato(senha: str) -> bool:
    """Senha da tela de distrato (coluna 'senha_distrato')."""
    return _checar_senha_coluna(cfg.col_senha_distrato, senha)


def listar_emails_notificacao() -> list[str]:
    ws = sheets.aba(cfg.sheet_credenciais_id, cfg.aba_emails)
    return [
        str(reg.get("email", "")).strip()
        for reg in ws.get_all_records()
        if str(reg.get("email", "")).strip()
    ]


def enviar_notificacao(assunto: str, corpo: str) -> None:
    """Envia e-mail aos destinatarios; falhas apenas sao logadas."""
    if not (cfg.smtp_user and cfg.smtp_password):
        app.logger.info("SMTP nao configurado; notificacao ignorada.")
        return
    try:
        destinatarios = listar_emails_notificacao()
    except Exception as e:
        app.logger.warning(f"Nao foi possivel ler a lista de e-mails: {e}")
        return
    if not destinatarios:
        return
    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = assunto
    msg["From"] = cfg.email_from
    msg["To"] = ", ".join(destinatarios)
    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as s:
            s.starttls()
            s.login(cfg.smtp_user, cfg.smtp_password)
            s.sendmail(cfg.email_from, destinatarios, msg.as_string())
    except Exception as e:
        app.logger.warning(f"Falha ao enviar notificacao: {e}")


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("autenticado"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def _agora() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            if checar_senha(request.form.get("senha", "")):
                session["autenticado"] = True
                return redirect(url_for("index"))
            flash("Senha invalida.", "erro")
        except Exception as e:
            app.logger.warning(f"Erro ao validar login: {e}")
            flash("Erro ao validar o login. Tente novamente.", "erro")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _opcoes_form():
    """Lista de projetos (da planilha) e niveis para renderizar o formulario."""
    try:
        projetos = mapa_repo.listar_projetos() or list(cfg.projetos)  # da planilha
        erro_projetos = None
    except Exception as e:
        app.logger.warning(f"Falha ao carregar projetos da planilha: {e}")
        projetos = list(cfg.projetos)
        erro_projetos = "Nao foi possivel carregar a lista de projetos agora."
    return projetos, list(cfg.niveis_acesso), erro_projetos


def _cpf_ja_ativo(cpf: str) -> bool:
    """True se o CPF ja tem cadastro ATIVO. Distratado (Ativo=Nao) libera novo."""
    achado = cadastros_repo.buscar_por_cpf(cpf)
    if not achado:
        return False
    ativo = str(achado["dados"].get(CadastrosRepository.C_ATIVO, "")).strip().lower()
    return ativo in ("sim", "ativo", "s", "true", "1")


@app.route("/")
@login_required
def index():
    projetos, niveis, erro_projetos = _opcoes_form()
    return render_template(
        "index.html", projetos=projetos, niveis=niveis, erro_projetos=erro_projetos,
    )


@app.route("/cadastro", methods=["POST"])
@login_required
def cadastro():
    nome = " ".join(request.form.get("nome", "").split())
    cpf_bruto = request.form.get("cpf", "")
    cpf = limpar_cpf(cpf_bruto)
    nasc = request.form.get("nascimento", "").strip()
    projetos = request.form.getlist("projetos")
    nivel = request.form.get("nivel_acesso", "").strip()

    # --- validacao campo a campo (mesma regra do cliente, aqui e a que vale) ---
    erros: dict[str, str] = {}

    motivo_nome = nome_invalido(nome)
    if motivo_nome:
        erros["nome"] = motivo_nome

    if not cpf:
        erros["cpf"] = "Informe o CPF."
    elif not cpf_valido(cpf):
        erros["cpf"] = "CPF invalido (verifique os numeros)."
    else:
        try:
            if _cpf_ja_ativo(cpf):
                erros["cpf"] = "Este CPF ja possui um cadastro ativo no sistema."
        except Exception as e:
            app.logger.warning(f"Falha ao consultar CPF em 'cadastros': {e}")

    motivo_data = data_nascimento_invalida(nasc)
    if motivo_data:
        erros["nascimento"] = motivo_data

    if not projetos:
        erros["projetos"] = "Selecione ao menos um projeto."

    if nivel not in cfg.niveis_acesso:
        erros["nivel_acesso"] = "Selecione o nivel de acesso."

    if erros:
        projetos_opts, niveis, erro_projetos = _opcoes_form()
        return render_template(
            "index.html",
            projetos=projetos_opts, niveis=niveis, erro_projetos=erro_projetos,
            erros=erros,
            valores={"nome": nome, "cpf": cpf_bruto, "nascimento": nasc,
                     "projetos": projetos, "nivel_acesso": nivel},
        ), 400

    # tudo valido -> enfileira
    nome = nome.upper()
    try:
        ws = sheets.aba(cfg.sheet_registros_id, cfg.aba_fila, FilaRepository.CABECALHO)
        agora = _agora()
        # coluna Superior fica vazia: o supervisor vem do mapa_projeto por portal
        ws.append_row([
            agora, "cadastro", nome, cpf, nasc,
            ", ".join(projetos), "", nivel, "pendente", "pendente", "",
        ], value_input_option="USER_ENTERED")
        flash(f"{nome} enviado(a) para a fila de cadastro!", "ok")
        enviar_notificacao(
            assunto=f"Nova solicitacao de cadastro: {nome}",
            corpo=(
                "Uma solicitacao de cadastro entrou na fila.\n\n"
                f"Nome: {nome}\nCPF: {cpf}\nNascimento: {nasc}\n"
                f"Projeto(s): {', '.join(projetos)}\n"
                f"Nivel de acesso: {nivel}\nData/hora: {agora}\n"
            ),
        )
    except Exception as e:
        app.logger.warning(f"Erro ao enviar para a fila: {e}")
        flash("Erro ao enviar para a fila. Tente novamente.", "erro")
    return redirect(url_for("index"))


@app.route("/distrato", methods=["POST"])
@login_required
def distrato():
    cpf = limpar_cpf(request.form.get("cpf_distrato", ""))
    senha_distrato = request.form.get("senha_distrato", "")
    try:
        senha_ok = checar_senha_distrato(senha_distrato)
    except Exception as e:
        app.logger.warning(f"Erro ao validar a senha de distrato: {e}")
        senha_ok = False
    if not senha_ok:
        flash("Senha de distrato invalida.", "erro")
    elif not cpf_valido(cpf):
        flash("CPF invalido (precisa de 11 digitos validos).", "erro")
    else:
        try:
            ws = sheets.aba(cfg.sheet_registros_id, cfg.aba_fila, FilaRepository.CABECALHO)
            agora = _agora()
            ws.append_row([
                agora, "distrato", "", cpf, "", "", "", "", "pendente", "pendente", "",
            ], value_input_option="USER_ENTERED")
            flash(f"Distrato do CPF {cpf} enviado para a fila!", "ok")
            enviar_notificacao(
                assunto=f"Nova solicitacao de distrato: CPF {cpf}",
                corpo=(
                    "Uma solicitacao de distrato entrou na fila.\n\n"
                    f"CPF: {cpf}\nData/hora: {agora}\n"
                ),
            )
        except Exception as e:
            app.logger.warning(f"Erro ao enviar para a fila: {e}")
            flash("Erro ao enviar para a fila. Tente novamente.", "erro")
    return redirect(url_for("index"))


if __name__ == "__main__":
    import os
    porta = int(os.getenv("PORT", "5000"))
    # debug SO quando FLASK_DEBUG estiver ligado (nunca em producao).
    # Em producao rode via gunicorn (que ignora este bloco).
    app.run(host="0.0.0.0", port=porta, debug=cfg.flask_debug)
