from __future__ import annotations
import io, hashlib, json, sqlite3, unicodedata, re
from datetime import datetime
import pandas as pd
from core.storage import criar_backup_banco

def _norm(v):
    s=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().upper()
    return " ".join(s.replace("_"," ").split())

def _known_key(desc,v1,va):
    d=_norm(desc)
    # O arquivo operacional usa o prefixo (MAN). Para serviços-base já
    # cadastrados, esse prefixo não cria um serviço diferente.
    base=re.sub(r'^\(?MAN\)?\s*[-–—:]?\s*','',d).strip()
    if base=="ALARME": return "ALARME"
    if base=="CFTV ANALOGICO": return "CFTV ANALOGICO"
    if base=="CFTV IP": return "CFTV IP"
    if base in ("CONTROLE ACESSO","CONTROLE DE ACESSO"): return "CONTROLE DE ACESSO"
    if base in ("CERCA ELETRICA","CERCA ELÉTRICA"): return "CERCA ELETRICA"
    if base=="INFORMATICA": return "INFORMATICA"
    if "MAN" in d and "TORRE" in d and "PRO" in d: return "MAN_TORRE_PRO"
    if "M.O VALOR FECHADO" in d or "MO VALOR FECHADO" in d: return "MAN_MO_VALOR_FECHADO"
    if "FORA DO HORARIO" in d and "EXCETO PORTAO" in d: return "FORA_DEMAIS"
    if "PORTAO" in base and "FORA" in base: return "PORTAO_FORA"
    if "PORTAO" in base and ("QUALQUER TECNICO" in base or "DEMAIS TECNICOS" in base): return "PORTAO_DEMAIS_HC"
    if base=="PORTAO": return "PORTAO_ESPECIAL_HC"
    if "TELECOMUNIC" in base:
        return "TELECOM_ESPECIAL_HC" if float(v1 or 0)>=190 else "TELECOMUNICACAO"
    return None

def chave_servico(desc,v1=0,va=0):
    known=_known_key(desc,v1,va)
    if known: return known
    # Serviços novos são válidos por definição. A chave é derivada do nome normalizado.
    return "SERVICO::"+_norm(desc)

def ler_tabela_tarifas(upload_bytes):
    df=pd.read_excel(io.BytesIO(upload_bytes),header=0).dropna(how="all").copy()
    if df.shape[1]<3:
        raise ValueError("A planilha deve possuir pelo menos 3 colunas: Seguimento, Valor 1ª Hora e Valor Hora Adicional.")
    # Somente as 3 primeiras colunas alimentam o cadastro. Colunas adicionais
    # são observações/regras e jamais viram campos de preço/cadastro.
    df=df.iloc[:,:3].copy()
    df.columns=["Seguimento","Valor 1ª Hora","Valor Hora Adicional"]
    df["Seguimento"]=df["Seguimento"].astype(str).str.strip()
    df["Valor 1ª Hora"]=pd.to_numeric(df["Valor 1ª Hora"],errors="coerce")
    df["Valor Hora Adicional"]=pd.to_numeric(df["Valor Hora Adicional"],errors="coerce")
    df=df[df["Seguimento"].ne("nan") & df["Seguimento"].ne("")].reset_index(drop=True)

    erros=[]; chaves=[]
    for i,r in df.iterrows():
        if pd.isna(r["Valor 1ª Hora"]) or pd.isna(r["Valor Hora Adicional"]):
            erros.append(f"Linha {i+2}: valor inválido.")
            chaves.append(None)
        else:
            chaves.append(chave_servico(r["Seguimento"],r["Valor 1ª Hora"],r["Valor Hora Adicional"]))
    df["Chave"]=chaves

    # Repetição idêntica não bloqueia; é consolidada. Valores diferentes na mesma
    # chave são conflito, exceto TELECOM, cujas duas regras conhecidas têm chaves distintas.
    conflitos=[]
    for chave,g in df.dropna(subset=["Chave"]).groupby("Chave"):
        pares=g[["Valor 1ª Hora","Valor Hora Adicional"]].drop_duplicates()
        if len(pares)>1:
            conflitos.append(f"Serviço repetido com valores diferentes: {g.iloc[0]['Seguimento']}.")
    erros.extend(conflitos)
    if not erros:
        df=df.drop_duplicates(subset=["Chave"],keep="last").reset_index(drop=True)
    return df,erros

