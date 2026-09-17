from __future__ import annotations

import math
import pandas as pd

from .calculos import calcular_valor
from .tabela_valores import tarifa_oficial


def _num(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        return float(v)
    except Exception:
        return None


def executar_conferencias(det: pd.DataFrame, pend: pd.DataFrame, total_linhas_operacionais: int) -> dict:
    """Executa conferências independentes antes de permitir aprovação.

    Retorna um dicionário com checks, alertas, totais e flag ``aprovavel``.
    Checks críticos bloqueiam aprovação; alertas servem para revisão humana.
    """
    checks = []
    alertas = []

    processadas = len(det)
    pendencias = len(pend)
    total_contabilizado = processadas + pendencias
    checks.append({
        'nome': 'Reconciliação de linhas',
        'ok': total_contabilizado == int(total_linhas_operacionais),
        'detalhe': f'{total_linhas_operacionais} linhas operacionais = {processadas} processadas + {pendencias} pendências',
    })

    if pendencias:
        checks.append({
            'nome': 'Pendências zeradas',
            'ok': False,
            'detalhe': f'Existem {pendencias} ocorrência(s) pendente(s).',
        })
    else:
        checks.append({'nome': 'Pendências zeradas', 'ok': True, 'detalhe': 'Nenhuma pendência encontrada.'})

    erros_numericos = []
    erros_recalculo = []
    if len(det):
        for i, row in det.iterrows():
            linha = row.get('linha_origem', i + 2)
            hp = _num(row.get('Horas Pagas'))
            v1 = _num(row.get('Valor 1ª Hora'))
            va = _num(row.get('Valor Hora Adicional'))
            vt = _num(row.get('Valor Total'))
            mins = _num(row.get('Tempo minutos'))
            nums = {'Horas Pagas': hp, 'Valor 1ª Hora': v1, 'Valor Hora Adicional': va, 'Valor Total': vt, 'Tempo minutos': mins}
            invalidos = [k for k, v in nums.items() if v is None or not math.isfinite(v) or v < 0]
            if invalidos:
                erros_numericos.append(f'linha {linha}: {", ".join(invalidos)}')
                continue
            esperado = float(calcular_valor(int(hp), v1, va))
            if abs(esperado - vt) > 0.005:
                erros_recalculo.append(f'linha {linha}: calculado {vt:.2f}, esperado {esperado:.2f}')

        checks.append({
            'nome': 'Integridade numérica',
            'ok': not erros_numericos,
            'detalhe': 'Todos os valores e tempos são numéricos e não negativos.' if not erros_numericos else '; '.join(erros_numericos[:5]),
        })
        checks.append({
            'nome': 'Recálculo independente das OS',
            'ok': not erros_recalculo,
            'detalhe': 'O total de cada OS confere com horas × parametrização.' if not erros_recalculo else '; '.join(erros_recalculo[:5]),
        })

        # Segunda camada independente: não basta a multiplicação estar correta.
        # A tarifa aplicada também precisa coincidir com a tabela oficial vigente.
        erros_tarifa = []
        for i, row in det.iterrows():
            linha = row.get('linha_origem', i + 2)
            fora = str(row.get('Regra', '')).strip().upper().startswith('FORA')
            oficial = tarifa_oficial(row.get('Técnico', ''), row.get('Tipo OS', ''), fora_horario=fora)
            if oficial is None:
                erros_tarifa.append(f'linha {linha}: tipo de serviço sem tarifa oficial')
                continue
            esp1, espa, descricao = oficial
            v1 = _num(row.get('Valor 1ª Hora'))
            va = _num(row.get('Valor Hora Adicional'))
            if v1 is None or va is None or abs(v1-esp1) > 0.005 or abs(va-espa) > 0.005:
                erros_tarifa.append(
                    f'linha {linha}: {descricao}; aplicado R$ {v1 or 0:.2f}/R$ {va or 0:.2f}, '
                    f'esperado R$ {esp1:.2f}/R$ {espa:.2f}'
                )
        checks.append({
            'nome': 'Tarifa × tabela oficial',
            'ok': not erros_tarifa,
            'detalhe': 'Todas as OS usam a tarifa oficial correta para serviço, técnico e horário.'
                       if not erros_tarifa else '; '.join(erros_tarifa[:5]),
        })

        total_detalhe = float(pd.to_numeric(det['Valor Total'], errors='coerce').sum())
        total_tecnicos = float(det.groupby('Técnico')['Valor Total'].sum().sum())
        checks.append({
            'nome': 'Conciliação do total',
            'ok': abs(total_detalhe - total_tecnicos) <= 0.005,
            'detalhe': f'Detalhamento R$ {total_detalhe:.2f} × consolidação por técnico R$ {total_tecnicos:.2f}',
        })

        # Alertas gerenciais: não bloqueiam automaticamente, mas exigem atenção visual.
        longos = det[pd.to_numeric(det['Tempo minutos'], errors='coerce') > 8 * 60]
        if len(longos):
            alertas.append(f'{len(longos)} atendimento(s) com duração superior a 8 horas. Revisar antes da aprovação.')

        os_vazias = det['OS'].isna() | (det['OS'].astype(str).str.strip() == '') if 'OS' in det.columns else pd.Series([], dtype=bool)
        if len(os_vazias) and int(os_vazias.sum()):
            alertas.append(f'{int(os_vazias.sum())} atendimento(s) sem identificador de OS. O cálculo foi mantido, mas recomenda-se conferência.')
    else:
        checks.extend([
            {'nome': 'Integridade numérica', 'ok': False, 'detalhe': 'Nenhuma OS foi processada.'},
            {'nome': 'Recálculo independente das OS', 'ok': False, 'detalhe': 'Nenhuma OS foi processada.'},
            {'nome': 'Tarifa × tabela oficial', 'ok': False, 'detalhe': 'Nenhuma OS foi processada.'},
            {'nome': 'Conciliação do total', 'ok': False, 'detalhe': 'Nenhuma OS foi processada.'},
        ])
        total_detalhe = 0.0

    aprovavel = bool(checks) and all(c['ok'] for c in checks)
    return {
        'checks': checks,
        'alertas': alertas,
        'aprovavel': aprovavel,
        'total': round(total_detalhe, 2),
        'processadas': processadas,
        'pendencias': pendencias,
        'linhas_operacionais': int(total_linhas_operacionais),
    }
