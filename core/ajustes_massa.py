
from __future__ import annotations
import pandas as pd
from .processamento import processar
from .validacoes import canonicalizar_tipo_servico, normalizar_texto

VALOR_KM = 1.50

def deslocamento(km):
    try: v=max(0.0,float(km or 0))
    except Exception: v=0.0
    return round(v*VALOR_KM,2)

def montar_grade(man, mapa, det, pend):
    atuais={int(r['linha_origem']):r for _,r in det.iterrows()} if len(det) else {}
    pmap={int(r['linha_origem']):r for _,r in pend.iterrows()} if len(pend) else {}
    linhas=[]
    for i,row in man.iterrows():
        li=int(i)+2; d=atuais.get(li); p=pmap.get(li)
        def src(campo):
            col=mapa.get(campo)
            return row.get(col,'') if col else ''
        raw=src('tipo_os')
        if (pd.isna(raw) or str(raw).strip()=='') and mapa.get('tipo_os_fallback'):
            raw=row.get(mapa['tipo_os_fallback'],'')
        orig='' if pd.isna(raw) else str(raw).strip()
        data0=src('data'); ini0=src('inicio'); fim0=src('fim')
        if d is not None:
            tp=str(d.get('Tipo Pagamento',d.get('Tipo OS','')) or '')
            km=float(d.get('Quilometragem',0) or 0); ped=float(d.get('Pedágio',0) or 0)
            out=float(d.get('Outros Ajustes',0) or 0); just=str(d.get('Justificativa Ajuste','') or '')
            mo=float(d.get('Valor Mão de Obra',d.get('Valor Total',0)) or 0)
            sit=str(d.get('Status','PROCESSADO')); motivo=''
            osval=d.get('OS',''); cli=d.get('Cliente',''); tec=d.get('Técnico','')
        else:
            tp=canonicalizar_tipo_servico(orig) if orig else ''
            km=ped=out=mo=0.0; just=''; sit='PENDENTE'
            osval=src('os'); cli=src('cliente'); tec=src('tecnico')
            motivo=str(p.get('Motivo','')) if p is not None else 'Pendente'
        ml=motivo.lower(); acao=''
        if sit=='PENDENTE':
            if 'parametrização não encontrada' in ml or 'tipo_os não informado' in ml:
                acao='Selecione o Tipo para Pagamento'
            elif 'data' in ml and ('não inform' in ml or 'inval' in ml):
                acao='Informe/corrija a Data do atendimento'
            elif 'inicio não informado' in ml or 'início não informado' in ml:
                acao='Informe/corrija a Hora Início'
            elif 'fim não informado' in ml:
                acao='Informe/corrija a Hora Fim'
            else: acao='Corrija a informação indicada na pendência'
        linhas.append({'linha_origem':li,'OS':osval,'Cliente':cli,'Técnico':tec,
          'Data Original':data0,'Data':data0,'Hora Início Original':ini0,'Hora Início':ini0,
          'Hora Fim Original':fim0,'Hora Fim':fim0,'Tipo Original':orig,'Tipo para Pagamento':tp,
          'KM':km,'Deslocamento':deslocamento(km),'Pedágio':ped,'Outros':out,'Justificativa':just,
          'Mão de Obra':mo,'Total':round(mo+deslocamento(km)+ped+out,2),'Situação':sit,
          'Pendência':motivo,'Ação necessária':acao})
    grade=pd.DataFrame(linhas)
    # Streamlit exige dtype compatível com DateColumn/TimeColumn.
    # Originais ficam intactos; somente as colunas editáveis são tipadas.
    if len(grade):
        grade['Data']=pd.to_datetime(grade['Data'],dayfirst=True,errors='coerce').dt.date
        def _hora_editavel(v):
            if v is None or (isinstance(v,float) and pd.isna(v)) or str(v).strip()=='':
                return None
            if hasattr(v,'hour') and hasattr(v,'minute'):
                try:
                    return v.time() if hasattr(v,'time') and not isinstance(v, __import__('datetime').time) else v
                except Exception:
                    return v
            t=pd.to_datetime(str(v),errors='coerce')
            return None if pd.isna(t) else t.time()
        grade['Hora Início']=grade['Hora Início'].map(_hora_editavel)
        grade['Hora Fim']=grade['Hora Fim'].map(_hora_editavel)
    return grade


