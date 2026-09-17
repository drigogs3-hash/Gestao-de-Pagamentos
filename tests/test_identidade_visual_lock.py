from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'assets/logo_sidebar_oficial.png': 'f4051ee7ee3c227c1227ad31537d7fc489dab07f3ec71086701c7a0e70aaa342',
    'assets/sidebar_condominio_aprovado_v95.png': '2e4dc9cbb5ce46b45f5180616f956b5740199c97a14eae53c4efc7c56f30d948',
    'assets/favicon_prosecurity.png': 'cae28549250310b601dc069a38c0432ed02976b22cdb1fea54be34a6346cfb6e',
    'assets/logo_prosecurity.png': '56bcfb0fee41011faa77df66e481852f89191f63a6679876fb602e03dcea9be4',
}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def test_identidade_visual_homologada_nao_foi_alterada():
    divergencias=[]
    for rel, esperado in EXPECTED.items():
        p=ROOT/rel
        if not p.exists() or sha256(p) != esperado:
            divergencias.append(rel)
    assert not divergencias, ('Identidade visual homologada alterada sem autorizacao. Arquivos divergentes: ' + ', '.join(divergencias) + '. Autorizacao exigida: ALTERE IDENTIDADE VISUAL')
