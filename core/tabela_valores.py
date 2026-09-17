from __future__ import annotations

from .validacoes import normalizar_texto, canonicalizar_tipo_servico
from .storage import caminho_banco
import sqlite3

TABELA_VERSAO = "15/09/2026"

# Tabela oficial recebida em 15/09/2026.
# PORTÃO em horário comercial:
#   Alexandre/Rubens -> 200,00 + 90,00 adicional
#   qualquer outro técnico -> 127,20 + 53,00 adicional
# PORTÃO fora do horário para Alexandre/Rubens -> 290,00 + 100,00 adicional
# Demais serviços fora do horário -> 159,00 + 53,00 adicional.
#
# A planilha também contém duas linhas de TELECOMUNICAÇÃO (127,20/53 e 200/90)
# sem explicitar, na própria linha, o critério de seleção. Mantém-se o critério
# funcional já existente: Alexandre/Rubens/Erinaldo usam 200/90 em horário
# comercial; os demais usam 127,20/53.

BASE_HC = {
    'ALARME': (90.10, 53.00),
    'CFTV ANALOGICO': (90.10, 53.00),
    'CFTV IP': (127.20, 53.00),
    'CONTROLE DE ACESSO': (127.20, 53.00),
    'CERCA ELETRICA': (127.20, 53.00),
    'TELECOMUNICACAO': (127.20, 53.00),
    'INFORMATICA': (127.20, 53.00),
    'MAN_TORRE_PRO': (127.20, 53.00),
}
TELECOM_ESPECIAIS = ('ALEXANDRE', 'RUBENS', 'ERINALDO')
PORTAO_ESPECIAIS_HC = ('ALEXANDRE', 'RUBENS')

def _tecnico_em_grupo(tecnico, grupo):
    tn = normalizar_texto(tecnico)
    return any(nome in tn for nome in grupo)

def _tarifa_banco(chave, fallback):
    try:
        db=caminho_banco()
        if db.exists():
            with sqlite3.connect(db) as con:
                row=con.execute('SELECT valor_primeira,valor_adicional FROM tarifas WHERE chave=? AND ativo=1',(chave,)).fetchone()
                if row: return float(row[0]),float(row[1])
    except Exception:
        pass
    return fallback

def tarifa_oficial(tecnico, tipo_os, fora_horario=False):
    """Retorna (1ª hora, adicional, descrição) ou None para tipo não tabelado.

    Prioridade: regra especial -> descrição exata cadastrada -> regra-base.
    Isso preserva os serviços (MAN) escolhidos na grade, sem reduzi-los
    indevidamente a uma família genérica durante o recálculo.
    """
    tipo_raw = '' if tipo_os is None else str(tipo_os).strip()
    tipo_norm = normalizar_texto(tipo_raw)
    tipo = canonicalizar_tipo_servico(tipo_raw)

    # Exceção oficial — ERINALDO em quatro serviços de Telecomunicação.
    # Demais técnicos permanecem com a tarifa cadastrada de 127,20 + 53,00.
    telecom_erinaldo = {
        'HOMETY TELECOMUNICACAO',
        'LETMEIN TELECOMUNICACAO',
        'TELECOMUNICACOES',
        'VISITA AVULSA TELECOMUNICACAO',
    }
    tipo_sem_man = tipo_norm
    if tipo_sem_man.startswith('(MAN) '):
        tipo_sem_man = tipo_sem_man[6:].strip()
    elif tipo_sem_man.startswith('MAN '):
        tipo_sem_man = tipo_sem_man[4:].strip()
    if _tecnico_em_grupo(tecnico, ('ERINALDO',)) and tipo_sem_man in telecom_erinaldo:
        if fora_horario:
            # Mantém a regra geral de fora do horário para serviços não-portão.
            v1,va=_tarifa_banco('FORA_DEMAIS',(159.00,53.00))
            return v1,va,'FORA DO HORÁRIO — SERVIÇOS EXCETO PORTÃO'
        return 200.00,90.00,'TELECOMUNICAÇÃO HC — ERINALDO'

    if tipo == 'PORTAO':
        if fora_horario and _tecnico_em_grupo(tecnico, PORTAO_ESPECIAIS_HC):
            return 290.00,100.00,'PORTÃO FORA — ALEXANDRE/RUBENS'
        if fora_horario:
            v1,va=_tarifa_banco('PORTAO_FORA',(290.00,90.00)); return v1,va,'PORTÃO — FORA DO HORÁRIO COMERCIAL'
        if _tecnico_em_grupo(tecnico, PORTAO_ESPECIAIS_HC):
            return 200.00,90.00,'PORTÃO HC — ALEXANDRE/RUBENS'
        v1,va=_tarifa_banco('PORTAO_DEMAIS_HC',(127.20,53.00)); return v1,va,'PORTÃO HC — DEMAIS TÉCNICOS'

    # Serviço escolhido na grade: procurar primeiro a descrição EXATA na tabela
    # ativa. Isso inclui tanto SERVICO:: quanto chaves conhecidas como
    # MAN_MO_VALOR_FECHADO. Não depende da parametrização antiga em memória.
    try:
        db=caminho_banco()
        if db.exists() and tipo_norm:
            with sqlite3.connect(db) as con:
                rows=con.execute("SELECT chave,descricao,valor_primeira,valor_adicional FROM tarifas WHERE ativo=1").fetchall()
            for chave,descricao,v1,va in rows:
                if normalizar_texto(descricao)==tipo_norm:
                    if fora_horario:
                        f1,fa=_tarifa_banco('FORA_DEMAIS',(159.00,53.00))
                        return f1,fa,'FORA DO HORÁRIO — SERVIÇOS EXCETO PORTÃO'
                    return float(v1),float(va),f'{descricao} — HORÁRIO COMERCIAL'
    except Exception:
        pass

    if tipo not in BASE_HC:
        # Serviço criado posteriormente pela importação da tabela.
        try:
            db=caminho_banco()
            if db.exists():
                with sqlite3.connect(db) as con:
                    rows=con.execute("SELECT chave,descricao,valor_primeira,valor_adicional FROM tarifas WHERE ativo=1").fetchall()
                alvo=normalizar_texto(tipo_os)
                for chave,descricao,v1,va in rows:
                    if chave.startswith("SERVICO::") and normalizar_texto(descricao)==alvo:
                        if fora_horario:
                            f1,fa=_tarifa_banco('FORA_DEMAIS',(159.00,53.00))
                            return f1,fa,'FORA DO HORÁRIO — SERVIÇOS EXCETO PORTÃO'
                        return float(v1),float(va),f'{descricao} — HORÁRIO COMERCIAL'
        except Exception:
            pass
        return None

    if fora_horario:
        v1,va=_tarifa_banco('FORA_DEMAIS',(159.00,53.00)); return v1,va,'FORA DO HORÁRIO — SERVIÇOS EXCETO PORTÃO'

    if tipo == 'TELECOMUNICACAO' and _tecnico_em_grupo(tecnico, TELECOM_ESPECIAIS):
        v1,va=_tarifa_banco('TELECOM_ESPECIAL_HC',(200.00,90.00)); return v1,va,'TELECOMUNICAÇÃO HC — REGRA ESPECIAL'

    v1, va = _tarifa_banco(tipo, BASE_HC[tipo])
    return v1, va, f'{tipo} — HORÁRIO COMERCIAL'
