import os
from pathlib import Path
from playwright.sync_api import Page, expect

BASE_URL = os.getenv("APP_URL", "http://127.0.0.1:8555")
ARTIFACTS = Path("artifacts/visual")


def test_revisoes_renderiza_estrutura_homologada(page: Page):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size({"width": 1536, "height": 1024})
    page.goto(BASE_URL, wait_until="networkidle", timeout=60000)

    # A navegação deve preservar a identidade e expor o módulo homologado.
    expect(page.get_by_text("Gestão de Pagamentos", exact=False).first).to_be_visible()
    page.get_by_text("Revisões dos Técnicos", exact=True).first.click()
    expect(page.get_by_text("Retornos, correções e aprovação individual por técnico", exact=False)).to_be_visible()

    # Controles funcionais que não podem desaparecer em alterações visuais.
    expect(page.get_by_text("Técnico", exact=True).first).to_be_visible()
    expect(page.get_by_text("Competência", exact=True).first).to_be_visible()
    expect(page.get_by_text("GERAR / BAIXAR PLANILHA DO TÉCNICO", exact=False)).to_be_visible()

    # Registra evidência visual da execução para inspeção no GitHub Actions.
    page.screenshot(path=str(ARTIFACTS / "revisoes_tecnicos.png"), full_page=True)


def test_sidebar_identidade_permanece(page: Page):
    page.set_viewport_size({"width": 1536, "height": 1024})
    page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
    expect(page.get_by_text("Visão Geral", exact=True)).to_be_visible()
    expect(page.get_by_text("Conferência", exact=True)).to_be_visible()
    expect(page.get_by_text("Por Técnico", exact=True)).to_be_visible()
    expect(page.get_by_text("Revisões dos Técnicos", exact=True)).to_be_visible()
    expect(page.get_by_text("Plantão", exact=True)).to_be_visible()
    expect(page.get_by_text("Histórico", exact=True)).to_be_visible()
    expect(page.get_by_text("Simulador", exact=True)).to_be_visible()
    expect(page.get_by_text("Exportações", exact=True)).to_be_visible()
    expect(page.get_by_text("Cadastros", exact=True)).to_be_visible()
    expect(page.get_by_text("Configurações", exact=True)).to_be_visible()