def comparar_tabela_tarifas(upload_bytes,db_path):
    df,erros=ler_tabela_tarifas(upload_bytes)
    if erros: return df,erros
    atuais={}
    with sqlite3.connect(db_path) as con:
        for row in con.execute("SELECT chave,descricao,valor_primeira,valor_adicional,ativo FROM tarifas"):
            atuais[row[0]]=row[1:]
    situacoes=[]; anteriores1=[]; anterioresa=[]
    for _,r in df.iterrows():
        atual=atuais.get(r["Chave"])
        if atual is None:
            situacoes.append("NOVO SERVIÇO"); anteriores1.append(None); anterioresa.append(None)
        else:
            a1,aa=float(atual[1]),float(atual[2])
            anteriores1.append(a1); anterioresa.append(aa)
            mudou=abs(a1-float(r["Valor 1ª Hora"]))>.004 or abs(aa-float(r["Valor Hora Adicional"]))>.004 or int(atual[3])!=1
            situacoes.append("VALOR ALTERADO" if mudou else "SEM ALTERAÇÃO")
    out=df.copy()
    out["Situação"]=situacoes
    out["Valor 1ª Hora Anterior"]=anteriores1
    out["Valor Hora Adicional Anterior"]=anterioresa
    return out,[]

def aplicar_tabela_tarifas(upload_bytes,nome_arquivo,usuario,db_path):
    df,erros=comparar_tabela_tarifas(upload_bytes,db_path)
    if erros: raise ValueError(" | ".join(erros))
    versao=datetime.now().strftime("%d/%m/%Y-%H%M%S")
    sha=hashlib.sha256(upload_bytes).hexdigest()
    backup=criar_backup_banco(db_path,"antes_importacao_tarifas")
    agora=datetime.now().isoformat(timespec="seconds")
    mudancas=[]
    with sqlite3.connect(db_path) as con:
        con.execute("BEGIN IMMEDIATE")
        for _,r in df.iterrows():
            if r["Situação"]=="SEM ALTERAÇÃO":
                continue
            antes={"valor_primeira":None if pd.isna(r["Valor 1ª Hora Anterior"]) else float(r["Valor 1ª Hora Anterior"]),
                   "valor_adicional":None if pd.isna(r["Valor Hora Adicional Anterior"]) else float(r["Valor Hora Adicional Anterior"])}
            depois={"valor_primeira":float(r["Valor 1ª Hora"]),"valor_adicional":float(r["Valor Hora Adicional"])}
            con.execute("""INSERT INTO tarifas(chave,descricao,valor_primeira,valor_adicional,ativo,versao,atualizado_em)
                           VALUES(?,?,?,?,1,?,?)
                           ON CONFLICT(chave) DO UPDATE SET descricao=excluded.descricao,
                           valor_primeira=excluded.valor_primeira,valor_adicional=excluded.valor_adicional,
                           ativo=1,versao=excluded.versao,atualizado_em=excluded.atualizado_em""",
                        (r["Chave"],r["Seguimento"],depois["valor_primeira"],depois["valor_adicional"],versao,agora))
            mudancas.append({"chave":r["Chave"],"servico":r["Seguimento"],"situacao":r["Situação"],"antes":antes,"depois":depois})
        # Serviços ausentes do novo arquivo permanecem ativos e não são excluídos.
        con.execute("""INSERT INTO tarifas_auditoria
          (ocorrido_em,usuario,arquivo,arquivo_hash,versao,backup,detalhes_json)
          VALUES(?,?,?,?,?,?,?)""",
          (agora,usuario,nome_arquivo,sha,versao,str(backup or ""),
           json.dumps({"mudancas":mudancas,"linhas_importadas":len(df)},ensure_ascii=False)))
    return versao,sha,backup,df
