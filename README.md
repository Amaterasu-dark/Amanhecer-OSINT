# Amanhecer OSINT

Versão **0.2.0**. Aplicação Python de linha de comando com busca de perfis públicos por **arroba e nome completo**, além de **consulta cadastral de CPF pelo serviço contratado do Serpro**. Python 3.11 ou superior; nenhuma dependência externa em execução.

## Escopo acordado

1. **Arroba:** consulta exata no GitHub e GitLab, com ou sem `@`.
2. **CPF:** validação de formato/dígitos e adaptador da Consulta CPF v3 do Serpro. A consulta cadastral exige contrato habilitado, Bearer token e data de nascimento. Sem credenciais, só o modo explícito `--somente-validar` funciona.
3. **Nome completo:** busca de possíveis perfis no GitHub e GitLab. Resultados são candidatos, sujeitos a homônimos e correspondências aproximadas.

Consultas de sites e domínios ficam para outra versão. CNPJ, CEP, DDD e banco não fazem parte desta etapa. O código do protótipo anterior está preservado internamente, mas essas consultas não são expostas pela CLI nem acionadas na busca por arroba.

## Fontes implementadas

| Plataforma | Consulta | Dados apresentados quando retornados |
| --- | --- | --- |
| GitHub | API pública, usuário exato | URL do perfil, arroba, ID, nome público, bio, tipo de conta, repositórios públicos, seguidores e data de criação |
| GitLab.com | API, filtro exato de username | URL do perfil, arroba, ID, nome público e estado da conta |
| GitHub / GitLab.com | Pesquisa por nome | Candidatos com arroba e URL; nome público quando a API o retorna |
| Serpro Consulta CPF v3 | CPF e nascimento, com Bearer token | Nome e situação cadastral retornados pela fonte; identificação de conteúdo parcial |

GitHub e GitLab são as integrações iniciais. Instagram, TikTok e X ainda não têm adaptadores implementados. As plataformas prioritárias podem ser ampliadas posteriormente; a existência de um adaptador não garante disponibilidade da fonte ou acesso sem autenticação em todos os ambientes.

Arroba e nome não fazem login nem usam tokens. CPF usa exclusivamente o token de acesso ao Serpro, enviado apenas ao endpoint dessa consulta. Respostas de autenticação obrigatória, bloqueio, limite de requisições, redirecionamento ou falha de rede aparecem como **inconclusivas**. A aplicação não segue redirecionamentos automaticamente.

## Executar no PowerShell

Na pasta do projeto, com Python 3.11 ou superior selecionado:

```powershell
py -3 main.py --help
py -3 main.py --version
py -3 main.py arroba "@octocat"
py -3 main.py arroba octocat --plataforma github
py -3 main.py arroba octocat --plataforma github --plataforma gitlab
py -3 main.py arroba octocat --formato json --saida reports/arroba.json
py -3 main.py arroba octocat --formato html --saida reports/arroba.html
py -3 main.py nome "Maria da Silva"
py -3 main.py nome "Maria da Silva" --plataforma github --limite 10
py -3 main.py cpf 404.428.201-35 --somente-validar
```

Use aspas ao informar `@apelido` no PowerShell. Sem `@`, as aspas são opcionais. URLs, espaços internos e entradas como `@@apelido` são rejeitados. A entrada aceita de 1 a 64 caracteres ASCII: letras, números, ponto, hífen e sublinhado, começando por letra, número ou sublinhado. Cada fonte pode ter regras de arroba mais restritas.

A saída padrão é texto legível no terminal. JSON e HTML incluem todos os campos coletados, URL da fonte e data UTC por resultado. O HTML é um arquivo de relatório, não uma interface web.

### Consulta de CPF

