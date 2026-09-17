from __future__ import annotations
from datetime import datetime, time, timedelta
import pandas as pd
from .validacoes import normalizar_texto, canonicalizar_tipo_servico
from .calculos import minutos_trabalhados, horas_pagamento, calcular_valor
from .gestao import enriquecer_plantao
from .tabela_valores import BASE_HC, tarifa_oficial, TABELA_VERSAO
from .storage import caminho_banco
import sqlite3

ALIASES = {
    # TESTE1: priorizar o TÉCNICO final simplificado em relação ao campo técnico longo da exportação.
    'tecnico': ['técnico ', 'técnico', 'tecnico', 'técnico responsável', 'tecnico responsavel', 'prestador', 'nome técnico', 'nome tecnico'],
    # TESTE1: DEFEITO final = PORTÕES / CONTROLE DE ACESSO etc.
    'tipo_os': ['defeito ', 'defeito', 'tipo os', 'tipo de os', 'tipo', 'segmento'],
    # TESTE1: Fechamento é a melhor data disponível no relatório para o atendimento concluído.
    'data': ['data execução', 'data execucao', 'data da execução', 'data da execucao', 'data atendimento', 'fechamento', 'data'],
    # O arquivo real contém o erro de digitação "HORA INCIO".
    'inicio': ['hora incio', 'hora início', 'hora inicio', 'início', 'inicio', 'hora inicial', 'horário inicial', 'horario inicial'],
    'fim': ['hora fim', 'término', 'termino', 'hora final', 'horário final', 'horario final', 'hora termino'],
    # TESTE1: SERVIÇO (ex. 3016 - MANUTENÇÃO SISTEMAS) é usado como centro de custo/serviço.
    'centro_custo': ['serviço', 'servico', 'centro de custo', 'centro custo', 'cc', 'c.c.'],
    'os': ['ordem', 'ordem de serviço', 'ordem de servico', 'chaves', 'ossigma', 'os sigma', 'os', 'nº os', 'n° os', 'numero os', 'número os'],
    'tempo_informado': ['tempo de atemdimento', 'tempo de atendimento', 'duração', 'duracao'],
    'cliente': ['cliente', 'fantasia'],
}


def _norm_col(s):
    return normalizar_texto(s).lower()


def _find_exact_preferred(df: pd.DataFrame, nomes):
    """Localiza colunas tolerando espaços, acentos, caixa e pequenas variações."""
    # 1) igualdade literal após strip
    for nome in nomes:
        for c in df.columns:
            if str(c).strip() == str(nome).strip():
                return c

    # 2) igualdade normalizada (remove acentos, espaços repetidos e ignora caixa)
    normalizadas = {c: _norm_col(c) for c in df.columns}
    for nome in nomes:
        alvo = _norm_col(nome)
        for c, norm in normalizadas.items():
            if norm == alvo:
                return c

    # 3) fallback conservador por conteúdo do cabeçalho. Evita falha por
    # caracteres invisíveis/variações de exportação, sem aceitar correspondências vagas.
    for nome in nomes:
        alvo = _norm_col(nome)
        if len(alvo) < 5:
            continue
        for c, norm in normalizadas.items():
            if alvo in norm or norm in alvo:
                return c
    return None


