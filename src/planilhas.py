# -*- coding: utf-8 -*-
"""Camada de acesso ao Google Sheets: cliente + repositorios.

- `GoogleSheets`        : autoriza e abre abas (cria com cabecalho se preciso).
- `FilaRepository`      : le solicitacoes pendentes e atualiza o status.
- `CadastrosRepository` : opera a aba de usuarios do portal (buscar, inserir,
                          reativar, inativar), respeitando a ordem das colunas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from config import Config, get_config
from modelos import Solicitacao, Status
from utils import cpf_normalizado


def _agora_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------
class GoogleSheets:
    """Fina camada sobre o gspread com autorizacao preguicosa (lazy)."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or get_config()
        self._cliente: Optional[gspread.Client] = None

    @property
    def cliente(self) -> gspread.Client:
        if self._cliente is None:
            scopes = list(self.cfg.scopes)
            if self.cfg.google_credentials_json.strip():
                # Nuvem: o JSON da conta de servico vem inteiro numa variavel.
                import json
                info = json.loads(self.cfg.google_credentials_json)
                creds = Credentials.from_service_account_info(info, scopes=scopes)
            else:
                # Local: arquivo credentials_google.json (fora do Git).
                creds = Credentials.from_service_account_file(
                    self.cfg.google_credentials_file, scopes=scopes
                )
            self._cliente = gspread.authorize(creds)
        return self._cliente

    def aba(self, sheet_id: str, nome: str, cabecalho: Optional[list] = None):
        """Abre (ou cria) a aba; garante o cabecalho se a aba estiver vazia."""
        planilha = self.cliente.open_by_key(sheet_id)
        try:
            ws = planilha.worksheet(nome)
        except gspread.WorksheetNotFound:
            ws = planilha.add_worksheet(
                title=nome, rows=1000, cols=max(len(cabecalho or []), 10)
            )
        if cabecalho:
            valores = ws.get_all_values()
            vazia = not any(str(c).strip() for linha in valores for c in linha)
            if vazia:
                ws.append_row(cabecalho, value_input_option="USER_ENTERED")
        return ws


# ---------------------------------------------------------------------------
# Repositorio da fila
# ---------------------------------------------------------------------------
class FilaRepository:
    """Solicitacoes pendentes na aba 'fila'."""

    CABECALHO = [
        "Carimbo", "Tipo", "Nome", "CPF", "Nascimento",
        "Projeto", "Superior", "Nível de Acesso",
        "Status Ligo", "Status AYTY", "Erro",
    ]
    # Cada portal tem sua propria coluna de status (1-based): o mesmo item fica
    # pendente no AYTY mesmo depois de processado no Ligo, e vice-versa.
    _COL_STATUS = {"ligo": 9, "ayty": 10}
    _COL_ERRO = 11  # detalhe da falha, por portal (limpo quando o portal da certo)

    def __init__(self, sheets: GoogleSheets):
        self.sheets = sheets
        self.cfg = sheets.cfg

    def _aba(self):
        return self.sheets.aba(
            self.cfg.sheet_registros_id, self.cfg.aba_fila, self.CABECALHO
        )

    def _coluna_status(self, portal: str) -> int:
        try:
            return self._COL_STATUS[portal]
        except KeyError:
            raise ValueError(f"Portal desconhecido para a fila: {portal!r}")

    def listar_pendentes(self, portal: str) -> list[Solicitacao]:
        """Solicitacoes ainda pendentes NESTE portal (le a coluna de status dele)."""
        col = self._coluna_status(portal)  # 1-based
        ws = self._aba()
        linhas = ws.get_all_values()
        pendentes: list[Solicitacao] = []
        for i, linha in enumerate(linhas[1:], start=2):  # pula cabecalho
            linha = (linha + [""] * len(self.CABECALHO))[: len(self.CABECALHO)]
            carimbo, tipo, nome, cpf, nasc, proj, sup, nivel, _st_l, _st_a = linha
            status = linha[col - 1]
            if status.strip().lower() != Status.PENDENTE.value:
                continue
            pendentes.append(Solicitacao(
                linha=i, carimbo=carimbo, tipo=tipo, nome=nome, cpf=cpf,
                nascimento=nasc, projeto=proj, superior=sup,
                nivel_acesso=nivel, status=status,
            ))
        return pendentes

    @staticmethod
    def _merge_erro(atual: str, portal: str, mensagem: Optional[str]) -> str:
        """Atualiza o segmento de erro DESTE portal, preservando o do outro.

        Formato da celula: '[ligo] msg | [ayty] msg'. Passar mensagem=None
        remove o segmento do portal (usado quando o portal processa com sucesso).
        """
        prefixo = f"[{portal}]"
        partes = [p for p in (atual or "").split(" | ")
                  if p.strip() and not p.startswith(prefixo)]
        if mensagem:
            partes.append(f"{prefixo} {' '.join(str(mensagem).split())}")
        return " | ".join(partes)

    def atualizar_status(self, linha: int, status: Status, portal: str,
                         erro: Optional[str] = None) -> None:
        """Grava o status do portal; registra o erro (ou limpa, se deu certo)."""
        ws = self._aba()
        ws.update_cell(linha, self._coluna_status(portal), status.value)
        atual = ws.cell(linha, self._COL_ERRO).value or ""
        mensagem = erro if status == Status.ERRO else None
        novo = self._merge_erro(atual, portal, mensagem)
        if novo != atual:
            ws.update_cell(linha, self._COL_ERRO, novo)