O número usado no exemplo de validação é uma fixture fictícia publicada na [demonstração do Serpro](https://apicenter.estaleiro.serpro.gov.br/documentacao/consulta-cpf/pt/quick_start/#dados-para-testes). `--somente-validar` roda sem rede e informa apenas se o formato e os dígitos verificadores conferem. Não comprova que exista um cadastro, nem informa titular ou situação cadastral.

A consulta cadastral usa a [API Serpro v3](https://apicenter.estaleiro.serpro.gov.br/documentacao/consulta-cpf/pt/chamadas/consulta-cpf-df-v3/), que requer CPF e nascimento. Obtenha um Bearer token conforme a [autenticação oficial](https://apicenter.estaleiro.serpro.gov.br/documentacao/consulta-cpf/pt/quick_start/), usando as credenciais do seu contrato. O programa recebe um token já emitido; não contrata o serviço nem gera ou renova tokens automaticamente.

No PowerShell 7, informe o token sem colocá-lo no histórico de comandos:

```powershell
$env:AMANHECER_SERPRO_TOKEN = Read-Host "Bearer token do Serpro" -MaskInput
py -3 main.py cpf "SEU_CPF" --nascimento "AAAA-MM-DD"
```

Substitua `SEU_CPF` e `AAAA-MM-DD` pelos dados da consulta. Esse comando usa **produção** e pode consumir a franquia ou gerar cobrança no serviço contratado. O aplicativo desativa novas tentativas automáticas para CPF. Nenhuma chamada ao Serpro de produção foi executada nos testes desta versão.

O número do CPF fica mascarado no texto, JSON e HTML. Data de nascimento e token não são gravados no relatório. O relatório registra o modelo do endpoint sem esses valores na URL. A entrada do CPF e nascimento ainda pode aparecer no histórico do seu terminal e na lista de argumentos do processo; o mascaramento se aplica às saídas da aplicação. Não há arquivo de credenciais ou carregamento automático de `.env`.

### Busca por nome completo

Informe pelo menos duas palavras entre aspas. Acentos, apóstrofos e hífens são aceitos. O GitHub pesquisa o campo de nome; o GitLab utiliza a busca de usuários, que também pode corresponder a um arroba. Os resultados recebem a classificação **CANDIDATOS**, sem confirmação de identidade e sem cruzamento automático com CPF.

Por padrão, é consultada somente a primeira página, com até 10 resultados por fonte. `--limite` aceita de 1 a 50. O relatório indica quando podem existir mais resultados e preserva a indicação de pesquisa incompleta do GitHub. Nenhum nome é inventado quando a API retorna apenas o arroba.

Alternativamente, execute `py -3 -m amanhecer`. Para instalar o comando `amanhecer` em um ambiente virtual:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\amanhecer.exe arroba octocat
```

`--plataforma` se aplica a arroba/nome e pode ser repetido; repetições da mesma fonte são deduplicadas. Sem a opção, GitHub e GitLab são consultados. `--timeout 15` limita cada operação HTTP, não o tempo total. Em arroba/nome há até duas novas tentativas para falhas transitórias de conexão e erros HTTP de servidor selecionados. CPF não faz novas tentativas automáticas. HTTP 429 encerra a consulta àquela fonte. As consultas são sequenciais, com intervalo mínimo de 0,5 s entre inícios de requisição. Respostas acima de 5 MB são rejeitadas. Arquivos existentes não são sobrescritos.

## Interpretação dos resultados

| Resultado no terminal | `data.match` no JSON | Significado |
| --- | --- | --- |
| ENCONTRADO | `found` | A fonte retornou um perfil com o arroba consultado, desconsiderando maiúsculas/minúsculas |
| NÃO ENCONTRADO | `not_found` | A fonte não retornou um perfil público: HTTP 404 no GitHub ou lista vazia no GitLab |
| INCONCLUSIVO | `inconclusive` | Não foi possível confirmar a consulta: erro, bloqueio, formato inesperado ou resposta com outro arroba |
| CANDIDATOS | `candidates` | A busca por nome retornou perfis para conferência manual; não confirma identidade |
| DÍGITOS VÁLIDOS | `validated` | Validação local de CPF, sem consulta cadastral |

Para CPF, `found` significa que o Serpro devolveu dados correspondentes ao CPF e nascimento informados; `not_found` corresponde ao HTTP 404 da fonte. HTTP 206 é registrado como conteúdo parcial. Divergência entre os identificadores enviados e retornados torna a consulta inconclusiva.

Um resultado não encontrado **não comprova inexistência da conta**: a fonte pode ocultar perfis indisponíveis ao acesso público. O mesmo arroba em plataformas diferentes **não confirma que os perfis pertencem à mesma pessoa**. Uma conta encontrada pode representar uma organização ou bot; quando disponível, o tipo consta no resultado do GitHub. Não há correlação automática de identidades.

O campo `status` é `ok` quando a fonte respondeu de forma interpretável, inclusive para `not_found`; é `error` quando a consulta foi inconclusiva ou a busca foi declarada incompleta pela fonte. Candidatos já retornados são preservados mesmo em pesquisa incompleta. Falhas em uma fonte não descartam as respostas das demais.

Códigos de saída: `0` para consultas concluídas, mesmo sem perfil encontrado; `1` quando alguma fonte falha; `2` para entrada/configuração/arquivo inválido; `130` para interrupção.

## Arquitetura

Portas e adaptadores, com orientação a objetos e injeção de dependências:

```text
main.py / amanhecer/__main__.py
             |
          cli.py           argumentos e composição
             |
       application.py     caso de uso e seleção de fontes
          /       \
    domain.py    ports.py  entidades, validação e contratos
                    |
    usernames.py / names.py / cpf.py  adaptadores por tipo de consulta
                    |
                 http.py    transporte HTTPS

reports.py                saída texto/JSON/HTML
providers.py              registro de fontes e adaptadores do protótipo anterior
tests/                    testes sem acesso à rede
```

`InvestigationService` recebe provedores pelo construtor. Cada provedor implementa `supports` e `collect` e recebe um `JsonClient`. `SourceHttpError` preserva o código HTTP para o adaptador decidir se houve ausência de resultado ou falha da fonte.

Para adicionar uma plataforma, implemente `UsernameProvider`, definindo a URL e a interpretação da resposta, e registre em `USERNAME_PROVIDERS`. Inclua novos hosts em `HttpClient.ALLOWED_HOSTS`. Só classifique como encontrado quando a resposta identificar o arroba exato. Não trate um HTTP 200 genérico ou uma tela de login como confirmação de perfil.

## Verificação

```powershell
py -3 -m unittest discover -s tests -v
```

Os 66 testes cobrem arroba, nomes com acentos, CPF com zeros iniciais, dígitos verificadores, datas, respostas malformadas, ausência de resultados, homônimos/candidatos, pesquisas incompletas, HTTP 206/403/404/429, credenciais restritas ao host do Serpro, falhas parciais, opções incompatíveis, seleção de plataformas, exportação com CPF mascarado, proteção de arquivos, caracteres de controle no terminal e escape HTML. Também preservam testes internos do protótipo anterior. Usam respostas simuladas e não certificam disponibilidade das fontes externas.

Para a validação manual no terminal, execute as consultas acima e compare cada resultado com a página pública da respectiva plataforma. Teste também `"@@apelido"`, uma fonte indisponível e uma segunda exportação para o mesmo arquivo. Resultado inconclusivo deve permanecer visível no relatório.

## Referências técnicas

- [GitHub: consulta de usuário](https://docs.github.com/en/rest/users/users#get-a-user)
- [GitHub: erros e limites da API](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api)
- [GitLab: Users API e filtro por username](https://docs.gitlab.com/api/users/)
- [GitHub: busca de usuários](https://docs.github.com/en/rest/search/search#search-users)
- [Serpro: Consulta CPF v3](https://apicenter.estaleiro.serpro.gov.br/documentacao/consulta-cpf/pt/chamadas/consulta-cpf-df-v3/)
- [Serpro: autenticação e dados fictícios para testes](https://apicenter.estaleiro.serpro.gov.br/documentacao/consulta-cpf/pt/quick_start/)

As buscas enviam o arroba/nome às plataformas selecionadas. A consulta de CPF envia CPF e nascimento apenas ao Serpro, junto ao Bearer token. O software não mantém cache ou banco de dados; persistência só ocorre quando `--saida` é informado ou a saída padrão é redirecionada.
