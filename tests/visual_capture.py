from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path('artifacts')
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1536, "height": 1024}, device_scale_factor=1)
    errors = []
    page.on('console', lambda msg: errors.append(f'console {msg.type}: {msg.text}') if msg.type == 'error' else None)
    page.on('pageerror', lambda exc: errors.append(f'pageerror: {exc}'))
    page.goto('http://127.0.0.1:8555', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=60000)
    page.wait_for_timeout(4000)
    body = page.locator('body').inner_text()
    if 'Gestão de Pagamentos' not in body:
        raise AssertionError('Aplicacao renderizou, mas o titulo Gestão de Pagamentos nao foi localizado.')
    page.screenshot(path=str(OUT / 'rc16-tela-real.png'), full_page=True)
    (OUT / 'browser-errors.txt').write_text('\n'.join(errors), encoding='utf-8')
    if errors:
        raise AssertionError('Erros de navegador detectados: ' + ' | '.join(errors[:5]))
    browser.close()