# ---------------------------------------------------------------------------
# Repositorio de cadastros (usuarios do portal)
# ---------------------------------------------------------------------------
class CadastrosRepository:
    """Aba 'cadastros' — espelho dos usuarios do portal.

    Colunas:
      Matrícula | Nome | Ativo | CPF | Superior | Nível de Acesso |
      Data de Criação | Data de Inativação | Retorno
    """

    C_MATRICULA = "Matrícula"
    C_NOME = "Nome"
    C_ATIVO = "Ativo"
    C_CPF = "CPF"
    C_SUPERIOR = "Superior"
    C_NIVEL = "Nível de Acesso"
    C_CRIACAO = "Data de Criação"
    C_INATIVACAO = "Data de Inativação"
    C_RETORNO = "Retorno"

    def __init__(self, sheets: GoogleSheets):
        self.sheets = sheets
        self.cfg = sheets.cfg

    def _aba(self):
        return self.sheets.aba(self.cfg.sheet_registros_id, self.cfg.aba_portal)

    def _indices(self, ws) -> dict[str, int]:
        """Mapeia nome da coluna -> indice 1-based, lendo o cabecalho ao vivo."""
        cabecalho = ws.row_values(1)
        return {nome.strip(): i for i, nome in enumerate(cabecalho, start=1)}

    def buscar_por_cpf(self, cpf) -> Optional[dict]:
        """Retorna {'linha': n, 'dados': {...}} do usuario, ou None."""
        ws = self._aba()
        alvo = cpf_normalizado(cpf)
        registros = ws.get_all_records()
        for i, reg in enumerate(registros, start=2):  # pula cabecalho
            if cpf_normalizado(reg.get(self.C_CPF, "")) == alvo:
                return {"linha": i, "dados": reg}
        return None

    def listar_superiores(self) -> list[str]:
        """Superiores distintos ja existentes, ordenados (lido ao vivo)."""
        ws = self._aba()
        nomes = set()
        for reg in ws.get_all_records():
            sup = str(reg.get(self.C_SUPERIOR, "")).strip()
            if sup:
                nomes.add(sup)
        return sorted(nomes)

    def cpfs_cadastrados(self) -> set[str]:
        """Conjunto de todos os CPFs (11 digitos) ja presentes no portal.

        Usado para calcular a unicidade do login: o espelho do portal e a
        propria aba 'cadastros', com todos os usuarios exportados.
        """
        ws = self._aba()
        cpfs = set()
        for reg in ws.get_all_records():
            bruto = str(reg.get(self.C_CPF, "")).strip()
            if bruto:
                cpfs.add(cpf_normalizado(bruto))
        return cpfs

    def proxima_matricula(self) -> int:
        ws = self._aba()
        idx = self._indices(ws)
        coluna = ws.col_values(idx[self.C_MATRICULA])[1:]  # sem cabecalho
        numeros = [int(v) for v in coluna if str(v).strip().isdigit()]
        return (max(numeros) + 1) if numeros else 1

    def inserir_novo(self, nome, cpf, superior, nivel, matricula: int) -> int:
        """Adiciona uma nova linha de usuario ativo. Retorna a matricula usada."""
        ws = self._aba()
        idx = self._indices(ws)
        linha = [""] * len(idx)
        valores = {
            self.C_MATRICULA: matricula,
            self.C_NOME: nome,
            self.C_ATIVO: "Sim",
            self.C_CPF: cpf_normalizado(cpf),
            self.C_SUPERIOR: superior,
            self.C_NIVEL: nivel,
            self.C_CRIACAO: _agora_iso(),
        }
        for coluna, valor in valores.items():
            if coluna in idx:
                linha[idx[coluna] - 1] = valor
        ws.append_row(linha, value_input_option="USER_ENTERED")
        return matricula

    def reativar(self, cpf) -> bool:
        """Retorno de operador: Ativo=Sim e preenche Retorno. Retorna se achou."""
        return self._atualizar_por_cpf(cpf, {
            self.C_ATIVO: "Sim",
            self.C_RETORNO: _agora_iso(),
            self.C_INATIVACAO: "",
        })

    def inativar(self, cpf) -> bool:
        """Distrato: Ativo=Não e preenche Data de Inativação. Retorna se achou."""
        return self._atualizar_por_cpf(cpf, {
            self.C_ATIVO: "Não",
            self.C_INATIVACAO: _agora_iso(),
        })

    def _atualizar_por_cpf(self, cpf, valores: dict) -> bool:
        ws = self._aba()
        achado = self.buscar_por_cpf(cpf)
        if not achado:
            return False
        idx = self._indices(ws)
        linha = achado["linha"]
        for coluna, valor in valores.items():
            if coluna in idx:
                ws.update_cell(linha, idx[coluna], valor)
        return True


