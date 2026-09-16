# -*- coding: utf-8 -*-
"""Robo local: processa a fila de solicitacoes no portal e registra em 'cadastros'.

Fluxo por solicitacao PENDENTE da aba 'fila':

  cadastro + CPF novo      -> cria no portal (Selenium) e insere linha em 'cadastros'
  cadastro + CPF ja existe -> RETORNO (reativa) — passos do portal ainda nao mapeados
  distrato                 -> inativa — passos do portal ainda nao mapeados

Uso:
  python robo.py --portal ligo            # processa no portal Ligo
  python robo.py --portal ayty            # processa no portal AYTY
  python robo.py --portal ligo --dry-run  # simula, sem abrir o navegador nem gravar
"""

from __future__ import annotations

import argparse
import sys

# Saida robusta: no Windows o console e cp1252 e quebra com emoji; na nuvem e
# UTF-8. Forcamos UTF-8 com fallback para nao derrubar o robo por causa de print.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from config import get_config
from modelos import DadosCadastro, Solicitacao, Status
from planilhas import (
    GoogleSheets, FilaRepository, CadastrosRepository, MapaProjetoRepository,
)
from portais import criar_portal, UsuarioJaExiste
from utils import cpf_normalizado, formatar_data, gerar_login


class Robo:
    def __init__(self, portal_nome: str, dry_run: bool = False):
        self.cfg = get_config()
        self.dry_run = dry_run
        self.portal_nome = portal_nome
        sheets = GoogleSheets(self.cfg)
        self.fila = FilaRepository(sheets)
        self.cadastros = CadastrosRepository(sheets)
        self.mapa = MapaProjetoRepository(sheets)
        self.portal = None
        self._navegador_aberto = False
        self._cadastro_preparado = False
        self._cadastros_no_portal = 0
        self.pendentes_manuais: list[str] = []  # retorno/distrato ainda nao automatizados
        self._cpfs_portal: set[str] = set()  # espelho dos CPFs do portal (unicidade do login)

    # -- infra --------------------------------------------------------------
    def _instancia_portal(self):
        """Cria (sem abrir o navegador) a instancia do portal escolhido."""
        if self.portal is None:
            self.portal = criar_portal(self.portal_nome, self.cfg)
        return self.portal

    def _garantir_navegador(self):
        """Abre o navegador uma unica vez (sem preparacao)."""
        portal = self._instancia_portal()
        if not self._navegador_aberto:
            portal.abrir()
            self._navegador_aberto = True
        return portal

    def _abrir_para_cadastro(self):
        """Navegador + preparacao do modal de cadastro (uma unica vez)."""
        portal = self._garantir_navegador()
        if not self._cadastro_preparado:
            portal.preparar()
            self._cadastro_preparado = True
        return portal

    def _login_para(self, cpf: str) -> str:
        """Login unico: menor prefixo do CPF que nao colide com outro usuario do portal."""
        def ja_existe(candidato: str) -> bool:
            return any(
                outro != cpf and outro.startswith(candidato)
                for outro in self._cpfs_portal
            )
        return gerar_login(cpf, ja_existe)

    # -- processamento ------------------------------------------------------
    def executar(self):
        pendentes = self.fila.listar_pendentes(self.portal_nome)
        print(f"📋 {len(pendentes)} solicitacao(oes) pendente(s) na fila.")
        if not pendentes:
            return

        # Espelho do portal (aba 'cadastros') para calcular a unicidade do login.
        self._cpfs_portal = self.cadastros.cpfs_cadastrados()
        print(f"👥 {len(self._cpfs_portal)} usuario(s) no portal (base da unicidade do login).")

        matricula_seq = self.cadastros.proxima_matricula()
        print(f"🔢 Proxima matricula disponivel: {matricula_seq}")

        for s in pendentes:
            try:
                if s.eh_cadastro:
                    matricula_seq = self._processar_cadastro(s, matricula_seq)
                elif s.eh_distrato:
                    self._processar_distrato(s)
                else:
                    print(f"⚠️ Tipo desconhecido em '{s.tipo}' (linha {s.linha}); ignorado.")
            except Exception as e:
                print(f"❌ Erro na linha {s.linha}: {e}")
                if not self.dry_run:
                    self.fila.atualizar_status(s.linha, Status.ERRO, self.portal_nome, erro=str(e))

        if self.portal:
            self.portal.finalizar()
        self._resumo()

    def _processar_cadastro(self, s: Solicitacao, matricula_seq: int) -> int:
        cpf = cpf_normalizado(s.cpf)
        existente = self.cadastros.buscar_por_cpf(cpf)

        if existente:  # RETORNO
            matricula = existente["dados"].get(CadastrosRepository.C_MATRICULA)
            print(f"🔁 RETORNO {s.nome or ''} | matricula {matricula} | CPF {cpf}")
            if self.dry_run:
                print(f"   [dry-run] buscaria matricula {matricula}, Ativo=Sim + Retorno (linha {existente['linha']})")
                return matricula_seq
            portal = self._instancia_portal()
            if not portal.gestao_calibrada:
                self._registrar_manual(f"RETORNO {s.nome} (CPF {cpf}) — gestao do portal nao calibrada")
                return matricula_seq
            nome_portal = existente["dados"].get(CadastrosRepository.C_NOME) or s.nome
            superior = self._supervisor_retorno(s.projeto)
            self._garantir_navegador()
            portal.preparar_gestao(cpf, nome_portal, matricula)
            portal.reativar(cpf, nome=nome_portal, matricula=matricula, superior=superior)
            self.cadastros.reativar(cpf)
            self.fila.atualizar_status(s.linha, Status.PROCESSADO, self.portal_nome)
            print("   ✅ reativado.")
            return matricula_seq

        # CADASTRO NOVO
        login = self._login_para(cpf)
        dados = DadosCadastro(
            nome=s.nome, cpf=cpf, nascimento=formatar_data(s.nascimento),
            projeto=s.projeto, superior=s.superior, nivel_acesso=s.nivel_acesso,
            matricula=matricula_seq, login=login,
        )
        print(f"🆕 NOVO {dados.nome} | matricula {dados.matricula} | login {dados.login} | {dados.projeto}")

        # o CPF passa a contar na unicidade dos proximos logins deste mesmo lote
        self._cpfs_portal.add(cpf)

        if self.dry_run:
            print("   [dry-run] cadastraria no portal e inseriria linha em 'cadastros'")
            return matricula_seq + 1

        portal = self._abrir_para_cadastro()
        if self._cadastros_no_portal > 0:
            portal.aguardar_proximo()
        try:
            portal.cadastrar(dados)
        except UsuarioJaExiste:
            # o portal ja tem esse CPF: e colaborador antigo, nao cadastro novo
            self._registrar_manual(
                f"{dados.nome} (CPF {cpf}) ja existe no portal — precisa de RETORNO, nao cadastro"
            )
            return matricula_seq  # nao consome a matricula
        self._cadastros_no_portal += 1

        self.cadastros.inserir_novo(
            dados.nome, cpf, dados.superior, dados.nivel_acesso, dados.matricula
        )
        self.fila.atualizar_status(s.linha, Status.PROCESSADO, self.portal_nome)
        print(f"   ✅ {dados.nome} cadastrado e registrado.")
        return matricula_seq + 1

    def _processar_distrato(self, s: Solicitacao):
        cpf = cpf_normalizado(s.cpf)
        existente = self.cadastros.buscar_por_cpf(cpf)
        if not existente:
            print(f"🚫 DISTRATO CPF {cpf} — usuario nao encontrado em 'cadastros'.")
            msg = f"DISTRATO CPF {cpf} — nao encontrado em 'cadastros'"
            self._registrar_manual(msg)
            if not self.dry_run:
                self.fila.atualizar_status(s.linha, Status.ERRO, self.portal_nome, erro=msg)
            return

        matricula = existente["dados"].get(CadastrosRepository.C_MATRICULA)
        print(f"🚫 DISTRATO | matricula {matricula} | CPF {cpf}")
        if self.dry_run:
            print(f"   [dry-run] buscaria matricula {matricula}, Ativo=Não + Data de Inativação (linha {existente['linha']})")
            return

        portal = self._instancia_portal()
        if not portal.gestao_calibrada:
            self._registrar_manual(f"DISTRATO CPF {cpf} — gestao do portal nao calibrada")
            return
        nome_portal = existente["dados"].get(CadastrosRepository.C_NOME)
        self._garantir_navegador()
        portal.preparar_gestao(cpf, nome_portal, matricula)
        portal.distratar(cpf, nome=nome_portal, matricula=matricula)
        self.cadastros.inativar(cpf)
        self.fila.atualizar_status(s.linha, Status.PROCESSADO, self.portal_nome)
        print("   ✅ inativado.")

    def _supervisor_retorno(self, projeto: str) -> str:
        """Supervisor do retorno vindo do mapa_projeto, conforme o portal.

        No AYTY o retorno troca o supervisor; no Ligo fica 'SUPERIOR NAO
        CADASTRADO'. Se o mapa nao resolver, devolve '' (portal mantem o atual).
        """
        primeiro = (projeto or "").split(",")[0].strip()
        try:
            r = self.mapa.resolver(primeiro)
        except Exception:
            r = None
        if not r:
            return ""
        chave = "supervisor_ayty" if self.portal_nome == "ayty" else "supervisor_ligo"
        return r.get(chave, "")

    def _registrar_manual(self, msg: str):
        print(f"⚠️ {msg}")
        self.pendentes_manuais.append(msg)

    def _resumo(self):
        print("\n" + "=" * 60)
        print("RESUMO")
        if self.pendentes_manuais:
            print(f"⚠️ {len(self.pendentes_manuais)} item(ns) precisam de passos ainda nao mapeados:")
            for m in self.pendentes_manuais:
                print(f"   - {m}")
        else:
            print("Tudo que era automatizavel foi processado.")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Robo de cadastro/distrato nos portais.")
    parser.add_argument("--portal", required=True, choices=["ligo", "ayty", "ambos"],
                        help="Portal onde processar a fila ('ambos' roda Ligo e depois AYTY).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simula sem abrir o navegador nem gravar nas planilhas.")
    args = parser.parse_args()

    portais = ["ligo", "ayty"] if args.portal == "ambos" else [args.portal]
    for nome in portais:
        print("\n" + "#" * 74)
        print(f"# PORTAL: {nome.upper()}")
        print("#" * 74)
        try:
            Robo(portal_nome=nome, dry_run=args.dry_run).executar()
        except Exception as e:
            # um portal com problema nao pode derrubar o outro
            print(f"❌ Falha geral no portal {nome}: {e}")


if __name__ == "__main__":
    main()