def mapear_colunas(df: pd.DataFrame):
    m = {}

    # Regras específicas do TESTE1: as colunas finais devem ter prioridade.
    teste1_pref = {
        'tecnico': ['TÉCNICO '],
        'tipo_os': ['DEFEITO'],
        'inicio': ['HORA INCIO '],
        'fim': ['HORA FIM'],
        'centro_custo': ['SERVIÇO'],
        'tempo_informado': ['TEMPO DE ATEMDIMENTO'],
        'data': ['Fechamento'],
        'os': ['Ordem', 'Chaves', 'OSSigma'],
        'cliente': ['Cliente'],
    }
    for alvo, nomes in teste1_pref.items():
        c = _find_exact_preferred(df, nomes)
        if c is not None:
            m[alvo] = c

    # Novo relatório Inside: 'Defeito' continua prioritário, mas pode vir vazio.
    # Mantém 'Defeito Informado' como fonte secundária explícita.
    c_fallback = _find_exact_preferred(df, ['Defeito Informado'])
    if c_fallback is not None:
        m['tipo_os_fallback'] = c_fallback

    # Completa o que não tiver sido encontrado pelas regras específicas.
    for alvo, aliases in ALIASES.items():
        if alvo in m:
            continue
        c = _find_exact_preferred(df, aliases)
        if c is not None:
            m[alvo] = c

    # FALLBACK ESTRUTURAL DO TESTE1 REAL.
    # O arquivo fornecido possui 38 colunas (A:AL) e o bloco operacional fica
    # em R/AG:AL. Esse fallback é deliberadamente restrito ao layout reconhecido
    # para não adivinhar colunas em relatórios genéricos.
    if df.shape[1] >= 38:
        cols = list(df.columns)
        norm36 = _norm_col(cols[36])
        norm37 = _norm_col(cols[37])
        parece_teste1 = ('defeito' in norm36 and 'tecnico' in norm37)
        if parece_teste1:
            fixos = {
                'cliente': 0,
                'os': 3,
                'data': 17,
                'inicio': 32,
                'fim': 33,
                'tempo_informado': 34,
                'centro_custo': 35,
                'tipo_os': 36,
                'tecnico': 37,
            }
            for alvo, idx in fixos.items():
                if idx < len(cols):
                    # No layout TESTE1 reconhecido, posição estrutural prevalece
                    # sobre aliases genéricos (ex.: evita 'SLA Fechamento' ser
                    # confundido com a data real 'Fechamento').
                    m[alvo] = cols[idx]
            # Inside novo: 'Ordem' é o identificador oficial da OS.
            # Planilhas antigas, que não possuem 'Ordem', continuam usando
            # o mapeamento legado da V10.2.
            ordem = _find_exact_preferred(df, ['Ordem'])
            if ordem is not None:
                m['os'] = ordem
    return m


def preparar_parametrizacao(df: pd.DataFrame) -> pd.DataFrame:
    p = df.copy()
    p.columns = [str(c).strip() for c in p.columns]
    rename = {}
    for c in p.columns:
        n = _norm_col(c)
        if n in ('tecnico','técnico'):
            rename[c] = 'tecnico'
        elif n in ('tipo os','tipo de os','defeito','tipo serviço','tipo servico','serviço','servico','segmento'):
            rename[c] = 'tipo_os'
        elif '1' in n and ('comercial' in n or 'hc' in n) and ('hora' in n) and 'fora' not in n:
            rename[c] = 'hc_primeira'
        elif ('adicional' in n or 'demais' in n) and ('comercial' in n or 'hc' in n) and 'fora' not in n:
            rename[c] = 'hc_adicional'
        elif '1' in n and 'fora' in n:
            rename[c] = 'fora_primeira'
        elif ('adicional' in n or 'demais' in n) and 'fora' in n:
            rename[c] = 'fora_adicional'
    p = p.rename(columns=rename)
    obrig = ['tecnico','tipo_os','hc_primeira','hc_adicional','fora_primeira','fora_adicional']
    falt = [c for c in obrig if c not in p.columns]
    if falt:
        raise ValueError('Parametrização sem colunas obrigatórias: ' + ', '.join(falt))
    p['tecnico_norm'] = p['tecnico'].map(normalizar_texto)
    p['tipo_os_norm'] = p['tipo_os'].map(canonicalizar_tipo_servico)
    return p


def _parse_hora(v):
    """Aceita texto HH:MM, datetime/time e fração de dia do Excel (ex.: 0.522916...)."""
    if pd.isna(v):
        raise ValueError('horário ausente')
    if hasattr(v, 'hour') and hasattr(v, 'minute'):
        try:
            return v.time() if hasattr(v, 'time') else v
        except Exception:
            pass
    if isinstance(v, (int, float)):
        total_seg = round(float(v) * 24 * 60 * 60) % (24 * 60 * 60)
        h = total_seg // 3600
        mi = (total_seg % 3600) // 60
        s = total_seg % 60
        return time(h, mi, s)
    return pd.to_datetime(str(v).strip(), errors='raise').time()


