# -*- coding: utf-8 -*-
"""Automacao dos portais (Selenium).

`PortalBase` concentra o que e comum (abrir o Chrome, pausa para login manual,
helpers de teclado). `PortalLigo` e `PortalAyty` guardam apenas a coreografia
especifica de cada portal, com os passos calibrados por projeto isolados em
tabelas (NAVEGACAO_*), longe da logica.

Observacao: o Selenium e importado de forma preguicosa (lazy) para que este
modulo — e o modo dry-run do robo — possa ser importado sem um navegador.
"""

from __future__ import annotations

import time
from typing import Optional

from config import Config, get_config
from modelos import DadosCadastro


class UsuarioJaExiste(Exception):
    """O portal recusou o cadastro porque o CPF ja existe (colaborador antigo)."""
    def __init__(self, cpf):
        super().__init__(f"CPF {cpf} ja cadastrado no portal (retorno).")
        self.cpf = cpf


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class PortalBase:
    nome = "base"
    url = ""
    instrucoes = ""

    # Calibracao (mesmo estilo dos scripts de cadastro): quantos TABs do PRIMEIRO
    # campo do formulario do usuario ate a flag Ativo. O distrato/retorno seguem o
    # mesmo modelo do cadastro — voce abre o usuario e o robo faz o teclado.
    TABS_ATE_FLAG_ATIVO: Optional[int] = None

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or get_config()
        self.driver = None

    def _resolver_projeto(self, projeto):
        """Resolve o projeto do formulario no mapa da planilha 'mapa_projeto'.

        Retorna {'ligo','ayty','tipo','supervisor'} ou None (aí usa-se o fallback).
        """
        try:
            if not hasattr(self, "_mapa_cache"):
                from planilhas import GoogleSheets, MapaProjetoRepository
                self._mapa_cache = MapaProjetoRepository(GoogleSheets(self.cfg))
            return self._mapa_cache.resolver(projeto)
        except Exception:
            return None

    @property
    def gestao_calibrada(self) -> bool:
        """True quando a navegacao ate a flag Ativo esta calibrada."""
        return self.TABS_ATE_FLAG_ATIVO is not None

    # -- ciclo de vida ------------------------------------------------------
    def abrir(self):
        """Sobe o Chrome e navega ate o portal."""
        from selenium import webdriver

        opcoes = webdriver.ChromeOptions()
        if self.cfg.headless:
            # Nuvem / container sem tela: roda oculto e estavel.
            opcoes.add_argument("--headless=new")
            opcoes.add_argument("--no-sandbox")
            opcoes.add_argument("--disable-dev-shm-usage")
            opcoes.add_argument("--disable-gpu")
            opcoes.add_argument("--window-size=1500,950")
        else:
            # Local: janela visivel para acompanhar o robo.
            opcoes.add_argument("--start-maximized")
            opcoes.add_experimental_option("detach", True)
        if self.cfg.chrome_binary:
            opcoes.binary_location = self.cfg.chrome_binary
        # No container apontamos o chromedriver do sistema; local o Selenium
        # Manager (4.6+) baixa/casa o driver automaticamente.
        if self.cfg.chromedriver_path:
            from selenium.webdriver.chrome.service import Service
            self.driver = webdriver.Chrome(
                service=Service(self.cfg.chromedriver_path), options=opcoes
            )
        else:
            self.driver = webdriver.Chrome(options=opcoes)
        self.driver.get(self.url)
        return self

    def preparar(self):
        """Mostra as instrucoes e espera o operador deixar o modal pronto."""
        print("\n" + "=" * 74)
        print(self.instrucoes.strip())
        print("=" * 74)
        input("\n🟢 Modal de cadastro pronto na tela? Aperte [ENTER] no terminal...")

    def aguardar_proximo(self) -> None:
        """Entre cadastros: pede para abrir o proximo modal/linha em branco."""
        input("\n🟢 Abra o proximo cadastro em branco e deixe pronto. [ENTER] para continuar...")

    def finalizar(self):
        print("\n🔒 Processo finalizado. Navegador mantido aberto para conferencia.")

    # -- operacoes (implementadas nas subclasses) ---------------------------
    def cadastrar(self, dados: DadosCadastro) -> None:
        raise NotImplementedError

    def preparar_gestao(self, cpf=None, nome=None, matricula=None) -> None:
        """Pede para abrir o usuario existente (modelo manual — fallback)."""
        print("\n" + "=" * 74)
        print(f"GESTAO — abra o usuario (matricula {matricula} / {nome}) para EDICAO")
        print("e clique no PRIMEIRO campo do formulario (cursor piscando).")
        print("=" * 74)
        input("🟢 [ENTER] quando o formulario do usuario estiver aberto...")

    def distratar(self, cpf, nome=None, matricula=None, superior: Optional[str] = None) -> None:
        """Distrato: desliga a flag Ativo (+ hook) no formulario ja aberto."""
        self._alternar_flag_ativo()          # precondicao: usuario estava ativo
        self._apos_flag_distrato(superior)
        self._salvar_gestao()

    def reativar(self, cpf, nome=None, matricula=None, superior: Optional[str] = None) -> None:
        """Retorno: liga a flag Ativo (+ hook) no formulario ja aberto."""
        self._alternar_flag_ativo()          # precondicao: usuario estava inativo
        self._apos_flag_retorno(superior)
        self._salvar_gestao()

    def _alternar_flag_ativo(self) -> None:
        from selenium.webdriver.common.keys import Keys

        if self.TABS_ATE_FLAG_ATIVO is None:
            raise NotImplementedError(
                f"{self.nome}: calibrar TABS_ATE_FLAG_ATIVO (1o campo -> flag Ativo)."
            )
        self._tabs(self.TABS_ATE_FLAG_ATIVO, 0.12)
        self._ativo().send_keys(Keys.SPACE)  # alterna o checkbox
        time.sleep(0.4)

    # Hooks pos-flag — Ligo nao faz nada; AYTY ajusta o supervisor.
    def _apos_flag_distrato(self, superior: Optional[str]) -> None:
        pass

    def _apos_flag_retorno(self, superior: Optional[str]) -> None:
        pass

    def _salvar_gestao(self) -> None:
        raise NotImplementedError

    # -- helpers de teclado -------------------------------------------------
    def _ativo(self):
        return self.driver.switch_to.active_element

    def _tabs(self, quantidade: int, intervalo: float = 0.1):
        from selenium.webdriver.common.keys import Keys
        for _ in range(quantidade):
            self._ativo().send_keys(Keys.TAB)
            time.sleep(intervalo)

    def _enter(self, espera: float = 0.0):
        from selenium.webdriver.common.keys import Keys
        self._ativo().send_keys(Keys.ENTER)
        if espera:
            time.sleep(espera)


