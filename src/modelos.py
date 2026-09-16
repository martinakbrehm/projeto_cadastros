# -*- coding: utf-8 -*-
"""Modelos de dominio (dataclasses e enums) usados em todo o projeto."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TipoSolicitacao(str, Enum):
    CADASTRO = "cadastro"
    DISTRATO = "distrato"


class Status(str, Enum):
    PENDENTE = "pendente"
    PROCESSADO = "processado"
    ERRO = "erro"


@dataclass
class Solicitacao:
    """Uma linha da aba 'fila' a ser processada pelo robo."""

    linha: int  # numero da linha na planilha (1-based, inclui cabecalho)
    carimbo: str
    tipo: str
    nome: str
    cpf: str
    nascimento: str
    projeto: str
    superior: str
    nivel_acesso: str
    status: str

    @property
    def eh_cadastro(self) -> bool:
        return self.tipo.strip().lower() == TipoSolicitacao.CADASTRO.value

    @property
    def eh_distrato(self) -> bool:
        return self.tipo.strip().lower() == TipoSolicitacao.DISTRATO.value


@dataclass
class DadosCadastro:
    """Dados ja preparados para digitar no portal (matricula e login resolvidos)."""

    nome: str
    cpf: str            # 11 digitos
    nascimento: str     # DD/MM/AAAA
    projeto: str
    superior: str
    nivel_acesso: str
    matricula: int
    login: str          # login do operador no portal (derivado do CPF)
