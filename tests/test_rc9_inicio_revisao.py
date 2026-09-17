import os, tempfile
from core.revisoes_tecnicos import obter_ou_criar_revisao, iniciar_revisao, listar_revisoes

def test_revisao_so_aparece_apos_inicio_expresso():
    fd, db = tempfile.mkstemp(suffix='.db'); os.close(fd)
    try:
        r = obter_ou_criar_revisao('ap-rc9','TECNICO A','09/2026',db)
        assert listar_revisoes('ap-rc9',db).empty
        iniciar_revisao(r['id'],db)
        x = listar_revisoes('ap-rc9',db)
        assert len(x) == 1
        assert x.iloc[0]['tecnico'] == 'TECNICO A'
        assert x.iloc[0]['status'] == 'AGUARDANDO RETORNO'
    finally:
        try: os.remove(db)
        except OSError: pass

def test_tecnicos_nao_iniciados_nao_se_misturam():
    fd, db = tempfile.mkstemp(suffix='.db'); os.close(fd)
    try:
        a = obter_ou_criar_revisao('ap-rc9b','ALEX','09/2026',db)
        obter_ou_criar_revisao('ap-rc9b','RUBENS','09/2026',db)
        iniciar_revisao(a['id'],db)
        x = listar_revisoes('ap-rc9b',db)
        assert x['tecnico'].tolist() == ['ALEX']
    finally:
        try: os.remove(db)
        except OSError: pass
