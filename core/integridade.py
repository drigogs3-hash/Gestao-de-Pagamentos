from __future__ import annotations
from datetime import datetime
import hashlib, json
import pandas as pd
from .tabela_valores import tarifa_oficial, TABELA_VERSAO

def _num(v):
    try:
        x=float(v)
        return x if pd.notna(x) else None
    except Exception:
        return None

def hash_dataframe(df: pd.DataFrame) -> str:
    """Hash canônico dos campos críticos; ignora diferenças de tipo int/float do SQLite."""
    if df is None or df.empty:
        return hashlib.sha256(b"EMPTY").hexdigest()
    campos=["OS","Cliente","Técnico","Tipo OS","Tipo Original","Tipo Pagamento","Data","Início","Término","Tempo minutos",
            "Horas Pagas","Regra","Valor 1ª Hora","Valor Hora Adicional","Valor Mão de Obra","Quilometragem","Pedágio",
            "Outros Ajustes","Valor Total","Justificativa Ajuste","Origem do Valor","Status","Centro de Custo"]
    numericos={"Tempo minutos","Horas Pagas","Valor 1ª Hora","Valor Hora Adicional","Valor Mão de Obra","Quilometragem","Pedágio","Outros Ajustes","Valor Total"}
    registros=[]
    for _,r in df.iterrows():
        item=[]
        for c in campos:
            defaults={"Tipo Original":r.get("Tipo OS",""),"Tipo Pagamento":r.get("Tipo OS",""),"Valor Mão de Obra":r.get("Valor Total",0),"Quilometragem":0,"Pedágio":0,"Outros Ajustes":0,"Justificativa Ajuste":"","Origem do Valor":"AUTOMÁTICO","Status":"PROCESSADO"}
            v=r.get(c,defaults.get(c,""))
            if (v is None or (isinstance(v,float) and pd.isna(v)) or str(v).strip()=="") and c in defaults:
                v=defaults[c]
            if c in numericos:
                n=_num(v)
                item.append("" if n is None else f"{n:.6f}")
            else:
                item.append(str(v).strip())
        registros.append(item)
    payload=json.dumps(registros,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def validar_tabela_oficial():
    """Autoteste da tabela: cobertura, valores positivos e ausência de conflito."""
    erros=[]
    tipos=['ALARME','CFTV ANALOGICO','CFTV IP','CONTROLE DE ACESSO',
           'CERCA ELETRICA','TELECOMUNICACAO','INFORMATICA','PORTAO']
    tecnicos=['ELIODORIO','RUBENS','ALEXANDRE','ERINALDO']
    vistos={}
    for tec in tecnicos:
        for tipo in tipos:
            for fora in (False, True):
                r=tarifa_oficial(tec,tipo,fora)
                if r is None:
                    erros.append(f"Sem tarifa: {tec}/{tipo}/{'FORA' if fora else 'HC'}")
                    continue
                v1,va,desc=r
                if v1 <= 0 or va <= 0:
                    erros.append(f"Valor inválido: {tec}/{tipo}/{desc}")
                chave=(tec,tipo,fora)
                atual=(round(v1,2),round(va,2))
                if chave in vistos and vistos[chave]!=atual:
                    erros.append(f"Regra conflitante: {chave}")
                vistos[chave]=atual
    return {"ok":not erros,"erros":erros,"versao":TABELA_VERSAO}

def validar_tempos(det):
    erros=[]
    if det is None or det.empty: return ["Nenhuma OS processada."]
    for i,r in det.iterrows():
        mins=_num(r.get("Tempo minutos"))
        hp=_num(r.get("Horas Pagas"))
        linha=r.get("linha_origem",i+2)
        if mins is None or mins < 0:
            erros.append(f"linha {linha}: tempo inválido")
            continue
        # Regra: primeira hora sempre; tolerância de 15 min.
        esperado=max(1, int((max(0, mins-15)+59)//60))
        if hp is None or int(hp)!=esperado:
            erros.append(f"linha {linha}: {mins:.0f} min exige {esperado}h paga(s), encontrado {hp}")
    return erros

def validar_tarifas(det):
    erros=[]
    if det is None or det.empty: return ["Nenhuma OS processada."]
    for i,r in det.iterrows():
        linha=r.get("linha_origem",i+2)
        if str(r.get("Status","")).upper() == "DUPLICADA E SEM VALOR":
            continue
        regra=str(r.get("Regra","")).upper()
        fora=regra.startswith("FORA")
        tipo_pag=r.get("Tipo Pagamento",r.get("Tipo OS",""))
        of=tarifa_oficial(r.get("Técnico",""),tipo_pag,fora)
        if of is None:
            erros.append(f"linha {linha}: tipo sem tarifa oficial")
            continue
        e1,ea,desc=of
        a1=_num(r.get("Valor 1ª Hora")); aa=_num(r.get("Valor Hora Adicional"))
        if a1 is None or aa is None or abs(a1-e1)>.005 or abs(aa-ea)>.005:
            erros.append(f"linha {linha}: {desc} esperado R$ {e1:.2f}/R$ {ea:.2f}")
    return erros

def validar_conciliacao(det):
    if det is None or det.empty:
        return False, "Nenhuma OS para conciliar."
    valor=pd.to_numeric(det.get("Valor Total",0),errors="coerce").fillna(0)
    total=round(float(valor.sum()),2)
    d=det.copy(); d["_v"]=valor
    tec=round(float(d.groupby("Técnico",dropna=False)["_v"].sum().sum()),2)
    cc_col="Centro de Custo" if "Centro de Custo" in d.columns else ("Centro Custo" if "Centro Custo" in d.columns else None)
    cc=round(float(d.groupby(cc_col,dropna=False)["_v"].sum().sum()),2) if cc_col else total
    ok=abs(total-tec)<.005 and abs(total-cc)<.005
    return ok, f"OS R$ {total:.2f} | Técnicos R$ {tec:.2f} | Centros R$ {cc:.2f}"

def _norm_chave(v):
    x=str(v if v is not None else '').strip().upper()
    if x.endswith('.0') and x[:-2].isdigit(): x=x[:-2]
    return ' '.join(x.split())

def detectar_duplicidades_internas(det):
    """Retorna duplicidades OS+Cliente que ainda NÃO foram saneadas com valor zero."""
    if det is None or det.empty or "OS" not in det.columns or "Cliente" not in det.columns: return []
    x=det.copy(); x['_os']=x['OS'].map(_norm_chave); x['_cl']=x['Cliente'].map(_norm_chave)
    dup=x['_os'].ne('') & x['_cl'].ne('') & x.duplicated(['_os','_cl'],keep='first')
    status = x['Status'].astype(str).str.upper() if 'Status' in x.columns else pd.Series('', index=x.index)
    valores = pd.to_numeric(x['Valor Total'],errors='coerce').fillna(0) if 'Valor Total' in x.columns else pd.Series(0.0,index=x.index)
    nao_saneada=dup & ~((valores.abs()<0.005) & (status=='DUPLICADA E SEM VALOR'))
    return [f"OS {r['_os']} / {r['_cl']}" for _,r in x[nao_saneada].iterrows()]

def contar_duplicidades_saneadas(det):
    if det is None or det.empty or 'Status' not in det.columns: return 0
    return int((det['Status'].astype(str).str.upper()=='DUPLICADA E SEM VALOR').sum())

def detectar_duplicidades_historico(det, detalhes_historicos):
    """Compara OS+Cliente atual contra pagamentos já APROVADOS; exige conferência humana."""
    if det is None or det.empty or detalhes_historicos is None or detalhes_historicos.empty: return []
    if not {'OS','Cliente'}.issubset(det.columns) or not {'os','cliente'}.issubset(detalhes_historicos.columns): return []
    atuais={( _norm_chave(r['OS']), _norm_chave(r['Cliente']) ) for _,r in det.iterrows() if _norm_chave(r['OS']) and _norm_chave(r['Cliente']) and str(r.get('Status','')).upper()!='DUPLICADA E SEM VALOR'}
    achados=[]
    for _,r in detalhes_historicos.iterrows():
        chave=(_norm_chave(r.get('os','')),_norm_chave(r.get('cliente','')))
        if chave in atuais:
            achados.append({'os':chave[0],'cliente':chave[1],'tecnico':r.get('tecnico',''),'valor':_num(r.get('valor_total')) or 0,'apuracao_id':r.get('apuracao_id','')})
    return achados

def validar_ajustes(det):
    erros=[]
    if det is None or det.empty: return erros
    for i,r in det.iterrows():
        if str(r.get('Status','')).upper()=='DUPLICADA E SEM VALOR': continue
        mo=_num(r.get('Valor Mão de Obra',r.get('Valor Total',0))) or 0
        km=_num(r.get('Quilometragem',0)) or 0; ped=_num(r.get('Pedágio',0)) or 0; out=_num(r.get('Outros Ajustes',0)) or 0
        total=_num(r.get('Valor Total')) or 0
        if abs(total-(mo+(km*1.50)+ped+out))>.005: erros.append(f"linha {r.get('linha_origem',i+2)}: total não concilia com ajustes (KM × R$ 1,50)")
        origem=str(r.get('Origem do Valor','AUTOMÁTICO')).upper()
        if origem!='AUTOMÁTICO' and not str(r.get('Justificativa Ajuste','')).strip():
            os_id = str(r.get('OS','')).strip() or 'não identificada'
            erros.append(f"OS {os_id}: ajuste sem justificativa (origem: {origem})")
    return erros

def checklist_integridade(det, pendencias=None, detalhes_historicos=None):
    tab=validar_tabela_oficial()
    et=validar_tempos(det)
    ev=validar_tarifas(det)
    dup_i=detectar_duplicidades_internas(det)
    dup_h=detectar_duplicidades_historico(det,detalhes_historicos)
    conc_ok,conc_msg=validar_conciliacao(det)
    aj=validar_ajustes(det)
    dup_s=contar_duplicidades_saneadas(det)
    pend=0 if pendencias is None else len(pendencias)
    checks=[
        {"nome":"Tabela oficial","ok":tab["ok"],"detalhe":f"Versão {tab['versao']}" if tab["ok"] else "; ".join(tab["erros"][:3])},
        {"nome":"Tarifas conferidas","ok":not ev,"detalhe":f"{len(det) if det is not None else 0}/{len(det) if det is not None else 0} OS" if not ev else "; ".join(ev[:3])},
        {"nome":"Duplicidades tratadas","ok":not dup_i,"detalhe":f"{dup_s} duplicada(s) zerada(s)" if not dup_i else "Não saneadas: "+", ".join(dup_i[:5])},
        {"nome":"OS já existentes no histórico","ok":not dup_h,"detalhe":"0 encontradas" if not dup_h else "; ".join(f"OS {x['os']} / {x['cliente']} já paga" for x in dup_h[:5])},
        {"nome":"Tempos e tolerância","ok":not et,"detalhe":"Todos conferidos" if not et else "; ".join(et[:3])},
        {"nome":"Ajustes autorizados","ok":not aj,"detalhe":"Ajustes conciliados e justificados" if not aj else "; ".join(aj[:3])},
        {"nome":"Conciliação financeira","ok":conc_ok,"detalhe":conc_msg},
        {"nome":"Pendências","ok":pend==0,"detalhe":f"{pend} pendência(s)"},
    ]
    return {
        "checks":checks,
        "ok":all(x["ok"] for x in checks),
        "hash_detalhes":hash_dataframe(det),
        "tabela_versao":TABELA_VERSAO,
        "gerado_em":datetime.now().isoformat(timespec="seconds"),
    }

def revalidar_hash(det, hash_validado):
    return hash_dataframe(det)==hash_validado
