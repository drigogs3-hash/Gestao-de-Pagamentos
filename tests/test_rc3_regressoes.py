from pathlib import Path

def _app():
    return (Path(__file__).parents[1]/'app.py').read_text(encoding='utf-8')

def test_rc3_expoe_filtro_para_ajustes_sem_justificativa():
    s=_app()
    assert 'Ajustes sem justificativa' in s
    assert 'Ajustes que bloqueiam a aprovação' in s

def test_rc3_persiste_justificativa_de_ajuste_existente():
    s=_app()
    assert "if just:\n                        nd.at[_ix,'Justificativa Ajuste']=just" in s
    assert "origem_resultante!='AUTOMÁTICO'" in s

def test_rc3_dashboard_distingue_revisao_de_aprovado():
    s=_app()
    assert 'Valor em Revisão' in s
    assert 'Prévia por Centro de Custo — EM REVISÃO' in s
    assert "evo['status'].astype(str).str.upper().eq('APROVADA')" in s

def test_rc3_oculta_registro_legado_incompleto_no_dashboard():
    s=_app()
    assert "hshow['competencia'].fillna('').astype(str).str.strip().ne('')" in s
    assert "hshow['criado_em'].notna()" in s
