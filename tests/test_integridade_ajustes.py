import pandas as pd
from core.integridade import validar_ajustes

def test_ajuste_sem_justificativa_identifica_os_e_origem():
    det=pd.DataFrame([{'OS':'38131','linha_origem':10,'Valor Mão de Obra':100,'Quilometragem':0,'Pedágio':0,'Outros Ajustes':0,'Valor Total':100,'Origem do Valor':'VALOR MANUAL','Justificativa Ajuste':''}])
    erros=validar_ajustes(det)
    assert erros == ['OS 38131: ajuste sem justificativa (origem: VALOR MANUAL)']
