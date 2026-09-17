# Gestão de Pagamentos Técnicos — V10.5 Permanente

A V10.5 reconstrói a navegação como uma camada própria em HTML/CSS, sem depender da sidebar nativa do Streamlit. O objetivo é reproduzir o mockup aprovado com fidelidade: menu fixo de 218 px, fundo de condomínio com tratamento vermelho translúcido, ícones brancos, item ativo em vermelho vivo, slogan e versão no rodapé, cabeçalho branco com o logotipo oficial e área principal preservada.

## Instalação / atualização
1. Feche a versão que estiver aberta.
2. Execute `INSTALAR_SISTEMA.bat`.
3. O instalador faz backup do banco antes de atualizar os arquivos do programa.
4. Abra pelo atalho `Gestao de Pagamentos Tecnicos` na Área de Trabalho.

Os dados permanecem em `%LOCALAPPDATA%\ProSecurity\PagamentoTecnicos` e não são substituídos pela atualização.

## Porta
V10.5: http://localhost:8539

## Navegação
A barra lateral é HTML/CSS próprio e usa parâmetros de URL para mudar de página. Não há botão `<<`, bolinhas, filtros, radio buttons ou scroll da sidebar nativa.

## Período
A Visão Geral mantém dois calendários independentes `De` e `Até`, com histórico consolidado pela revisão mais recente de cada competência.
