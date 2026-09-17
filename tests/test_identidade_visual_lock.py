import os, json, hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUTORIZACAO='ALTERE IDENTIDADE VISUAL'

def test_identidade_visual_aprovada_permanece_intacta():
    # Trava de desenvolvimento/build. Não produz qualquer elemento na interface.
    if os.environ.get('IDENTIDADE_VISUAL_AUTORIZACAO') == AUTORIZACAO:
        return
    manifest=json.loads((ROOT/'IDENTIDADE_VISUAL_LOCK.json').read_text(encoding='utf-8'))
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    css=app[app.index('<style>'):app.index('</style>')+8]
    assert hashlib.sha256(css.encode()).hexdigest()==manifest['css_sha256'], (
        'IDENTIDADE VISUAL BLOQUEADA. Para alterar a identidade, a solicitação deve conter exatamente: '
        + AUTORIZACAO
    )
    for rel,esperado in manifest['assets'].items():
        assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==esperado, f'Ativo visual protegido alterado: {rel}'
