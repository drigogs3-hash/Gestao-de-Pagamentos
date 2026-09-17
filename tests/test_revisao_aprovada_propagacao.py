import json
import pandas as pd
from core.historico import inicializar_banco, salvar_apuracao, conectar, substituir_revisao


def _det(valor=180.20, km=0):
    return pd.DataFrame([{
        'linha_origem': 1, 'OS':'50001', 'Cliente':'COND A', 'Técnico':'002000 - TECNICO',
        'Tipo OS':'(MAN) (TORRE) PRO','Tipo Original':'(MAN) (TORRE) PRO','Tipo Pagamento':'(MAN) (TORRE) PRO',
        'Data':'2026-09-15','Início':'09:00','Término':'11:00','Tempo minutos':120,
        'Horas Pagas':2,'Regra':'HORÁRIO COMERCIAL','Valor 1ª Hora':127.20,
        'Valor Hora Adicional':53.0,'Valor Mão de Obra':180.20,'Quilometragem':km,
        'Pedágio':0,'Outros Ajustes':0,'Valor Total':valor,'Justificativa Ajuste':'Revisão do técnico',
        'Origem do Valor':'REVISÃO TÉCNICA','Status':'PROCESSADO','Centro de Custo':'MANUTENÇÃO SISTEMAS'
    }])


def test_revisao_tecnica_aprovada_atualiza_total_sem_duplicar(tmp_path):
    db=tmp_path/'p.db'; inicializar_banco(db)
    conf={'aprovavel':True,'alertas':[],'checks':[]}
    base=_det()
    ap=salvar_apuracao(base,pd.DataFrame(),conf,'teste.xlsx','09/2026',db_path=db)
    with conectar(db) as con:
        con.execute("UPDATE apuracoes SET status='APROVADA', aprovado_por='Rodrigo Santos', aprovado_em='2026-09-16T10:58:32' WHERE id=?",(ap,))
    novo=_det(195.20,10)
    substituir_revisao(ap,novo,pd.DataFrame(),conf,'Rodrigo Santos',base,db_path=db,permitir_aprovada=True)
    with conectar(db) as con:
        meta=con.execute('SELECT status,total FROM apuracoes WHERE id=?',(ap,)).fetchone()
        rows=con.execute('SELECT COUNT(*) qtd,SUM(valor_total) total FROM detalhes WHERE apuracao_id=?',(ap,)).fetchone()
        aud=con.execute("SELECT detalhes_json FROM auditoria WHERE apuracao_id=? AND evento='REVISAO_TECNICA_INCORPORADA' ORDER BY id DESC LIMIT 1",(ap,)).fetchone()
    assert meta['status']=='APROVADA'
    assert round(meta['total'],2)==195.20
    assert rows['qtd']==1 and round(rows['total'],2)==195.20
    assert round(json.loads(aud['detalhes_json'])['total_recalculado'],2)==195.20
