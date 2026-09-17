from __future__ import annotations
import io
import pandas as pd

LAYOUT_RELATORIO_SEM_CABECALHO = {
    0: 'Data', 1: 'Processo', 2: 'Fornecedor/Técnico Cadastro', 3: 'Centro de Custo',
    4: 'Status', 5: 'OS', 6: 'Cliente', 7: 'Tipo OS', 8: 'Início',
    9: 'Término', 10: 'Duração Informada', 11: 'Técnico',
}


def _nome_arquivo(arq) -> str:
    return str(getattr(arq, 'name', 'arquivo.xlsx')).lower()


def _snapshot_bytes(arq) -> bytes:
    """Obtém uma cópia estável dos bytes do upload.

    Streamlit UploadedFile é um objeto de memória cujo cursor pode mudar depois de
    uma leitura. Sempre criamos um BytesIO novo para cada tentativa de pd.read_excel,
    eliminando diferenças entre Windows/Streamlit e testes com arquivo em disco.
    """
    if hasattr(arq, 'getvalue'):
        return arq.getvalue()
    pos = None
    try:
        pos = arq.tell()
    except Exception:
        pass
    try:
        arq.seek(0)
    except Exception:
        pass
    data = arq.read()
    if pos is not None:
        try:
            arq.seek(pos)
        except Exception:
            pass
    return data


def _ler_excel_bytes(data: bytes, header=0):
    return pd.read_excel(io.BytesIO(data), header=header)


def _parece_relatorio_sem_cabecalho(df: pd.DataFrame) -> bool:
    if df.shape[1] < 12 or df.empty:
        return False
    primeira = df.iloc[0]
    b = str(primeira.iloc[1]).strip().upper() if pd.notna(primeira.iloc[1]) else ''
    e = str(primeira.iloc[4]).strip().upper() if pd.notna(primeira.iloc[4]) else ''
    h = str(primeira.iloc[7]).strip().upper() if pd.notna(primeira.iloc[7]) else ''
    return b.startswith('PO') and e in {'APROVADO', 'APROVADA'} and '(MAN)' in h


def _limpar_cabecalhos(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # remove quebra de linha, NBSP e espaços antes/depois; preserva nomes legíveis.
    out.columns = [
        str(c).replace('\n', ' ').replace('\r', ' ').replace('\xa0', ' ').strip()
        for c in out.columns
    ]
    return out


def ler_relatorio(arq):
    nome = _nome_arquivo(arq)
    if nome.endswith('.csv'):
        data = _snapshot_bytes(arq)
        df = pd.read_csv(io.BytesIO(data), sep=None, engine='python')
        return _limpar_cabecalhos(df), 'CSV COM CABEÇALHO'

    data = _snapshot_bytes(arq)
    convencional = _limpar_cabecalhos(_ler_excel_bytes(data, header=0))

    # O TESTE1 real tem 38 colunas e o bloco operacional no final.
    # Usamos nomes normalizados apenas para identificar o layout; o mapeamento
    # definitivo possui também fallback por posição no processamento.py.
    cols_upper = {str(c).strip().upper() for c in convencional.columns}
    marcadores_teste1 = {'HORA INCIO', 'HORA FIM', 'TEMPO DE ATEMDIMENTO', 'SERVIÇO', 'DEFEITO', 'TÉCNICO'}
    if convencional.shape[1] >= 38 or len(marcadores_teste1.intersection(cols_upper)) >= 4:
        # Remove somente linhas de total sem dados operacionais.
        indices_operacionais = [17, 32, 33, 35, 36, 37]
        cols_ops = [convencional.columns[i] for i in indices_operacionais if i < convencional.shape[1]]
        if cols_ops:
            convencional = convencional.loc[convencional[cols_ops].notna().any(axis=1)]
        return convencional.reset_index(drop=True), 'LAYOUT TESTE1 / 38 COLUNAS IDENTIFICADO'

    bruto = _ler_excel_bytes(data, header=None)
    if _parece_relatorio_sem_cabecalho(bruto):
        bruto = bruto.iloc[:, :12].copy()
        bruto.columns = [LAYOUT_RELATORIO_SEM_CABECALHO[i] for i in range(12)]
        bruto = bruto.dropna(how='all').reset_index(drop=True)
        return bruto, 'LAYOUT LEGADO — SEM CABEÇALHO'

    return convencional, 'EXCEL COM CABEÇALHO'


def ler_parametrizacao(arq):
    nome = _nome_arquivo(arq)
    data = _snapshot_bytes(arq)
    if nome.endswith('.csv'):
        return pd.read_csv(io.BytesIO(data), sep=None, engine='python')
    return pd.read_excel(io.BytesIO(data))