def processar(man: pd.DataFrame, param: pd.DataFrame, mapa: dict, hc_inicio=time(8,0), hc_fim=time(18,0), feriados=None, permitir_virada_dia=True):
    feriados = set(feriados or [])
    resultados, pendencias = [], []
    for idx, row in man.iterrows():
        base = {'linha_origem': int(idx)+2}  # +2 porque linha 1 contém cabeçalho no TESTE1
        try:
            vals = {k: row.get(v) if v else None for k,v in mapa.items()}
            # Se o campo Defeito vier vazio, usa Defeito Informado.
            if pd.isna(vals.get('tipo_os')) or str(vals.get('tipo_os')).strip() == '':
                fb = vals.get('tipo_os_fallback')
                if not (pd.isna(fb) or str(fb).strip() == ''):
                    vals['tipo_os'] = fb
            for campo in ['tecnico','tipo_os','data','inicio','fim','centro_custo']:
                if campo not in vals or pd.isna(vals[campo]) or str(vals[campo]).strip()=='':
                    raise ValueError(f'{campo} não informado')

            tecnico = str(vals['tecnico']).strip()
            tipo_raw = str(vals['tipo_os']).strip()
            tipo = canonicalizar_tipo_servico(tipo_raw)
            data = pd.to_datetime(vals['data'], dayfirst=True, errors='raise').date()
            h_ini = _parse_hora(vals['inicio'])
            h_fim = _parse_hora(vals['fim'])
            dt_ini = datetime.combine(data, h_ini)
            dt_fim = datetime.combine(data, h_fim)
            if permitir_virada_dia and h_fim < h_ini:
                dt_fim += timedelta(days=1)
            minutos = minutos_trabalhados(dt_ini, dt_fim)
            hp = horas_pagamento(minutos)

            os_val = vals.get('os','')

            # Um atendimento só é integralmente comercial quando começa e termina
            # no MESMO dia e todo o intervalo fica dentro da janela comercial.
            # Isso evita classificar incorretamente viradas de dia como 23:33 -> 00:50.
            mesmo_dia = dt_ini.date() == dt_fim.date()
            dia_util = dt_ini.weekday() < 5 and dt_ini.date() not in feriados
            dentro_janela = h_ini >= hc_inicio and h_fim <= hc_fim
            fora = not (mesmo_dia and dia_util and dentro_janela)
            regra = 'FORA DO HORÁRIO COMERCIAL' if fora else 'HORÁRIO COMERCIAL'

            # A tabela ativa é a fonte oficial do cálculo. A parametrização antiga
            # fica apenas como fallback para serviços legados que não existam no
            # cadastro atual. Isso elimina falsos 'não encontrada' e 'duplicada'
            # após o usuário escolher um serviço válido no editor.
            tarifa = tarifa_oficial(tecnico, tipo_raw, fora)
            if tarifa is not None:
                vp, va, _ = tarifa
            else:
                mask = (param['tecnico_norm'] == normalizar_texto(tecnico)) & (param['tipo_os_norm'] == canonicalizar_tipo_servico(tipo))
                matches = param.loc[mask]
                if len(matches) > 1:
                    raise ValueError('parametrização duplicada')
                if len(matches) == 1:
                    pr = matches.iloc[0]
                    vp = pr['fora_primeira'] if fora else pr['hc_primeira']
                    va = pr['fora_adicional'] if fora else pr['hc_adicional']
                else:
                    raise ValueError('parametrização não encontrada')
            total = calcular_valor(hp, vp, va)

            resultados.append({
                **base,
                'OS': '' if pd.isna(os_val) else os_val,
                'Cliente': '' if pd.isna(vals.get('cliente')) else vals.get('cliente',''),
                'Técnico': tecnico,
                'Tipo OS': tipo,
                'Data': data,
                'Início': h_ini.strftime('%H:%M:%S'),
                'Término': h_fim.strftime('%H:%M:%S'),
                'Tempo minutos': minutos,
                'Horas Pagas': hp,
                'Regra': regra,
                'Valor 1ª Hora': float(str(vp).replace('R$','').replace('.','').replace(',','.')) if isinstance(vp,str) else vp,
                'Valor Hora Adicional': float(str(va).replace('R$','').replace('.','').replace(',','.')) if isinstance(va,str) else va,
                'Valor Total': float(total),
                'Centro de Custo': vals['centro_custo'],
                'Tabela Valores': TABELA_VERSAO,
                'Status': 'PROCESSADO'
            })
        except Exception as e:
            pendencias.append({
                **base,
                'OS': row.get(mapa.get('os',''), ''),
                'Cliente': row.get(mapa.get('cliente',''), ''),
                'Técnico': row.get(mapa.get('tecnico',''), ''),
                'Tipo OS': row.get(mapa.get('tipo_os',''), ''),
                'Centro de Custo': row.get(mapa.get('centro_custo',''), ''),
                'Motivo': str(e),
                'Status': 'PENDENTE'
            })
    det = pd.DataFrame(resultados)
    if len(det):
        det = enriquecer_plantao(det).drop(columns=['_dt_inicio','_dt_fim'])
        # V10.2: duplicidade é definida por Nº OS + Cliente. A primeira ocorrência
        # permanece válida; as seguintes são preservadas para auditoria, porém sem valor.
        def _chave_os(v):
            x = normalizar_texto(v)
            if x.endswith('.0') and x[:-2].isdigit(): x = x[:-2]
            return x
        det['_dup_os'] = det['OS'].map(_chave_os)
        det['_dup_cliente'] = det['Cliente'].map(normalizar_texto)
        mask_valida = det['_dup_os'].ne('') & det['_dup_cliente'].ne('')
        dup = mask_valida & det.duplicated(['_dup_os','_dup_cliente'], keep='first')
        det['Tipo Original'] = det['Tipo OS']
        det['Tipo Pagamento'] = det['Tipo OS']
        det['Valor Mão de Obra'] = det['Valor Total'].astype(float)
        det['Quilometragem'] = 0.0
        det['Pedágio'] = 0.0
        det['Outros Ajustes'] = 0.0
        det['Justificativa Ajuste'] = ''
        det['Origem do Valor'] = 'AUTOMÁTICO'
        det.loc[dup, 'Valor Mão de Obra'] = 0.0
        det.loc[dup, 'Valor Total'] = 0.0
        det.loc[dup, 'Status'] = 'DUPLICADA E SEM VALOR'
        det.loc[dup, 'Origem do Valor'] = 'DUPLICADA E SEM VALOR'
        det = det.drop(columns=['_dup_os','_dup_cliente'])
    return det, pd.DataFrame(pendencias)


