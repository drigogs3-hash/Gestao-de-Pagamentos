import pandas as pd
from core.historico import inicializar_banco, salvar_apuracao, validar_aprovacao_persistida

def _det(just=''):
    return pd.DataFrame([{
        'linha_origem': 10, 'OS':'38131', 'Cliente':'CLIENTE', 'Técnico':'RUBENS',
        'Tipo OS':'ALARME','Tipo Original':'ALARME','Tipo Pagamento':'ALARME',
        'Data':'2026-09-15','Início':'09:00','Término':'10:00','Tempo minutos':60,
        'Horas Pagas':1,'Regra':'HORÁRIO COMERCIAL','Valor 1ª Hora':90.10,
        'Valor Hora Adicional':53.0,'Valor Mão de Obra':90.10,'Quilometragem':0,
        'Pedágio':0,'Outros Ajustes':0,'Valor Total':90.10,'Justificativa Ajuste':just,
        'Origem do Valor':'VALOR MANUAL','Status':'AJUSTADO','Centro de Custo':'PRO'
    }])

def test_checklist_persistido_expoe_ajuste_sem_justificativa(tmp_path):
    db=tmp_path/'p.db'; inicializar_banco(db)
    det=_det('')
    conf={'aprovavel':True,'alertas':[],'checks':[]}
    ap=salvar_apuracao(det,pd.DataFrame(),conf,'teste.xlsx','09/2026',db_path=db)
    integ,_=validar_aprovacao_persistida(ap,db)
    chk=next(x for x in integ['checks'] if x['nome']=='Ajustes autorizados')
    assert chk['ok'] is False
    assert '38131' in chk['detalhe'] and 'VALOR MANUAL' in chk['detalhe']

def test_checklist_persistido_aceita_ajuste_justificado(tmp_path):
    db=tmp_path/'p.db'; inicializar_banco(db)
    det=_det('Valor fechado autorizado')
    conf={'aprovavel':True,'alertas':[],'checks':[]}
    ap=salvar_apuracao(det,pd.DataFrame(),conf,'teste.xlsx','09/2026',db_path=db)
    integ,_=validar_aprovacao_persistida(ap,db)
    chk=next(x for x in integ['checks'] if x['nome']=='Ajustes autorizados')
    assert chk['ok'] is True
