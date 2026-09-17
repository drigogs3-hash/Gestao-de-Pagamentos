from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

APP_NAME = 'PagamentoTecnicos'
ORG_NAME = 'ProSecurity'


def raiz_persistente() -> Path:
    """Diretório permanente, independente da pasta/versão do programa."""
    custom = os.getenv('PROSECURITY_PAGAMENTOS_HOME')
    if custom:
        return Path(custom).expanduser().resolve()

    local = os.getenv('LOCALAPPDATA')
    if local:  # Windows
        return Path(local) / ORG_NAME / APP_NAME

    # Fallback para testes/Linux/macOS.
    return Path.home() / '.prosecurity' / APP_NAME


def diretorio_dados() -> Path:
    p = raiz_persistente() / 'dados'
    p.mkdir(parents=True, exist_ok=True)
    return p


def diretorio_backups() -> Path:
    p = raiz_persistente() / 'backups'
    p.mkdir(parents=True, exist_ok=True)
    return p


def diretorio_originais() -> Path:
    p = raiz_persistente() / 'originais'
    p.mkdir(parents=True, exist_ok=True)
    return p


def caminho_banco() -> Path:
    return diretorio_dados() / 'apuracoes.db'


def salvar_arquivo_original(apuracao_id: str, nome: str, conteudo: bytes | None) -> str:
    if not conteudo:
        return ''
    nome_limpo = Path(nome or 'relatorio.xlsx').name
    pasta = diretorio_originais() / apuracao_id
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / nome_limpo
    destino.write_bytes(conteudo)
    return str(destino)


def criar_backup_banco(db_path: str | Path | None = None, motivo: str = 'manual') -> Path | None:
    origem = Path(db_path) if db_path else caminho_banco()
    if not origem.exists():
        return None
    carimbo = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    motivo_limpo = ''.join(c for c in motivo.lower() if c.isalnum() or c in ('-', '_')) or 'backup'
    destino = diretorio_backups() / f'apuracoes_{carimbo}_{motivo_limpo}.db'
    shutil.copy2(origem, destino)
    return destino