# ---------------------------------------------------------------------------
# Ligo
# ---------------------------------------------------------------------------
class PortalLigo(PortalBase):
    nome = "ligo"
    # Mapa projeto do formulario -> projeto no combo do Ligo
    MAPA_PROJETO = {
        "RECEPTIVO BRASIL": "ASSISTY - CPFL",  # vai pro projeto do CPFL (antes da regra generica)
        "CHILE": "ASSISTY - CL",               # ATIVO CHILE / RECEPTIVO CHILE -> ASSISTY - CL
        "RECEPTIVO": "ASSISTY - CL",
        "CPFL": "ASSISTY - CPFL",
        "ENELSP": "ASSISTY - ENEL",
        "NEOENERGIA": "ASSISTY - NEO ENERGIA",
        "BANCO": "ASSISTY - BANKS",
    }
    PROJETO_PADRAO = "ASSISTY - CL"

    # Gestao (distrato/retorno) — Ligo e SO a flag Ativo. A calibrar.
    TABS_ATE_FLAG_ATIVO = None

    def __init__(self, cfg: Optional[Config] = None):
        super().__init__(cfg)
        self.url = self.cfg.url_ligo

    # -- helpers de UI ------------------------------------------------------
    def _clicar(self, el):
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.15)
        try:
            el.click()  # clique nativo (React registra)
        except Exception:
            self.driver.execute_script("arguments[0].click();", el)

    def _digitar(self, el, texto):
        from selenium.webdriver.common.keys import Keys
        self.driver.execute_script("arguments[0].focus();", el)
        el.send_keys(Keys.CONTROL + "a")
        el.send_keys(Keys.DELETE)
        try:
            el.send_keys(texto)
        except Exception:
            self.driver.switch_to.active_element.send_keys(texto)

    def _por_name(self, campo):
        from selenium.webdriver.common.by import By
        return self.driver.find_element(By.CSS_SELECTOR, f"input[name='{campo}']")

    def _escolher_opcao(self, valor):
        from selenium.webdriver.common.by import By
        time.sleep(1.0)
        for p in self.driver.find_elements(By.XPATH, f"//p[@title={valor!r}]"):
            if p.is_displayed():
                self._clicar(p); time.sleep(0.6); return True
        return False

    def _combos_vazios(self):
        from selenium.webdriver.common.by import By
        return [c for c in self.driver.find_elements(By.CSS_SELECTOR, "input[placeholder='Selecionar']")
                if c.is_displayed() and not c.get_attribute("value")]

    # -- login e navegacao (100% automatico) --------------------------------
    def _credenciais(self):
        usuario = str(self.cfg.usuario_crmligo)
        senha = str(self.cfg.senha_crmligo)
        if usuario.isdigit() and len(usuario) < 4:
            usuario = usuario.zfill(4)
        return usuario, senha

    def preparar(self):
        """Login + selecionar LIGO CORE + ir para Usuarios — sem intervencao manual."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        if getattr(self, "_ja_preparado", False):
            return
        d = self.driver
        usuario, senha = self._credenciais()
        print(f"   🔐 Logando no Ligo como {usuario}...")
        WebDriverWait(d, 25).until(EC.presence_of_element_located((By.NAME, "login")))
        self._digitar(d.find_element(By.CSS_SELECTOR, "input[name='login']"), usuario)
        self._digitar(d.find_element(By.CSS_SELECTOR, "input[name='password']"), senha)
        d.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(11)
        print("   🗂️ Selecionando LIGO CORE...")
        self._clicar(d.find_element(By.XPATH, "//button[normalize-space()='LIGO CORE'] | //*[@title='LIGO CORE']"))
        time.sleep(1.5)
        d.find_element(By.XPATH, "//button[@type='submit' and normalize-space()='Selecionar']").click()
        time.sleep(7)
        print("   📁 Cadastros -> Usuarios...")
        for xp in ("//*[normalize-space(text())='Cadastros']", "//*[@title='Cadastros']"):
            try:
                self._clicar(d.find_element(By.XPATH, xp)); time.sleep(2); break
            except Exception:
                continue
        self._clicar(d.find_element(By.XPATH, "//*[normalize-space(text())='Usuários' or @title='Usuários']"))
        time.sleep(5)
        self._ja_preparado = True

    def aguardar_proximo(self):
        # cadastrar abre o proprio modal; nada a fazer entre cadastros
        return

    def _mapear_projeto(self, projeto):
        r = self._resolver_projeto(projeto)     # 1o: mapa da planilha
        if r and r["ligo"]:
            return r["ligo"]
        p = (projeto or "").upper()             # fallback: mapa embutido
        for chave, valor in self.MAPA_PROJETO.items():
            if chave in p:
                return valor
        return self.PROJETO_PADRAO

    def _supervisor_do_cadastro(self, projeto, superior_form):
        """Supervisor do cadastro novo no Ligo (coluna 'Supervisor Ligo' do mapa)."""
        r = self._resolver_projeto(projeto)
        if r and r["supervisor_ligo"]:
            return r["supervisor_ligo"]
        return superior_form

    def _salvar_gestao(self) -> None:
        from selenium.webdriver.common.by import By
        for rotulo in ("Salvar", "Adicionar"):
            try:
                self.driver.find_element(By.XPATH, f"//button[normalize-space()='{rotulo}']").click()
                time.sleep(3); return
            except Exception:
                continue

    # -- cadastro (full auto; unicidade de login verificada no portal) ------
    def cadastrar(self, dados: DadosCadastro) -> None:
        from selenium.webdriver.common.by import By

        d = self.driver
        projeto_ligo = self._mapear_projeto(dados.projeto)
        print(f"   ➕ Adicionar usuario: {dados.nome} / {projeto_ligo}")
        self._clicar(d.find_element(By.XPATH, "//button[contains(normalize-space(),'Adicionar')]"))
        time.sleep(3)

        self._digitar(self._por_name("name"), dados.nome)
        self._digitar(self._por_name("phoneLogin"), dados.cpf)
        self._digitar(self._por_name("registrationNumber"), dados.cpf)
        try:
            self._digitar(self._por_name("birth"), (dados.nascimento or "").replace("/", ""))
        except Exception:
            pass

        # combos na ordem: Projeto, Supervisor, Nivel (sempre o proximo vazio)
        print("   📦 Projeto...")
        self._clicar(self._combos_vazios()[0]); time.sleep(0.8)
        self._escolher_opcao(projeto_ligo); time.sleep(1.2)
        print("   📦 Supervisor...")
        supervisor = self._supervisor_do_cadastro(dados.projeto, dados.superior)
        self._clicar(self._combos_vazios()[0]); time.sleep(1.0)
        if not self._escolher_opcao(supervisor):
            self._escolher_primeiro_supervisor()
        time.sleep(1.2)
        print("   📦 Nivel...")
        if self._combos_vazios():
            self._clicar(self._combos_vazios()[0]); time.sleep(0.8)
            self._escolher_opcao(dados.nivel_acesso or "Operador")
        time.sleep(0.8)

        dados.login = self._salvar_com_login_unico(dados.cpf)
        print(f"   ✅ {dados.nome} cadastrado (login {dados.login}).")

    def _escolher_primeiro_supervisor(self):
        from selenium.webdriver.common.by import By
        projetos = set(self.MAPA_PROJETO.values()) | {"LIGO CORE"}
        for p in self.driver.find_elements(By.XPATH, "//p[@title]"):
            t = p.get_attribute("title")
            if p.is_displayed() and t and t not in projetos and t != "Sem opções":
                self._clicar(p); return True
        return False

    def _salvar_com_login_unico(self, cpf):
        """Clica Adicionar; se o portal reclamar do Login, estende +1 digito.
        Se reclamar do CPF, e colaborador antigo -> levanta UsuarioJaExiste."""
        import re as _re
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        d = self.driver
        for tam in range(4, len(cpf) + 1):
            login = cpf[:tam]
            campo = self._por_name("accessLogin")
            campo.click(); campo.send_keys(Keys.CONTROL + "a"); campo.send_keys(Keys.DELETE)
            time.sleep(0.15)
            self._digitar(campo, login); time.sleep(0.3)
            self._clicar(d.find_element(By.XPATH, "//button[normalize-space()='Adicionar' and not(contains(.,'usu'))]"))
            time.sleep(1.3)
            src = d.page_source
            conflito_login = bool(_re.search(r'existe.{0,30}Login', src, _re.I))
            conflito_cpf = bool(_re.search(r'existe.{0,30}CPF', src, _re.I))
            time.sleep(2.5)
            aberto = any(b.is_displayed() for b in d.find_elements(By.XPATH, "//button[normalize-space()='Adicionar']"))
            if not aberto:
                return login
            if conflito_cpf:
                raise UsuarioJaExiste(cpf)
            if conflito_login:
                continue
            raise RuntimeError(f"Cadastro nao salvou (login {login}) — verifique o formulario.")
        raise RuntimeError("Nao foi possivel gerar um login unico.")

    # -- distrato / retorno (full auto por seletores) -----------------------
    @property
    def gestao_calibrada(self) -> bool:
        return True  # implementado por seletores (nao depende de TABs)

    def preparar_gestao(self, cpf=None, nome=None, matricula=None) -> None:
        self.preparar()  # login + navegacao (guardado contra repeticao)

    def distratar(self, cpf, nome=None, matricula=None, superior: Optional[str] = None) -> None:
        self._abrir_edicao(cpf, nome, procurar_ativo=True)  # usuario esta ATIVO
        self._toggle_ativar()   # -> fica inativo
        self._salvar_edicao()

    def reativar(self, cpf, nome=None, matricula=None, superior: Optional[str] = None) -> None:
        self._abrir_edicao(cpf, nome, procurar_ativo=False)  # usuario esta INATIVO
        self._toggle_ativar()   # -> fica ativo
        self._salvar_edicao()

    def _selecionar_status_filtro(self, valor):
        """Ajusta o filtro de status (Ativo/Inativo) — 5o combo da barra de filtros
        (Nome, Login, Projetos, Supervisor, Status)."""
        from selenium.webdriver.common.by import By
        inputs = [i for i in self.driver.find_elements(By.CSS_SELECTOR, "input") if i.is_displayed()]
        if len(inputs) >= 5:
            self._clicar(inputs[4]); time.sleep(1)
            self._escolher_opcao(valor); time.sleep(0.4)
            # fecha o dropdown clicando no titulo
            try:
                self._clicar(self.driver.find_element(By.XPATH, "//*[normalize-space(text())='Usuários']"))
                time.sleep(0.3)
            except Exception:
                pass

    def _abrir_edicao(self, cpf, nome, procurar_ativo=True):
        """Filtra o usuario (nome + todos os projetos + status), acha pela linha
        do CPF e abre o lapis de edicao."""
        from selenium.webdriver.common.by import By
        d = self.driver
        try:
            self._clicar(d.find_element(By.XPATH, "//button[normalize-space()='Limpar']"))
            time.sleep(1)
        except Exception:
            pass
        if nome:
            self._digitar(d.find_element(By.CSS_SELECTOR, "input[placeholder='Nome']"), nome)
            time.sleep(0.3)
        # marca todos os projetos no filtro (a lista e por projeto)
        try:
            self._clicar(d.find_element(By.CSS_SELECTOR, "input[placeholder='Projetos']"))
            time.sleep(1)
            self._escolher_opcao("Selecionar todas as opções")
            time.sleep(0.4)
            self._clicar(d.find_element(By.XPATH, "//*[normalize-space(text())='Usuários']"))
            time.sleep(0.3)
        except Exception:
            pass
        # status: distrato procura Ativo; retorno procura Inativo
        self._selecionar_status_filtro("Ativo" if procurar_ativo else "Inativo")
        self._clicar(d.find_element(By.XPATH, "//button[normalize-space()='Filtrar']"))
        time.sleep(4)
        linhas = d.find_elements(By.XPATH, f"//tr[.//*[contains(normalize-space(),{cpf!r})]]")
        if not linhas:
            raise RuntimeError(f"Usuario CPF {cpf} nao encontrado no Ligo.")
        botoes = linhas[0].find_elements(By.TAG_NAME, "button")
        self._clicar(botoes[-1])  # ultimo icone = editar (lapis)
        time.sleep(3)

    def _toggle_ativar(self):
        from selenium.webdriver.common.by import By
        toggle = self.driver.find_element(
            By.XPATH, "//label[.//p[normalize-space()='Ativar']]//button")
        self._clicar(toggle)
        time.sleep(0.6)

    def _salvar_edicao(self):
        from selenium.webdriver.common.by import By
        self._clicar(self.driver.find_element(By.XPATH, "//button[normalize-space()='Salvar']"))
        time.sleep(3)


# ---------------------------------------------------------------------------
# AYTY
# ---------------------------------------------------------------------------
class PortalAyty(PortalBase):
    """AYTY (ASP.NET, iframe frmMain) — cadastro 100% automatico por seletores."""

    nome = "ayty"

    # projeto do formulario -> projeto no combo do AYTY
    MAPA_PROJETO = {
        "RECEPTIVO BRASIL": "ASSISTY - CPFL CRM CLOUD",  # vai pro projeto do CPFL (antes da generica)
        "CHILE": "CELESC CRM CLOUD",           # Chile (ativo ou receptivo) -> CELESC CRM CLOUD
        "RECEPTIVO": "CELESC CRM CLOUD",       # RECEPTIVO CHILE -> CELESC CRM CLOUD
        "CPFL": "ASSISTY - CPFL CRM CLOUD",
        "NEOENERGIA": "ASSISTY - NEO ENERGIA",
        "ENELSP": "ENEL",
        "BANCO": "ASSISTY - BANKS",
    }
    PROJETO_PADRAO = "AYTY CORE"

    # distrato/retorno do AYTY ainda nao testado -> robo pula com aviso
    _GESTAO_PRONTA = True

    def __init__(self, cfg: Optional[Config] = None):
        super().__init__(cfg)
        self.url = self.cfg.url_ayty

    @property
    def gestao_calibrada(self) -> bool:
        return self._GESTAO_PRONTA

    # -- credenciais / helpers ---------------------------------------------
    def _credenciais(self):
        usuario = str(self.cfg.usuario_ayty)
        senha = str(self.cfg.senha_ayty)
        if usuario.isdigit() and len(usuario) < 4:
            usuario = usuario.zfill(4)
        return usuario, senha

    def _frame(self):
        self.driver.switch_to.default_content()
        self.driver.switch_to.frame("frmMain")

    def _txt(self, id_, valor):
        from selenium.webdriver.common.by import By
        e = self.driver.find_element(By.ID, id_)
        e.clear()
        e.send_keys(str(valor))
        time.sleep(0.2)

    def _ddl(self, id_, valor):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import Select
        Select(self.driver.find_element(By.ID, id_)).select_by_visible_text(valor)
        time.sleep(0.3)

    def _mapear_projeto(self, projeto):
        r = self._resolver_projeto(projeto)     # 1o: mapa da planilha
        if r and r["ayty"]:
            return r["ayty"]
        p = (projeto or "").upper()             # fallback: mapa embutido
        for chave, valor in self.MAPA_PROJETO.items():
            if chave in p:
                return valor
        return self.PROJETO_PADRAO

    def _tipo_usuario(self, projeto):
        r = self._resolver_projeto(projeto)
        if r and r["tipo"]:
            return r["tipo"]
        return "Receptivo" if "RECEPTIVO" in (projeto or "").upper() else "Ativo"

    def _supervisor_do_cadastro(self, projeto, superior_form):
        """Supervisor do cadastro novo no AYTY (coluna 'Supervisor AYTY' do mapa)."""
        r = self._resolver_projeto(projeto)
        if r and r["supervisor_ayty"]:
            return r["supervisor_ayty"]
        return superior_form

    # -- login + navegacao (automatico) ------------------------------------
    def preparar(self):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        if getattr(self, "_ja_preparado", False):
            return
        d = self.driver
        usuario, senha = self._credenciais()
        print(f"   🔐 Logando no AYTY como {usuario}...")
        WebDriverWait(d, 25).until(EC.presence_of_element_located((By.ID, "txtDeLogin")))
        d.find_element(By.ID, "txtDeLogin").send_keys(usuario)
        d.find_element(By.ID, "txtDePassword").send_keys(senha)
        d.find_element(By.ID, "btnOk").click()
        time.sleep(12)
        print("   📁 Abrindo Usuarios...")
        self._frame()
        d.find_element(By.XPATH, "//a[normalize-space()='Usuários']").click()
        time.sleep(8)
        self._frame()
        WebDriverWait(d, 20).until(EC.presence_of_element_located((By.ID, "btnInsertTop")))
        self._ja_preparado = True

    def aguardar_proximo(self):
        return

    # -- cadastro (por ID; testado) ----------------------------------------
    def cadastrar(self, dados: DadosCadastro) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        d = self.driver
        projeto = self._mapear_projeto(dados.projeto)
        print(f"   ➕ Novo usuario AYTY: {dados.nome} / {projeto}")
        self._frame()
        d.execute_script("arguments[0].click();", d.find_element(By.ID, "btnInsertTop"))
        time.sleep(8)
        self._frame()
        WebDriverWait(d, 20).until(
            EC.presence_of_element_located((By.ID, "grdEditorList_editnew_2_txt")))

        self._txt("grdEditorList_editnew_2_txt", dados.nome)              # Nome
        self._txt("grdEditorList_editnew_3_txt", dados.nome)             # Apelido
        self._txt("grdEditorList_editnew_5_dt_I", dados.nascimento)      # Data nasc
        self._txt("grdEditorList_editnew_6_txt", dados.cpf)             # CPF
        self._txt("grdEditorList_editnew_7_txt", str(dados.matricula))  # Matricula
        self._txt("grdEditorList_editnew_8_txt", dados.login)          # Login Sistema
        tipo = self._tipo_usuario(dados.projeto)
        self._ddl("grdEditorList_editnew_11_ddl", "Intermediário")     # Turno
        self._ddl("grdEditorList_editnew_12_ddl", tipo)              # Tipo de usuario
        self._ddl("grdEditorList_editnew_13_ddl", projeto)            # Projeto
        self._selecionar_superior(self._supervisor_do_cadastro(dados.projeto, dados.superior))
        self._ddl("grdEditorList_editnew_15_ddl", dados.nivel_acesso or "Operador")  # Nivel
        self._txt("grdEditorList_editnew_20_txt", "00000000")        # CEP (8 digitos!)
        try:                                                          # Monitoravel
            chk = d.find_element(By.ID, "grdEditorList_editnew_22_chk")
            if not chk.is_selected():
                chk.click()
        except Exception:
            pass

        # salvar: link 'Salvar' da linha
        links = [a for a in d.find_elements(By.XPATH, "//a[normalize-space()='Salvar']")
                 if a.is_displayed()]
        if links:
            links[0].click()
        time.sleep(6)
        self._frame()
        if d.find_elements(By.ID, "grdEditorList_editnew_6_txt"):
            raise RuntimeError(
                f"AYTY: cadastro de {dados.nome} nao salvou (verifique campos/regras).")
        print(f"   ✅ {dados.nome} cadastrado no AYTY.")

    def _selecionar_superior(self, nome):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import Select
        sel = Select(self.driver.find_element(By.ID, "grdEditorList_editnew_14_ddl"))
        if nome:
            try:
                sel.select_by_visible_text(nome)
                time.sleep(0.3)
                return
            except Exception:
                pass
        for o in sel.options:  # fallback: primeira opcao valida
            if o.text.strip() and o.get_attribute("value") not in ("", "-1", "0"):
                sel.select_by_visible_text(o.text.strip())
                time.sleep(0.3)
                return

    # -- distrato / retorno (por seletores; linha filtrada e editavel) ------
    def preparar_gestao(self, cpf=None, nome=None, matricula=None):
        self.preparar()

    def distratar(self, cpf, nome=None, matricula=None, superior=None):
        self._filtrar_por_matricula(matricula)
        self._set_ativo(False)  # desmarca -> inativo
        self._set_superior_gestao(self.cfg.ayty_supervisor_distrato)  # "teste code7"
        self._salvar_edicao()

    def reativar(self, cpf, nome=None, matricula=None, superior=None):
        self._filtrar_por_matricula(matricula)
        self._set_ativo(True)   # marca -> ativo
        if superior:
            self._set_superior_gestao(superior)  # volta ao superior do formulario
        self._salvar_edicao()

    def _filtrar_por_matricula(self, matricula):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        d = self.driver
        self._frame()
        campo = d.find_element(By.ID, "ctl12_textBox")
        campo.clear()
        campo.send_keys(str(matricula))
        time.sleep(0.3)
        d.execute_script("arguments[0].click();", d.find_element(By.ID, "btnQueryTop"))
        time.sleep(6)
        self._frame()
        if not d.find_elements(By.ID, "grdEditorList_cell0_4_chk"):
            raise RuntimeError(f"AYTY: usuario matricula {matricula} nao encontrado.")

    def _set_ativo(self, ativo):
        from selenium.webdriver.common.by import By
        chk = self.driver.find_element(By.ID, "grdEditorList_cell0_4_chk")
        if chk.is_selected() != ativo:
            chk.click()
        time.sleep(0.3)

    def _set_superior_gestao(self, nome):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import Select
        try:
            Select(self.driver.find_element(By.ID, "grdEditorList_cell0_14_ddl")).select_by_visible_text(nome)
            time.sleep(0.3)
        except Exception:
            print(f"   ⚠️ Superior '{nome}' nao encontrado no AYTY; mantido o atual.")

    def _salvar_edicao(self):
        from selenium.webdriver.common.by import By
        d = self.driver
        links = [a for a in d.find_elements(By.XPATH, "//a[normalize-space()='Salvar']") if a.is_displayed()]
        if links:
            links[0].click()
        time.sleep(6)
        self._frame()
        corpo = d.find_element(By.TAG_NAME, "body").text.lower()
        if "não realizada" in corpo or "nao realizada" in corpo:
            raise RuntimeError("AYTY: gestao nao salvou (Operacao nao realizada).")


PORTAIS = {
    PortalLigo.nome: PortalLigo,
    PortalAyty.nome: PortalAyty,
}


def criar_portal(nome: str, cfg: Optional[Config] = None) -> PortalBase:
    nome = nome.strip().lower()
    if nome not in PORTAIS:
        raise ValueError(
            f"Portal '{nome}' desconhecido. Opcoes: {', '.join(PORTAIS)}"
        )
    return PORTAIS[nome](cfg)
