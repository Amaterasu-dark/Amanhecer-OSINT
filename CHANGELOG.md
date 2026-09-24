# Histórico de versões

## 0.2.0

- CLI focada em `arroba`, `nome` e `cpf`, com opção `--version`.
- Busca por arroba no GitHub e GitLab, distinguindo encontrado, não encontrado e inconclusivo.
- Busca por nome completo, com candidatos, limite por fonte e indicação de pesquisa incompleta.
- Consulta CPF pelo adaptador do Serpro v3, mediante token e nascimento; modo separado de validação local dos dígitos.
- CPF mascarado nos relatórios de texto, JSON e HTML; token e nascimento omitidos das saídas.
- HTTP 206 preservado como resultado parcial; token restrito ao endpoint de CPF; consultas de produção sem repetição automática.
- 66 testes automatizados sem rede. Consultas ao vivo permanecem pendentes; o Serpro exige configuração do contrato/token.
- Adaptadores cadastrais e de domínios do protótipo preservados internamente, fora da CLI desta versão.
