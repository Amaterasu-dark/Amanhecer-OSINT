# Histórico de versões

## Em desenvolvimento

- Refatoração da CLI e do domínio com `match/case`, funções por responsabilidade e normalização independente dos adaptadores. Cálculo de dígitos e formatação de campos compartilhados.
- CNPJ disponível na CLI: validação local numérica/alfanumérica e consulta empresarial pela BrasilAPI, com conferência do CNPJ retornado.
- Telefone brasileiro: normalização com DDD/DDI, análise local de formato e região do DDD na BrasilAPI. Não consulta titular, operadora ou atividade da linha.
- `--somente-validar` disponível para CPF, CNPJ e telefone; relatórios texto, JSON e HTML para os novos tipos.
- Testes automatizados e consultas ao vivo desta etapa não executados, conforme combinado. Revisão por leitura do código.

## 0.2.0

- CLI focada em `arroba`, `nome` e `cpf`, com opção `--version`.
- Busca por arroba no GitHub e GitLab, distinguindo encontrado, não encontrado e inconclusivo.
- Busca por nome completo, com candidatos, limite por fonte e indicação de pesquisa incompleta.
- Consulta CPF pelo adaptador do Serpro v3, mediante token e nascimento; modo separado de validação local dos dígitos.
- CPF mascarado nos relatórios de texto, JSON e HTML; token e nascimento omitidos das saídas.
- HTTP 206 preservado como resultado parcial; token restrito ao endpoint de CPF; consultas de produção sem repetição automática.
- 66 testes automatizados sem rede. Consultas ao vivo permanecem pendentes; o Serpro exige configuração do contrato/token.
- Adaptadores cadastrais e de domínios do protótipo preservados internamente, fora da CLI desta versão.
