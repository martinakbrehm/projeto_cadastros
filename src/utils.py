# -*- coding: utf-8 -*-
"""Utilidades de dominio reutilizaveis: CPF, datas e geracao de login.

Sem dependencia de Flask, Selenium ou Google Sheets — funcoes puras e testaveis.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable, Optional

import pandas as pd

# Biblioteca consolidada de validacao de documentos BR (CPF/CNPJ). Se nao estiver
# instalada, caimos no algoritmo proprio (mesmo resultado) — ver cpf_valido().
try:
    from validate_docbr import CPF as _CPF
    _validador_cpf = _CPF()
except Exception:  # pragma: no cover - fallback quando a lib nao existe
    _validador_cpf = None


# ---------------------------------------------------------------------------
# CPF
# ---------------------------------------------------------------------------
def limpar_cpf(cpf_bruto) -> str:
    """Remove tudo que nao for digito."""
    return re.sub(r"\D", "", str(cpf_bruto))


def cpf_normalizado(cpf_bruto) -> str:
    """CPF apenas com digitos e com 11 posicoes (zeros a esquerda)."""
    return limpar_cpf(cpf_bruto).zfill(11)


def cpf_valido(cpf_bruto) -> bool:
    """Valida o digito verificador do CPF (usa validate-docbr quando disponivel)."""
    cpf = limpar_cpf(cpf_bruto)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    if _validador_cpf is not None:
        return bool(_validador_cpf.validate(cpf))
    for i in (9, 10):
        soma = sum(int(cpf[n]) * ((i + 1) - n) for n in range(i))
        digito = ((soma * 10) % 11) % 10
        if digito != int(cpf[i]):
            return False
    return True


# ---------------------------------------------------------------------------
# Validacoes de formulario (nome e data)
# ---------------------------------------------------------------------------
# Letras (com acento), espaco, apostrofo e hifen — o que se espera num nome.
_NOME_PERMITIDO = re.compile(r"^[A-Za-zÀ-ÿ '\-]+$")


def nome_invalido(nome) -> Optional[str]:
    """Retorna o motivo se o nome parecer invalido; None se estiver ok."""
    n = " ".join(str(nome).split())  # normaliza espacos
    if not n:
        return "Informe o nome completo."
    if any(c.isdigit() for c in n):
        return "O nome nao pode conter numeros."
    if not _NOME_PERMITIDO.match(n):
        return "O nome contem caracteres invalidos."
    partes = [p for p in n.split(" ") if p]
    if len(partes) < 2:
        return "Informe o nome completo (nome e sobrenome)."
    if any(len(p) < 2 for p in partes):
        return "Nome com partes muito curtas; revise."
    if re.search(r"(.)\1\1\1", n.lower()):
        return "Nome com repeticao suspeita; revise."
    return None


def data_nascimento_invalida(texto) -> Optional[str]:
    """Retorna o motivo se a data (DD/MM/AAAA) for invalida; None se estiver ok."""
    t = str(texto).strip()
    if not t:
        return "Informe a data de nascimento."
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", t)
    if not m:
        return "Data invalida. Use o formato DD/MM/AAAA."
    dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        nasc = date(ano, mes, dia)
    except ValueError:
        return "Data invalida."
    hoje = date.today()
    if nasc > hoje:
        return "Data de nascimento no futuro."
    idade = (hoje - nasc).days / 365.25
    if idade < 16 or idade > 100:
        return "Idade fora do intervalo esperado (16 a 100 anos)."
    return None


# ---------------------------------------------------------------------------
# Login do operador no portal
# ---------------------------------------------------------------------------
def gerar_login(
    cpf_bruto,
    ja_existe: Callable[[str], bool],
    tamanho_inicial: int = 4,
) -> str:
    """Gera o login do operador a partir do CPF (11 digitos, zeros a esquerda).

    Comeca com os `tamanho_inicial` primeiros digitos; enquanto `ja_existe`
    retornar True para o candidato, estende em um digito, sucessivamente.

    `ja_existe` e injetado para desacoplar a regra da fonte de verdade
    (portal, planilha, etc.), o que torna a funcao testavel isoladamente.
    """
    cpf = cpf_normalizado(cpf_bruto)
    for tamanho in range(tamanho_inicial, len(cpf) + 1):
        candidato = cpf[:tamanho]
        if not ja_existe(candidato):
            return candidato
    return cpf  # ultimo caso: o CPF inteiro


# ---------------------------------------------------------------------------
# Datas
# ---------------------------------------------------------------------------
def formatar_data(data_bruta) -> str:
    """Normaliza a data para o formato DD/MM/AAAA aceito pelos portais."""
    try:
        return pd.to_datetime(data_bruta).strftime("%d/%m/%Y")
    except Exception:
        texto = str(data_bruta).strip()
        if "-" in texto:
            partes = texto.split(" ")[0].split("-")
            if len(partes) == 3:
                return f"{partes[2]}/{partes[1]}/{partes[0]}"
        return texto
