from __future__ import annotations
import re
import unicodedata
import pandas as pd


def normalizar_texto(v):
    if pd.isna(v):
        return ''
    s = str(v).strip().upper()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    s = re.sub(r'\s+', ' ', s)
    return s


def canonicalizar_tipo_servico(v):
    """Normaliza descrições do Inside somente para segmentos da tabela oficial."""
    s = normalizar_texto(v)
    aliases = {
        'PORTOES':'PORTAO','PORTAO':'PORTAO',
        'CONTROLE ACESSO':'CONTROLE DE ACESSO','CONTROLE DE ACESSO':'CONTROLE DE ACESSO',
        'CFTV ANALOGICO':'CFTV ANALOGICO','CFTV IP':'CFTV IP',
        'ALARME':'ALARME','CERCA ELETRICA':'CERCA ELETRICA',
        'TELECOMUNICACAO':'TELECOMUNICACAO','INFORMATICA':'INFORMATICA',
    }
    if s in aliases: return aliases[s]
    if 'MAN' in s and 'TORRE' in s and 'PRO' in s: return 'MAN_TORRE_PRO'
    if 'PORTOES' in s or re.search(r'\bPORTAO\b', s): return 'PORTAO'
    if 'CONTROLE DE ACESSO' in s or 'CONTROLE ACESSO' in s: return 'CONTROLE DE ACESSO'
    if 'CFTV IP' in s: return 'CFTV IP'
    if re.search(r'\bCFTV\b', s): return 'CFTV ANALOGICO'
    if 'CERCA ELETRICA' in s: return 'CERCA ELETRICA'
    if re.search(r'\bALARME\b', s): return 'ALARME'
    if 'TELECOMUNIC' in s: return 'TELECOMUNICACAO'
    if 'INFORMATICA' in s: return 'INFORMATICA'
    return s


def validar_campos_obrigatorios(row, campos):
    erros = []
    for campo in campos:
        v = row.get(campo)
        if pd.isna(v) or str(v).strip() == '':
            erros.append(f'{campo} não informado')
    return erros