def linhas_editadas_usuario(base: pd.DataFrame, editado: pd.DataFrame):
    """Retorna linha_origem alteradas pelo usuário comparando com o DataFrame
    EXATO entregue ao data_editor, e não com a planilha original/reconstruída.

    Isso evita falsos ajustes causados por Timestamp/date, datetime/time, NaN/None
    ou canonicalização interna. Justificativa não conta como alteração de negócio.
    """
    campos = ['Data','Hora Início','Hora Fim','Tipo para Pagamento','KM','Pedágio','Outros','Mão de Obra']
    if base is None or editado is None or not len(base) or not len(editado):
        return set()
    b=base.set_index('linha_origem', drop=False)
    e=editado.set_index('linha_origem', drop=False)

    def _vazio(v):
        if v is None: return True
        try:
            if pd.isna(v): return True
        except Exception:
            pass
        return isinstance(v,str) and not v.strip()

    def _norm(c,v):
        import datetime as _dt
        if _vazio(v): return ''
        if c=='Data':
            t=pd.to_datetime(v,dayfirst=True,errors='coerce')
            return str(v).strip() if pd.isna(t) else t.strftime('%Y-%m-%d')
        if c in ('Hora Início','Hora Fim'):
            if isinstance(v,_dt.time): return v.strftime('%H:%M:%S')
            if isinstance(v,(_dt.datetime,pd.Timestamp)): return v.strftime('%H:%M:%S')
            t=pd.to_datetime(str(v).strip(),errors='coerce')
            return str(v).strip() if pd.isna(t) else t.strftime('%H:%M:%S')
        if c in ('KM','Pedágio','Outros','Mão de Obra'):
            try: return round(float(v),6)
            except Exception: return str(v).strip()
        return str(v).strip()

    alteradas=set()
    for li in b.index.intersection(e.index):
        for c in campos:
            if c in b.columns and c in e.columns and _norm(c,b.at[li,c]) != _norm(c,e.at[li,c]):
                alteradas.add(int(li)); break
    return alteradas

