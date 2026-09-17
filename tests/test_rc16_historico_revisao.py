import pandas as pd
from core.historico import inicializar_banco, salvar_apuracao, carregar_detalhes

def test_historico_expoe_campos_financeiros_da_revisao(tmp_path):
    db=tmp_path/"r.db"; inicializar_banco(db)
    det=pd.DataFrame([{"linha_origem":1,"OS":"1","Cliente":"C","Técnico":"T","Tipo OS":"SERV",
      "Data":"2026-09-01","Início":"08:00","Término":"09:00","Tempo minutos":60,"Horas Pagas":1,"Regra":"HC",
      "Valor 1ª Hora":90.1,"Valor Hora Adicional":53,"Valor Total":105.1,"Centro de Custo":"CC","Status":"PROCESSADO",
      "Tipo Original":"SERV","Tipo Pagamento":"SERV","Valor Mão de Obra":90.1,"Quilometragem":10,"Pedágio":0,
      "Outros Ajustes":0,"Justificativa Ajuste":"ok","Origem do Valor":"REVISÃO TÉCNICA"}])
    ap=salvar_apuracao(det,pd.DataFrame(),{"aprovavel":True,"checks":[],"alertas":[]},"x.xlsx","09/2026",db_path=db)
    got=carregar_detalhes(ap,db_path=db)
    for c in ["tipo_pagamento","valor_mao_obra","quilometragem","pedagio","outros_ajustes","justificativa_ajuste","origem_valor"]:
        assert c in got.columns
    assert float(got.iloc[0]["quilometragem"])==10
