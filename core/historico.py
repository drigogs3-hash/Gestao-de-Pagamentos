from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

from .storage import caminho_banco, criar_backup_banco, salvar_arquivo_original
from .integridade import TABELA_VERSAO, hash_dataframe, checklist_integridade

DB_PATH = caminho_banco()


def conectar(db_path: str | Path | None = None):
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def inicializar_banco(db_path=None):
    with conectar(db_path) as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS apuracoes (
            id TEXT PRIMARY KEY,
            criado_em TEXT NOT NULL,
            competencia TEXT,
            arquivo_origem TEXT,
            arquivo_salvo TEXT,
            status TEXT NOT NULL,
            total REAL NOT NULL,
            os_processadas INTEGER NOT NULL,
            pendencias INTEGER NOT NULL,
            tecnicos INTEGER NOT NULL,
            aprovavel INTEGER NOT NULL,
            alertas_json TEXT,
            checks_json TEXT,
            aprovado_por TEXT,
            aprovado_em TEXT
        );
        CREATE TABLE IF NOT EXISTS detalhes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apuracao_id TEXT NOT NULL,
            linha_origem INTEGER,
            os TEXT,
            cliente TEXT,
            tecnico TEXT,
            tipo_os TEXT,
            data TEXT,
            inicio TEXT,
            termino TEXT,
            tempo_minutos REAL,
            horas_pagas REAL,
            regra TEXT,
            valor_primeira REAL,
            valor_adicional REAL,
            valor_total REAL,
            centro_custo TEXT,
            plantao_fds INTEGER DEFAULT 0,
            faixa_plantao TEXT,
            fim_de_semana TEXT,
            status TEXT,
            FOREIGN KEY(apuracao_id) REFERENCES apuracoes(id)
        );
        CREATE TABLE IF NOT EXISTS pendencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apuracao_id TEXT NOT NULL,
            linha_origem INTEGER,
            os TEXT,
            cliente TEXT,
            tecnico TEXT,
            tipo_os TEXT,
            centro_custo TEXT,
            motivo TEXT,
            status TEXT,
            FOREIGN KEY(apuracao_id) REFERENCES apuracoes(id)
        );
        ''')
        cols_det = {r['name'] for r in con.execute('PRAGMA table_info(detalhes)').fetchall()}
        for nome, ddl in [('plantao_fds','INTEGER DEFAULT 0'), ('faixa_plantao','TEXT'), ('fim_de_semana','TEXT')]:
            if nome not in cols_det:
                con.execute(f'ALTER TABLE detalhes ADD COLUMN {nome} {ddl}')
        cols_det = {r['name'] for r in con.execute('PRAGMA table_info(detalhes)').fetchall()}
        novos_det = [('tipo_original','TEXT'),('tipo_pagamento','TEXT'),('valor_mao_obra','REAL DEFAULT 0'),('quilometragem','REAL DEFAULT 0'),('pedagio','REAL DEFAULT 0'),('outros_ajustes','REAL DEFAULT 0'),('justificativa_ajuste','TEXT'),('origem_valor','TEXT DEFAULT "AUTOMÁTICO"')]
        for nome, ddl in novos_det:
            if nome not in cols_det: con.execute(f'ALTER TABLE detalhes ADD COLUMN {nome} {ddl}')
        cols_ap = {r['name'] for r in con.execute('PRAGMA table_info(apuracoes)').fetchall()}
        if 'arquivo_salvo' not in cols_ap:
            con.execute('ALTER TABLE apuracoes ADD COLUMN arquivo_salvo TEXT')
        if 'tabela_versao' not in cols_ap:
            con.execute('ALTER TABLE apuracoes ADD COLUMN tabela_versao TEXT')
        if 'dados_hash' not in cols_ap:
            con.execute('ALTER TABLE apuracoes ADD COLUMN dados_hash TEXT')
        con.execute('''CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apuracao_id TEXT,
            evento TEXT NOT NULL,
            usuario TEXT,
            ocorrido_em TEXT NOT NULL,
            tabela_versao TEXT,
            dados_hash TEXT,
            detalhes_json TEXT
        )''')

        con.execute('''CREATE TABLE IF NOT EXISTS tarifas (
            chave TEXT PRIMARY KEY,
            descricao TEXT NOT NULL,
            valor_primeira REAL NOT NULL,
            valor_adicional REAL NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            versao TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )''')
        agora_tarifa=datetime.now().isoformat(timespec='seconds')
        tarifas_v108=[
          ('ALARME','ALARME',90.10,53.00),('CFTV ANALOGICO','CFTV ANALOGICO',90.10,53.00),
          ('CFTV IP','CFTV IP',127.20,53.00),('CONTROLE DE ACESSO','CONTROLE ACESSO',127.20,53.00),
          ('CERCA ELETRICA','CERCA ELETRICA',127.20,53.00),('TELECOMUNICACAO','TELECOMUNICAÇÃO',127.20,53.00),
          ('INFORMATICA','INFORMATICA',127.20,53.00),('PORTAO_ESPECIAL_HC','PORTÃO',200.00,90.00),
          ('PORTAO_FORA','PORTÃO (FORA DO HORARIO COMERCIAL)',290.00,90.00),
          ('TELECOM_ESPECIAL_HC','TELECOMUNICAÇÃO — REGRA ESPECIAL',200.00,90.00),
          ('FORA_DEMAIS','FORA DO HORARIO (TODOS OS SERVIÇOS EXCETO PORTAO)',159.00,53.00),
          ('MAN_MO_VALOR_FECHADO','(MAN) M.O VALOR FECHADO',0.00,0.00),
          ('PORTAO_DEMAIS_HC','PORTÃO (NO HORARIO COMERCIAL) — DEMAIS TÉCNICOS',127.20,53.00),
          ('MAN_TORRE_PRO','(MAN) (TORRE) PRO',127.20,53.00)
        ]
        qtd_tarifas=con.execute('SELECT COUNT(*) FROM tarifas').fetchone()[0]
        if qtd_tarifas==0:
            for chave,descricao,v1,va in tarifas_v108:
                con.execute('''INSERT INTO tarifas(chave,descricao,valor_primeira,valor_adicional,ativo,versao,atualizado_em)
                               VALUES(?,?,?,?,1,?,?)''',
                            (chave,descricao,v1,va,'15/09/2026-V2',agora_tarifa))

        # V11.12 — autorreparo do cadastro em instalações permanentes antigas.
        # Versões anteriores só faziam o seed quando a tabela inteira estava vazia.
        # Assim, um banco já existente podia nunca receber os novos serviços (MAN),
        # mesmo que eles estivessem na tabela oficial distribuída com o sistema.
        # Aqui inserimos SOMENTE serviços ausentes; valores já existentes no banco
        # são preservados e continuam sob controle do cadastro/auditoria do usuário.
        try:
            # Só migra automaticamente o banco permanente real. Bancos passados
            # explicitamente (testes/homologação) continuam isolados.
            if db_path is not None:
                raise RuntimeError('autorreparo desativado para banco explícito')
            from .tarifas_importacao import ler_tabela_tarifas
            ref = Path(__file__).resolve().parent.parent / 'referencias' / 'VALOR_MANUTENCAO_OFICIAL.xlsx'
            if ref.exists():
                tabela_ref, erros_ref = ler_tabela_tarifas(ref.read_bytes())
                if not erros_ref:
                    for _, tr in tabela_ref.iterrows():
                        con.execute('''INSERT OR IGNORE INTO tarifas
                            (chave,descricao,valor_primeira,valor_adicional,ativo,versao,atualizado_em)
                            VALUES(?,?,?,?,1,?,?)''',
                            (str(tr['Chave']), str(tr['Seguimento']), float(tr['Valor 1ª Hora']),
                             float(tr['Valor Hora Adicional']), '15/09/2026-V11.12-AUTOREPARO', agora_tarifa))
        except Exception:
            # A inicialização do histórico nunca deve ser impedida por uma referência
            # externa danificada; a tela Cadastros continua disponível para correção.
            pass
        con.execute('''CREATE TABLE IF NOT EXISTS tarifas_auditoria(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ocorrido_em TEXT NOT NULL, usuario TEXT, arquivo TEXT,
            arquivo_hash TEXT, versao TEXT, backup TEXT, detalhes_json TEXT
        )''')


def salvar_apuracao(det: pd.DataFrame, pend: pd.DataFrame, conferencia: dict, arquivo_origem='', competencia='', db_path=None, arquivo_original_bytes: bytes | None = None) -> str:
    inicializar_banco(db_path)
    ap_id = str(uuid.uuid4())
    status = 'EM REVISÃO' if conferencia.get('aprovavel') else 'BLOQUEADA'
    agora = datetime.now().isoformat(timespec='microseconds')
    arquivo_salvo = ''
    if db_path is None and arquivo_original_bytes:
        arquivo_salvo = salvar_arquivo_original(ap_id, arquivo_origem, arquivo_original_bytes)
    with conectar(db_path) as con:
        con.execute('''INSERT INTO apuracoes
            (id, criado_em, competencia, arquivo_origem, arquivo_salvo, status, total, os_processadas, pendencias, tecnicos, aprovavel, alertas_json, checks_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            ap_id, agora, competencia, arquivo_origem, arquivo_salvo, status, float(conferencia.get('total', 0)),
            int(len(det)), int(len(pend)), int(det['Técnico'].nunique() if len(det) and 'Técnico' in det else 0),
            int(bool(conferencia.get('aprovavel'))), json.dumps(conferencia.get('alertas', []), ensure_ascii=False),
            json.dumps(conferencia.get('checks', []), ensure_ascii=False),
        ))
        for _, r in det.iterrows():
            data = r.get('Data', '')
            if hasattr(data, 'isoformat'):
                data = data.isoformat()
            con.execute('''INSERT INTO detalhes
                (apuracao_id, linha_origem, os, cliente, tecnico, tipo_os, data, inicio, termino, tempo_minutos, horas_pagas, regra, valor_primeira, valor_adicional, valor_total, centro_custo, plantao_fds, faixa_plantao, fim_de_semana, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                ap_id, int(r.get('linha_origem', 0)), str(r.get('OS', '')), str(r.get('Cliente', '')), str(r.get('Técnico', '')),
                str(r.get('Tipo OS', '')), str(data), str(r.get('Início', '')), str(r.get('Término', '')),
                float(r.get('Tempo minutos', 0)), float(r.get('Horas Pagas', 0)), str(r.get('Regra', '')),
                float(r.get('Valor 1ª Hora', 0)), float(r.get('Valor Hora Adicional', 0)), float(r.get('Valor Total', 0)),
                str(r.get('Centro de Custo', '')), int(bool(r.get('Plantão FDS', False))), str(r.get('Faixa Plantão', '')), str(r.get('Fim de Semana', '')), str(r.get('Status', 'PROCESSADO')),
            ))
        # Persiste os campos complementares criados pelo sistema (não existem no Excel de origem).
        for _, r in det.iterrows():
            con.execute('''UPDATE detalhes SET tipo_original=?, tipo_pagamento=?, valor_mao_obra=?, quilometragem=?, pedagio=?, outros_ajustes=?, justificativa_ajuste=?, origem_valor=? WHERE apuracao_id=? AND linha_origem=?''', (
                str(r.get('Tipo Original',r.get('Tipo OS',''))), str(r.get('Tipo Pagamento',r.get('Tipo OS',''))), float(r.get('Valor Mão de Obra',r.get('Valor Total',0)) or 0), float(r.get('Quilometragem',0) or 0), float(r.get('Pedágio',0) or 0), float(r.get('Outros Ajustes',0) or 0), str(r.get('Justificativa Ajuste','')), str(r.get('Origem do Valor','AUTOMÁTICO')), ap_id, int(r.get('linha_origem',0))))
        for _, r in pend.iterrows():
            con.execute('''INSERT INTO pendencias
                (apuracao_id, linha_origem, os, cliente, tecnico, tipo_os, centro_custo, motivo, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                ap_id, int(r.get('linha_origem', 0)), str(r.get('OS', '')), str(r.get('Cliente', '')), str(r.get('Técnico', '')),
                str(r.get('Tipo OS', '')), str(r.get('Centro de Custo', '')), str(r.get('Motivo', '')), str(r.get('Status', 'PENDENTE')),
            ))
        dados_hash = hash_dataframe(det)
        con.execute('UPDATE apuracoes SET tabela_versao=?, dados_hash=? WHERE id=?',
                    (TABELA_VERSAO, dados_hash, ap_id))
        con.execute('''INSERT INTO auditoria
            (apuracao_id, evento, usuario, ocorrido_em, tabela_versao, dados_hash, detalhes_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (ap_id, 'APURACAO_CRIADA', '', datetime.now().isoformat(timespec='seconds'),
             TABELA_VERSAO, dados_hash, json.dumps({'arquivo_origem':arquivo_origem,'competencia':competencia}, ensure_ascii=False)))
    return ap_id


def validar_aprovacao_persistida(apuracao_id: str, db_path=None):
    """Executa o mesmo checklist da aprovação sobre o snapshot persistido."""
    inicializar_banco(db_path)
    with conectar(db_path) as con:
        atual = pd.read_sql_query('SELECT * FROM detalhes WHERE apuracao_id=?', con, params=[apuracao_id])
        atual = atual.rename(columns={
            'linha_origem':'linha_origem','os':'OS','cliente':'Cliente','tecnico':'Técnico',
            'tipo_os':'Tipo OS','data':'Data','inicio':'Início','termino':'Término',
            'tempo_minutos':'Tempo minutos','horas_pagas':'Horas Pagas','regra':'Regra',
            'valor_primeira':'Valor 1ª Hora','valor_adicional':'Valor Hora Adicional',
            'valor_total':'Valor Total','centro_custo':'Centro de Custo','tipo_original':'Tipo Original',
            'tipo_pagamento':'Tipo Pagamento','valor_mao_obra':'Valor Mão de Obra',
            'quilometragem':'Quilometragem','pedagio':'Pedágio','outros_ajustes':'Outros Ajustes',
            'justificativa_ajuste':'Justificativa Ajuste','origem_valor':'Origem do Valor','status':'Status'
        })
        anteriores = pd.read_sql_query("""SELECT d.*, a.status AS status_apuracao
            FROM detalhes d JOIN apuracoes a ON a.id=d.apuracao_id
            WHERE a.status='APROVADA' AND d.apuracao_id<>?""", con, params=[apuracao_id])
        pend = pd.read_sql_query('SELECT * FROM pendencias WHERE apuracao_id=?', con, params=[apuracao_id])
    return checklist_integridade(atual, pend, anteriores), atual

def aprovar_apuracao(apuracao_id: str, aprovado_por: str, db_path=None):
    if not aprovado_por.strip():
        raise ValueError('Informe o responsável pela aprovação.')
    with conectar(db_path) as con:
        row = con.execute('SELECT aprovavel, status FROM apuracoes WHERE id=?', (apuracao_id,)).fetchone()
        if row is None:
            raise ValueError('Apuração não encontrada.')
        if row['status'] == 'APROVADA':
            raise ValueError('Esta apuração já foi aprovada. O registro de aprovação não pode ser sobrescrito.')
        if not row['aprovavel']:
            raise ValueError('Esta apuração possui bloqueios e não pode ser aprovada.')

        # Revalidação independente no próprio backend de aprovação.
        integ, atual = validar_aprovacao_persistida(apuracao_id, db_path)
        if not integ['ok']:
            falhas = [x['nome'] for x in integ['checks'] if not x['ok']]
            detalhes = [f"{x['nome']}: {x['detalhe']}" for x in integ['checks'] if not x['ok']]
            raise ValueError('Aprovação bloqueada pela validação de integridade: ' + ' | '.join(detalhes))
        meta_hash = con.execute('SELECT dados_hash FROM apuracoes WHERE id=?', (apuracao_id,)).fetchone()
        if meta_hash and meta_hash['dados_hash'] and hash_dataframe(atual) != meta_hash['dados_hash']:
            raise ValueError('Os dados armazenados foram alterados após a criação da apuração. Aprovação bloqueada.')
    # Backup ANTES de alterar um pagamento para aprovado.
    criar_backup_banco(db_path, motivo='antes_aprovacao')
    with conectar(db_path) as con:
        con.execute('UPDATE apuracoes SET status=?, aprovado_por=?, aprovado_em=? WHERE id=?',
                    ('APROVADA', aprovado_por.strip(), datetime.now().isoformat(timespec='seconds'), apuracao_id))
        meta = con.execute('SELECT tabela_versao, dados_hash, total FROM apuracoes WHERE id=?', (apuracao_id,)).fetchone()
        con.execute('''INSERT INTO auditoria
            (apuracao_id, evento, usuario, ocorrido_em, tabela_versao, dados_hash, detalhes_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (apuracao_id, 'PAGAMENTO_APROVADO', aprovado_por.strip(), datetime.now().isoformat(timespec='seconds'),
             meta['tabela_versao'] if meta else TABELA_VERSAO, meta['dados_hash'] if meta else '',
             json.dumps({'total': float(meta['total']) if meta else 0}, ensure_ascii=False)))


def listar_apuracoes(db_path=None) -> pd.DataFrame:
    inicializar_banco(db_path)
    with conectar(db_path) as con:
        return pd.read_sql_query('SELECT * FROM apuracoes ORDER BY criado_em DESC', con)


def carregar_detalhes(apuracao_id: str | None = None, tecnico: str | None = None, db_path=None) -> pd.DataFrame:
    inicializar_banco(db_path)
    sql = '''SELECT d.*, a.criado_em, a.competencia, a.status AS status_apuracao, a.aprovado_por, a.aprovado_em
             FROM detalhes d JOIN apuracoes a ON a.id=d.apuracao_id WHERE 1=1'''
    args = []
    if apuracao_id:
        sql += ' AND d.apuracao_id=?'; args.append(apuracao_id)
    if tecnico and tecnico != 'Todos':
        sql += ' AND d.tecnico=?'; args.append(tecnico)
    sql += ' ORDER BY d.data DESC, d.tecnico, d.id'
    with conectar(db_path) as con:
        return pd.read_sql_query(sql, con, params=args)


def listar_tecnicos_historico(db_path=None):
    inicializar_banco(db_path)
    with conectar(db_path) as con:
        rows = con.execute('SELECT DISTINCT tecnico FROM detalhes WHERE TRIM(tecnico)<>"" ORDER BY tecnico').fetchall()
    return [r['tecnico'] for r in rows]


def carregar_pendencias(apuracao_id: str, db_path=None) -> pd.DataFrame:
    inicializar_banco(db_path)
    with conectar(db_path) as con:
        return pd.read_sql_query(
            'SELECT * FROM pendencias WHERE apuracao_id=? ORDER BY id',
            con,
            params=[apuracao_id],
        )


def carregar_ultima_apuracao_competencia(competencia: str, db_path=None):
    """Retorna a última apuração salva para MM/AAAA, com detalhe e pendências."""
    inicializar_banco(db_path)
    with conectar(db_path) as con:
        row = con.execute(
            'SELECT * FROM apuracoes WHERE competencia=? ORDER BY criado_em DESC LIMIT 1',
            (competencia,),
        ).fetchone()
    if row is None:
        return None
    meta = dict(row)
    det = carregar_detalhes(meta['id'], db_path=db_path)
    pend = carregar_pendencias(meta['id'], db_path=db_path)
    return meta, det, pend


def _competencias_entre(data_inicio, data_fim):
    """Lista MM/AAAA entre duas datas, inclusive."""
    ini = pd.Timestamp(data_inicio).date()
    fim = pd.Timestamp(data_fim).date()
    if ini > fim:
        ini, fim = fim, ini
    atual = pd.Timestamp(ini.year, ini.month, 1)
    limite = pd.Timestamp(fim.year, fim.month, 1)
    comps = []
    while atual <= limite:
        comps.append(atual.strftime('%m/%Y'))
        atual = atual + pd.offsets.MonthBegin(1)
    return comps


def listar_ultimas_apuracoes_periodo(data_inicio, data_fim, db_path=None) -> pd.DataFrame:
    """Retorna somente a revisão mais recente de cada competência dentro do período."""
    inicializar_banco(db_path)
    comps = _competencias_entre(data_inicio, data_fim)
    if not comps:
        return pd.DataFrame()
    marks = ','.join('?' for _ in comps)
    sql = f'''SELECT * FROM (
                  SELECT a.*, ROW_NUMBER() OVER (
                      PARTITION BY a.competencia
                      ORDER BY a.criado_em DESC, a.rowid DESC
                  ) AS _rn
                  FROM apuracoes a
                  WHERE a.competencia IN ({marks})
              ) x
              WHERE x._rn=1
              ORDER BY x.competencia, x.criado_em DESC'''
    with conectar(db_path) as con:
        return pd.read_sql_query(sql, con, params=comps)


def carregar_historico_periodo(data_inicio, data_fim, tecnico=None, status_apuracao=None, db_path=None):
    """Carrega detalhes/pendências no intervalo de datas usando só a última revisão por competência."""
    hist = listar_ultimas_apuracoes_periodo(data_inicio, data_fim, db_path=db_path)
    if hist.empty:
        return hist, pd.DataFrame(), pd.DataFrame()
    if status_apuracao and status_apuracao != 'Todos':
        hist = hist[hist['status'].astype(str) == str(status_apuracao)].copy()
    if hist.empty:
        return hist, pd.DataFrame(), pd.DataFrame()
    ids = hist['id'].astype(str).tolist()
    marks = ','.join('?' for _ in ids)
    ini = pd.Timestamp(data_inicio).date().isoformat()
    fim = pd.Timestamp(data_fim).date().isoformat()
    sql_det = f'''SELECT d.*, a.criado_em, a.competencia, a.status AS status_apuracao,
                         a.aprovado_por, a.aprovado_em
                  FROM detalhes d JOIN apuracoes a ON a.id=d.apuracao_id
                  WHERE d.apuracao_id IN ({marks})
                    AND date(d.data) BETWEEN date(?) AND date(?)'''
    args = ids + [ini, fim]
    if tecnico and tecnico not in ('Todos', 'Todos os técnicos'):
        sql_det += ' AND d.tecnico=?'
        args.append(tecnico)
    sql_det += ' ORDER BY d.data DESC, d.tecnico, d.id'
    sql_pend = f'''SELECT p.*, a.competencia, a.status AS status_apuracao
                   FROM pendencias p JOIN apuracoes a ON a.id=p.apuracao_id
                   WHERE p.apuracao_id IN ({marks}) ORDER BY p.id'''
    with conectar(db_path) as con:
        det = pd.read_sql_query(sql_det, con, params=args)
        pend = pd.read_sql_query(sql_pend, con, params=ids)
    return hist, det, pend


def carregar_detalhes_aprovados(db_path=None) -> pd.DataFrame:
    inicializar_banco(db_path)
    with conectar(db_path) as con:
        return pd.read_sql_query(
            """SELECT d.*, a.status AS status_apuracao, a.competencia, a.aprovado_por, a.aprovado_em
               FROM detalhes d JOIN apuracoes a ON a.id=d.apuracao_id
               WHERE a.status='APROVADA'""", con)

def listar_auditoria(apuracao_id: str | None = None, db_path=None) -> pd.DataFrame:
    inicializar_banco(db_path)
    sql="SELECT * FROM auditoria WHERE 1=1"; args=[]
    if apuracao_id:
        sql+=" AND apuracao_id=?"; args.append(apuracao_id)
    sql+=" ORDER BY ocorrido_em DESC, id DESC"
    with conectar(db_path) as con:
        return pd.read_sql_query(sql,con,params=args)


def atualizar_ajuste_os(apuracao_id: str, linha_origem: int, det_atual: pd.DataFrame, usuario: str, db_path=None):
    """Persiste uma OS ajustada e registra auditoria; apuração aprovada é imutável."""
    inicializar_banco(db_path)
    alvo = det_atual[pd.to_numeric(det_atual['linha_origem'], errors='coerce') == int(linha_origem)]
    if alvo.empty:
        raise ValueError('OS/linha não encontrada para atualização.')
    r = alvo.iloc[0]
    with conectar(db_path) as con:
        ap = con.execute('SELECT status FROM apuracoes WHERE id=?', (apuracao_id,)).fetchone()
        if not ap:
            raise ValueError('Apuração não encontrada.')
        if ap['status'] == 'APROVADA':
            raise ValueError('Apuração aprovada não pode ser alterada. Crie uma nova revisão.')
        con.execute('''UPDATE detalhes SET tipo_pagamento=?, valor_primeira=?, valor_adicional=?, valor_mao_obra=?, quilometragem=?, pedagio=?, outros_ajustes=?, valor_total=?, justificativa_ajuste=?, origem_valor=?, status=? WHERE apuracao_id=? AND linha_origem=?''', (
            str(r.get('Tipo Pagamento', r.get('Tipo OS',''))), float(r.get('Valor 1ª Hora',0)), float(r.get('Valor Hora Adicional',0)), float(r.get('Valor Mão de Obra',0)), float(r.get('Quilometragem',0)), float(r.get('Pedágio',0)), float(r.get('Outros Ajustes',0)), float(r.get('Valor Total',0)), str(r.get('Justificativa Ajuste','')), str(r.get('Origem do Valor','AUTOMÁTICO')), str(r.get('Status','PROCESSADO')), apuracao_id, int(linha_origem)))
        h = hash_dataframe(det_atual)
        total = float(pd.to_numeric(det_atual['Valor Total'], errors='coerce').fillna(0).sum())
        con.execute('UPDATE apuracoes SET total=?, dados_hash=?, status=? WHERE id=?', (total, h, 'EM REVISÃO', apuracao_id))
        dados = {'os':str(r.get('OS','')), 'cliente':str(r.get('Cliente','')), 'linha_origem':int(linha_origem), 'tipo_original':str(r.get('Tipo Original',r.get('Tipo OS',''))), 'tipo_pagamento':str(r.get('Tipo Pagamento','')), 'quilometragem':float(r.get('Quilometragem',0)), 'pedagio':float(r.get('Pedágio',0)), 'outros_ajustes':float(r.get('Outros Ajustes',0)), 'justificativa':str(r.get('Justificativa Ajuste',''))}
        con.execute('''INSERT INTO auditoria (apuracao_id,evento,usuario,ocorrido_em,tabela_versao,dados_hash,detalhes_json) VALUES (?,?,?,?,?,?,?)''', (apuracao_id, 'OS_AJUSTADA', usuario.strip(), datetime.now().isoformat(timespec='seconds'), TABELA_VERSAO, h, json.dumps(dados, ensure_ascii=False)))
    return h


def substituir_revisao(apuracao_id: str, det_novo: pd.DataFrame, pend_novo: pd.DataFrame,
                       conferencia: dict, usuario: str, det_antes: pd.DataFrame | None=None, db_path=None,
                       permitir_aprovada: bool=False):
    """Persiste revisão recalculada; apuração aprovada só muda em revisão técnica explícita e auditada."""
    inicializar_banco(db_path)
    if not apuracao_id: raise ValueError('Apuração não identificada.')
    antes={}
    if det_antes is not None and len(det_antes):
        antes={int(r['linha_origem']):r.to_dict() for _,r in det_antes.iterrows()}
    with conectar(db_path) as con:
        ap=con.execute('SELECT status FROM apuracoes WHERE id=?',(apuracao_id,)).fetchone()
        if not ap: raise ValueError('Apuração não encontrada.')
        status_anterior=str(ap['status']).upper()
        if status_anterior=='APROVADA' and not permitir_aprovada:
            raise ValueError('Apuração aprovada é imutável fora do fluxo controlado de revisão técnica.')
        con.execute('DELETE FROM detalhes WHERE apuracao_id=?',(apuracao_id,))
        con.execute('DELETE FROM pendencias WHERE apuracao_id=?',(apuracao_id,))
        for _,r in det_novo.iterrows():
            data=r.get('Data','')
            if hasattr(data,'isoformat'): data=data.isoformat()
            con.execute("""INSERT INTO detalhes
            (apuracao_id,linha_origem,os,cliente,tecnico,tipo_os,data,inicio,termino,tempo_minutos,horas_pagas,regra,
             valor_primeira,valor_adicional,valor_total,centro_custo,plantao_fds,faixa_plantao,fim_de_semana,status,
             tipo_original,tipo_pagamento,valor_mao_obra,quilometragem,pedagio,outros_ajustes,justificativa_ajuste,origem_valor)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
             apuracao_id,int(r.get('linha_origem',0)),str(r.get('OS','')),str(r.get('Cliente','')),str(r.get('Técnico','')),
             str(r.get('Tipo OS','')),str(data),str(r.get('Início','')),str(r.get('Término','')),float(r.get('Tempo minutos',0) or 0),
             float(r.get('Horas Pagas',0) or 0),str(r.get('Regra','')),float(r.get('Valor 1ª Hora',0) or 0),
             float(r.get('Valor Hora Adicional',0) or 0),float(r.get('Valor Total',0) or 0),str(r.get('Centro de Custo','')),
             int(bool(r.get('Plantão FDS',False))),str(r.get('Faixa Plantão','')),str(r.get('Fim de Semana','')),
             str(r.get('Status','PROCESSADO')),str(r.get('Tipo Original',r.get('Tipo OS',''))),
             str(r.get('Tipo Pagamento',r.get('Tipo OS',''))),float(r.get('Valor Mão de Obra',r.get('Valor Total',0)) or 0),
             float(r.get('Quilometragem',0) or 0),float(r.get('Pedágio',0) or 0),float(r.get('Outros Ajustes',0) or 0),
             str(r.get('Justificativa Ajuste','')),str(r.get('Origem do Valor','AUTOMÁTICO'))))
        for _,r in pend_novo.iterrows():
            con.execute("""INSERT INTO pendencias
            (apuracao_id,linha_origem,os,cliente,tecnico,tipo_os,centro_custo,motivo,status)
            VALUES (?,?,?,?,?,?,?,?,?)""",(apuracao_id,int(r.get('linha_origem',0)),str(r.get('OS','')),str(r.get('Cliente','')),
             str(r.get('Técnico','')),str(r.get('Tipo OS','')),str(r.get('Centro de Custo','')),str(r.get('Motivo','')),
             str(r.get('Status','PENDENTE'))))
        h=hash_dataframe(det_novo)
        total=float(pd.to_numeric(det_novo['Valor Total'],errors='coerce').fillna(0).sum()) if len(det_novo) else 0.0
        con.execute("""UPDATE apuracoes SET total=?,os_processadas=?,pendencias=?,tecnicos=?,aprovavel=?,
                    alertas_json=?,checks_json=?,dados_hash=?,status=? WHERE id=?""",
                    (total,len(det_novo),len(pend_novo),int(det_novo['Técnico'].nunique() if len(det_novo) else 0),
                     int(bool(conferencia.get('aprovavel'))),json.dumps(conferencia.get('alertas',[]),ensure_ascii=False),
                     json.dumps(conferencia.get('checks',[]),ensure_ascii=False),h,
                     ('APROVADA' if status_anterior=='APROVADA' and permitir_aprovada else ('EM REVISÃO' if conferencia.get('aprovavel') else 'BLOQUEADA')),apuracao_id))
        campos=['Tipo Pagamento','Quilometragem','Pedágio','Outros Ajustes','Justificativa Ajuste','Valor Mão de Obra','Valor Total','Status']
        for _,r in det_novo.iterrows():
            li=int(r.get('linha_origem',0)); old=antes.get(li,{})
            ant={c:old.get(c,'') for c in campos}; dep={c:r.get(c,'') for c in campos}
            if any(str(ant[c])!=str(dep[c]) for c in campos):
                payload={'os':str(r.get('OS','')),'cliente':str(r.get('Cliente','')),'linha_origem':li,
                         'antes':ant,'depois':dep,'valor_km':1.50}
                con.execute("""INSERT INTO auditoria(apuracao_id,evento,usuario,ocorrido_em,tabela_versao,dados_hash,detalhes_json)
                            VALUES(?,?,?,?,?,?,?)""",(apuracao_id,'OS_AJUSTADA_EM_MASSA',usuario.strip(),
                            datetime.now().isoformat(timespec='seconds'),TABELA_VERSAO,h,json.dumps(payload,ensure_ascii=False)))
        if status_anterior=='APROVADA' and permitir_aprovada:
            con.execute("""INSERT INTO auditoria(apuracao_id,evento,usuario,ocorrido_em,tabela_versao,dados_hash,detalhes_json)
                        VALUES(?,?,?,?,?,?,?)""",(apuracao_id,'REVISAO_TECNICA_INCORPORADA',usuario.strip(),
                        datetime.now().isoformat(timespec='seconds'),TABELA_VERSAO,h,json.dumps({'total_recalculado':total},ensure_ascii=False)))
    return h

def buscar_os_global(numero_os: str, db_path=None) -> pd.DataFrame:
    """Busca a OS em todas as competências; competência não é filtro obrigatório."""
    inicializar_banco(db_path)
    alvo=str(numero_os or '').strip().upper()
    if alvo.endswith('.0') and alvo[:-2].isdigit(): alvo=alvo[:-2]
    if not alvo: return pd.DataFrame()
    with conectar(db_path) as con:
        df=pd.read_sql_query("""SELECT d.*,a.competencia,a.criado_em,a.status AS status_apuracao,
                               a.aprovado_por,a.aprovado_em FROM detalhes d
                               JOIN apuracoes a ON a.id=d.apuracao_id ORDER BY a.criado_em DESC""",con)
    def norm(v):
        x=str(v or '').strip().upper()
        return x[:-2] if x.endswith('.0') and x[:-2].isdigit() else x
    return df[df['os'].map(norm)==alvo].copy() if len(df) else df

def auditoria_por_os(numero_os: str, db_path=None) -> pd.DataFrame:
    inicializar_banco(db_path)
    alvo=str(numero_os or '').strip().upper()
    if alvo.endswith('.0') and alvo[:-2].isdigit(): alvo=alvo[:-2]
    with conectar(db_path) as con:
        aud=pd.read_sql_query("""SELECT au.*,a.competencia FROM auditoria au
                                LEFT JOIN apuracoes a ON a.id=au.apuracao_id
                                ORDER BY au.ocorrido_em DESC,au.id DESC""",con)
    out=[]
    for _,r in aud.iterrows():
        try: d=json.loads(r.get('detalhes_json') or '{}')
        except Exception: d={}
        x=str(d.get('os','')).strip().upper()
        if x.endswith('.0') and x[:-2].isdigit(): x=x[:-2]
        if x!=alvo: continue
        ant=d.get('antes',{}) or {}; dep=d.get('depois',{}) or {}
        campos=sorted(set(ant)|set(dep))
        if campos:
            for c in campos:
                if str(ant.get(c,''))!=str(dep.get(c,'')):
                    out.append({'Data/Hora':r['ocorrido_em'],'Responsável':r.get('usuario',''),
                                'Competência':r.get('competencia',''),'Campo':c,'Antes':ant.get(c,''),'Depois':dep.get(c,'')})
        else:
            out.append({'Data/Hora':r['ocorrido_em'],'Responsável':r.get('usuario',''),
                        'Competência':r.get('competencia',''),'Campo':r.get('evento',''),'Antes':'','Depois':d})
    return pd.DataFrame(out)
