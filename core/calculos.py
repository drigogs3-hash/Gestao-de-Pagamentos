from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP
import math

MONEY = Decimal('0.01')


def to_decimal(value) -> Decimal:
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    s = str(value).strip().replace('R$', '').replace(' ', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    return Decimal(s)


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def minutos_trabalhados(inicio: datetime, fim: datetime) -> int:
    diff = int((fim - inicio).total_seconds() // 60)
    if diff <= 0:
        raise ValueError('Horário final deve ser posterior ao inicial.')
    return diff


def horas_pagamento(minutos: int) -> int:
    """Regra: 1a hora sempre; nova hora somente após N horas + 15 min.
    Exemplos: 75 -> 1, 76 -> 2, 135 -> 2, 136 -> 3.
    """
    if minutos <= 0:
        raise ValueError('Tempo trabalhado deve ser maior que zero.')
    if minutos <= 75:
        return 1
    return 1 + math.ceil((minutos - 75) / 60)


def calcular_valor(horas: int, valor_primeira_hora, valor_adicional) -> Decimal:
    if horas < 1:
        raise ValueError('Horas pagas deve ser >= 1.')
    primeira = to_decimal(valor_primeira_hora)
    adicional = to_decimal(valor_adicional)
    total = primeira + Decimal(max(horas - 1, 0)) * adicional
    return money(total)


def em_horario_comercial(hora_inicio: time, hora_fim: time, hc_inicio: time, hc_fim: time) -> bool:
    return hora_inicio >= hc_inicio and hora_fim <= hc_fim


@dataclass
class ResultadoCalculo:
    minutos: int
    horas_pagas: int
    valor_total: Decimal