def recalcular_grade(man, mapa, param, grade, hc_inicio, hc_fim, feriados, permitir_virada=True):
    g=grade.copy(); man2=man.copy(); eg=g.set_index('linha_origem')
    def vals(c, mapa_campo=None):
        out=[]
        for i in range(len(man2)):
            e=eg.loc[i+2]
            if c in e.index and not pd.isna(e.get(c)):
                v=e.get(c)
            else:
                col=mapa.get(mapa_campo) if mapa_campo else None
                v=man2.iloc[i].get(col,'') if col else ''
            out.append(v)
        return out
    man2['__TIPO_PAGAMENTO__']=vals('Tipo para Pagamento','tipo_os')
    man2['__DATA_CORRIGIDA__']=vals('Data','data')
    man2['__INICIO_CORRIGIDO__']=vals('Hora Início','inicio')
    man2['__FIM_CORRIGIDO__']=vals('Hora Fim','fim')
    # V11.13: processar() recebe explicitamente os valores corrigidos da grade.
    # Convertemos time/date para formatos estáveis para impedir fallback ao original vazio.
    def _fmt_data(v):
        if v is None or (isinstance(v,float) and pd.isna(v)) or str(v).strip()=='': return ''
        t=pd.to_datetime(v,dayfirst=True,errors='coerce')
        return v if pd.isna(t) else t.strftime('%d/%m/%Y')
    def _fmt_hora(v):
        import datetime as _dt
        if v is None or (isinstance(v,float) and pd.isna(v)) or str(v).strip()=='': return ''
        if isinstance(v,_dt.time): return v.strftime('%H:%M:%S')
        if isinstance(v,(_dt.datetime,pd.Timestamp)): return v.strftime('%H:%M:%S')
        t=pd.to_datetime(str(v),errors='coerce')
        return v if pd.isna(t) else t.strftime('%H:%M:%S')
    man2['__DATA_CORRIGIDA__']=man2['__DATA_CORRIGIDA__'].map(_fmt_data)
    man2['__INICIO_CORRIGIDO__']=man2['__INICIO_CORRIGIDO__'].map(_fmt_hora)
    man2['__FIM_CORRIGIDO__']=man2['__FIM_CORRIGIDO__'].map(_fmt_hora)
    mapa2=dict(mapa); mapa2['tipo_os']='__TIPO_PAGAMENTO__'; mapa2.pop('tipo_os_fallback',None)
    mapa2['data']='__DATA_CORRIGIDA__'; mapa2['inicio']='__INICIO_CORRIGIDO__'; mapa2['fim']='__FIM_CORRIGIDO__'
    det,pend=processar(man2,param,mapa2,hc_inicio,hc_fim,feriados,permitir_virada_dia=permitir_virada)
    if len(det):
        for ix,r in det.iterrows():
            li=int(r['linha_origem']); e=eg.loc[li]
            km=max(0.0,float(e.get('KM',0) or 0)); ped=max(0.0,float(e.get('Pedágio',0) or 0))
            out=float(e.get('Outros',0) or 0); just=str(e.get('Justificativa','') or '').strip()
            mo=float(r.get('Valor Mão de Obra',r.get('Valor Total',0)) or 0)
            original=str(e.get('Tipo Original','') or ''); escolhido=canonicalizar_tipo_servico(e.get('Tipo para Pagamento',''))
            tipo_digitado=str(e.get('Tipo para Pagamento','') or '')
            eh_valor_fechado='M.O VALOR FECHADO' in normalizar_texto(tipo_digitado) or 'MO VALOR FECHADO' in normalizar_texto(tipo_digitado)
            valor_manual=False
            if eh_valor_fechado:
                try:
                    mo_editado=max(0.0,float(e.get('Mão de Obra',0) or 0))
                except Exception:
                    mo_editado=0.0
                if mo_editado>0:
                    mo=mo_editado
                    valor_manual=True
            mudou_tipo=canonicalizar_tipo_servico(original)!=escolhido

            # V11.16: compara valores semanticamente, não a representação Python/Excel.
            # Ex.: Timestamp('2026-09-09'), date(2026,9,9) e '09/09/2026' são a MESMA data;
            # time(9,33), '09:33:00' e um datetime Excel com 09:33 são a MESMA hora.
            # Isso impede que normalização interna marque dezenas de OS como AJUSTADAS.
            def _data_norm(v):
                if v is None or (isinstance(v,float) and pd.isna(v)) or str(v).strip()=='':
                    return ''
                t=pd.to_datetime(v,dayfirst=True,errors='coerce')
                return str(v).strip() if pd.isna(t) else t.strftime('%Y-%m-%d')
            def _hora_norm(v):
                import datetime as _dt
                if v is None or (isinstance(v,float) and pd.isna(v)) or str(v).strip()=='':
                    return ''
                if isinstance(v,_dt.time):
                    return v.strftime('%H:%M:%S')
                if isinstance(v,(_dt.datetime,pd.Timestamp)):
                    return v.strftime('%H:%M:%S')
                t=pd.to_datetime(str(v),errors='coerce')
                return str(v).strip() if pd.isna(t) else t.strftime('%H:%M:%S')

            mudou_data=_data_norm(e.get('Data Original','')) != _data_norm(e.get('Data',''))
            mudou_ini=_hora_norm(e.get('Hora Início Original','')) != _hora_norm(e.get('Hora Início',''))
            mudou_fim=_hora_norm(e.get('Hora Fim Original','')) != _hora_norm(e.get('Hora Fim',''))
            mudou_dados=mudou_data or mudou_ini or mudou_fim
            tem_desp=km>0 or ped>0 or abs(out)>.005
            det.at[ix,'Tipo Original']=original; det.at[ix,'Tipo Pagamento']=escolhido
            det.at[ix,'Valor Mão de Obra']=mo; det.at[ix,'Quilometragem']=km; det.at[ix,'Pedágio']=ped
            det.at[ix,'Outros Ajustes']=out; det.at[ix,'Justificativa Ajuste']=just
            det.at[ix,'Valor Total']=round(mo+deslocamento(km)+ped+out,2)
            det.at[ix,'Data Original']=e.get('Data Original',''); det.at[ix,'Data Corrigida']=e.get('Data','')
            det.at[ix,'Hora Início Original']=e.get('Hora Início Original',''); det.at[ix,'Hora Início Corrigida']=e.get('Hora Início','')
            det.at[ix,'Hora Fim Original']=e.get('Hora Fim Original',''); det.at[ix,'Hora Fim Corrigida']=e.get('Hora Fim','')
            det.at[ix,'Origem do Valor']='VALOR MANUAL' if valor_manual else ('AJUSTE DE DADOS' if mudou_dados else ('RECLASSIFICADO + DESPESAS' if mudou_tipo and tem_desp else ('RECLASSIFICADO' if mudou_tipo else ('COM DESPESAS' if tem_desp else 'AUTOMÁTICO'))))
            if str(det.at[ix,'Status']).upper()!='DUPLICADA E SEM VALOR':
                det.at[ix,'Status']='AJUSTADO' if (mudou_tipo or mudou_dados or tem_desp or valor_manual) else 'PROCESSADO'
    return det,pend
