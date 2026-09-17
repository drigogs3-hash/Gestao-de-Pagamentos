from __future__ import annotations
from datetime import datetime, time, timedelta
import pandas as pd

PLANTAO_INICIO_SEXTA = time(18,0)
PLANTAO_FIM_SEGUNDA = time(6,0)


def _dt(row):
    d = pd.to_datetime(row.get('Data'), errors='coerce')
    if pd.isna(d): return None, None
    try:
        hi = pd.to_datetime(str(row.get('Início')), errors='raise').time()
        hf = pd.to_datetime(str(row.get('Término')), errors='raise').time()
    except Exception:
        return None, None
    ini = datetime.combine(d.date(), hi)
    fim = datetime.combine(d.date(), hf)
    if fim < ini: fim += timedelta(days=1)
    return ini, fim


def eh_plantao_fds(dt: datetime) -> bool:
    wd, t = dt.weekday(), dt.time()
    return wd == 4 and t >= PLANTAO_INICIO_SEXTA or wd in (5,6) or wd == 0 and t < PLANTAO_FIM_SEGUNDA


def faixa_plantao(dt: datetime) -> str:
    if not eh_plantao_fds(dt): return 'FORA DO PLANTÃO FDS'
    if dt.weekday() == 4: return 'SEXTA 18H–00H'
    if dt.weekday() == 5: return 'SÁBADO'
    if dt.weekday() == 6: return 'DOMINGO'
    return 'SEGUNDA 00H–06H'


def chave_fim_de_semana(dt: datetime) -> str:
    # identifica o fim de semana pela sexta-feira que inicia a janela
    if dt.weekday() == 4:
        sexta = dt.date()
    elif dt.weekday() == 5:
        sexta = (dt - timedelta(days=1)).date()
    elif dt.weekday() == 6:
        sexta = (dt - timedelta(days=2)).date()
    elif dt.weekday() == 0 and dt.time() < PLANTAO_FIM_SEGUNDA:
        sexta = (dt - timedelta(days=3)).date()
    else:
        return ''
    return sexta.isoformat()


def enriquecer_plantao(det: pd.DataFrame) -> pd.DataFrame:
    out = det.copy()
    flags=[]; faixas=[]; fins=[]; inis=[]; terminos=[]
    for _, r in out.iterrows():
        ini, fim = _dt(r)
        flag = bool(ini and eh_plantao_fds(ini))
        flags.append(flag)
        faixas.append(faixa_plantao(ini) if ini else 'NÃO IDENTIFICADO')
        fins.append(chave_fim_de_semana(ini) if flag else '')
        inis.append(ini); terminos.append(fim)
    out['Plantão FDS'] = flags
    out['Faixa Plantão'] = faixas
    out['Fim de Semana'] = fins
    out['_dt_inicio'] = inis
    out['_dt_fim'] = terminos
    return out


def analisar_plantao(det: pd.DataFrame) -> dict:
    e = enriquecer_plantao(det)
    p = e[e['Plantão FDS']].copy()
    total_os=len(e); qtd=len(p)
    total_val=float(pd.to_numeric(e.get('Valor Total', pd.Series(dtype=float)), errors='coerce').sum())
    valor=float(pd.to_numeric(p.get('Valor Total', pd.Series(dtype=float)), errors='coerce').sum())
    minutos=float(pd.to_numeric(p.get('Tempo minutos', pd.Series(dtype=float)), errors='coerce').sum())
    horas=minutos/60 if minutos else 0.0
    simultaneas=set()
    rows=list(p.iterrows())
    for a in range(len(rows)):
        ia, ra=rows[a]; ai, af=ra['_dt_inicio'], ra['_dt_fim']
        if not ai or not af: continue
        for b in range(a+1,len(rows)):
            ib, rb=rows[b]; bi,bf=rb['_dt_inicio'],rb['_dt_fim']
            if bi and bf and ai < bf and bi < af:
                simultaneas.add(ia); simultaneas.add(ib)
    return {
        'detalhes': e.drop(columns=['_dt_inicio','_dt_fim'], errors='ignore'),
        'plantao': p.drop(columns=['_dt_inicio','_dt_fim'], errors='ignore'),
        'qtd': qtd,
        'percentual_qtd': qtd/total_os*100 if total_os else 0,
        'valor': valor,
        'percentual_valor': valor/total_val*100 if total_val else 0,
        'horas_efetivas': horas,
        'custo_por_acionamento': valor/qtd if qtd else 0,
        'custo_hora_efetiva': valor/horas if horas else 0,
        'finais_semana_acionados': int(p['Fim de Semana'].nunique()) if qtd else 0,
        'os_com_simultaneidade': len(simultaneas),
    }