# ---------------------------------------------------------------------------
# Mapa de projetos (aba 'mapa_projeto' da planilha de credenciais)
# ---------------------------------------------------------------------------
class MapaProjetoRepository:
    """Le a aba 'mapa_projeto': Projeto | Ligo | AYTY | Tipo | Supervisor Padrão.

    Resolve, para o projeto escolhido no formulario, o projeto correspondente em
    cada portal, o Tipo de Usuario (AYTY) e o supervisor padrao do cadastro novo.
    """

    def __init__(self, sheets: "GoogleSheets"):
        self.sheets = sheets
        self.cfg = sheets.cfg
        self._linhas = None

    def _carregar(self):
        if self._linhas is None:
            ws = self.sheets.aba(self.cfg.sheet_credenciais_id, self.cfg.aba_mapa)
            self._linhas = ws.get_all_records()
        return self._linhas

    def listar_projetos(self) -> list:
        """Nomes dos projetos (1a coluna) — usados como opcoes do formulario."""
        return [str(r.get("Projeto", "")).strip()
                for r in self._carregar() if str(r.get("Projeto", "")).strip()]

    def resolver(self, projeto_formulario) -> Optional[dict]:
        """Acha a linha do projeto (match por conter o nome; combos usam o 1o).

        Retorna {'ligo','ayty','tipo','supervisor_ligo','supervisor_ayty'} ou None.
        """
        alvo = (projeto_formulario or "").upper()
        for reg in self._carregar():
            nome = str(reg.get("Projeto", "")).strip().upper()
            if nome and nome in alvo:
                return {
                    "ligo": str(reg.get("Ligo", "")).strip(),
                    "ayty": str(reg.get("AYTY", "")).strip(),
                    "tipo": str(reg.get("Tipo", "Ativo")).strip() or "Ativo",
                    "supervisor_ligo": str(reg.get("Supervisor Ligo", "")).strip(),
                    "supervisor_ayty": str(reg.get("Supervisor AYTY", "")).strip(),
                }
        return None