def criar_parametrizacao_padrao(tecnicos) -> pd.DataFrame:
    """Cria parametrização usando exclusivamente a tabela oficial vigente."""
    tecnicos_limpos = sorted({
        str(t).strip() for t in tecnicos
        if str(t).strip() and str(t).lower() != 'nan'
    })
    tipos = list(BASE_HC.keys()) + ['PORTAO']
    try:
        db=caminho_banco()
        if db.exists():
            with sqlite3.connect(db) as con:
                extras=[r[0] for r in con.execute("SELECT descricao FROM tarifas WHERE ativo=1 AND chave LIKE 'SERVICO::%'")]
            tipos += [x for x in extras if x not in tipos]
    except Exception:
        pass
    linhas = []
    for tecnico in tecnicos_limpos:
        for tipo in tipos:
            hc = tarifa_oficial(tecnico, tipo, fora_horario=False)
            fora = tarifa_oficial(tecnico, tipo, fora_horario=True)
            if hc is None or fora is None:
                continue
            linhas.append({
                'tecnico': tecnico,
                'tipo_os': tipo,
                'hc_primeira': hc[0],
                'hc_adicional': hc[1],
                'fora_primeira': fora[0],
                'fora_adicional': fora[1],
                'origem_regra': 'TABELA OFICIAL VALOR_MANUTENCAO — 15/09/2026',
            })
    return preparar_parametrizacao(pd.DataFrame(linhas))


def parece_relatorio_em_vez_de_parametrizacao(df: pd.DataFrame) -> bool:
    cols = {normalizar_texto(c) for c in df.columns}
    marcadores = {'HORA INCIO', 'HORA FIM', 'TEMPO DE ATEMDIMENTO', 'SERVICO', 'DEFEITO', 'TECNICO'}
    return len(cols.intersection(marcadores)) >= 4
