# Fala Brasil Notícias — atualização automática

O portal usa GitHub Pages para hospedagem e GitHub Actions para buscar notícias RSS a cada 2 horas. O computador do proprietário não precisa ficar ligado.

## Configuração obrigatória da IA

1. Crie uma chave de API em https://platform.openai.com/api-keys e confira a forma de cobrança da API (a assinatura do ChatGPT não inclui créditos de API).
2. No GitHub, abra o repositório `fala-brasil-noticias-site`.
3. Vá em **Settings → Secrets and variables → Actions → New repository secret**.
4. Nome: `OPENAI_API_KEY`. Valor: sua chave da API. Não coloque a chave em nenhum arquivo do site ou commit.

Sem esse segredo, o fluxo ainda publica títulos e descrições dos feeds, mas não gera resumos com IA.

## Ativar o fluxo

- Confirme em **Settings → Actions → General → Workflow permissions** que workflows podem ter permissão de leitura e escrita no repositório.
- O arquivo `.github/workflows/atualizar-noticias.yml` agenda a execução em `17 */2 * * *` (UTC) e também permite execução manual pela aba **Actions**.
- Abra **Actions → Atualizar notícias automaticamente → Run workflow** para testar imediatamente.
- O fluxo atualiza `news.json` e faz commit automático. O GitHub Pages publica a alteração em seguida.

## Conteúdo e direitos

O sistema consulta resultados RSS do Google Notícias por editoria, mantém título, data, nome da fonte e link original, e cria resumos curtos a partir dos metadados/trechos disponíveis. Não copia o texto integral da reportagem. A disponibilidade dos feeds e os horários de execução podem variar. Revise o conteúdo e as fontes periodicamente.

## Frequência

A programação é a cada 2 horas. O agendador do GitHub Actions pode atrasar alguns minutos e não é um serviço de tempo real.
