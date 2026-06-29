# FutNeural - Bot Preditivo Copa do Mundo 2026

Bot de previsoes de futebol com interface grafica, que combina modelo de Poisson com Rede Neural (MLP) para prever resultados, gols, escanteios, cartoes e outros mercados de aposta.

## Funcionalidades

- Previsao de **15+ mercados de aposta** (1X2, Over/Under, BTTS, Placar Exato, Chance Dupla, Escanteios, Cartoes, 1o Tempo)
- **Aba exclusiva Copa 2026** com previsoes baseadas apenas nos jogos reais do torneio
- **Sistema de nivel** (0-10) que rastreia a eficiencia do bot ao longo do tempo
- **Explicacao humanizada** de cada previsao via IA (Groq), sem inventar dados
- **Retreino manual** do modelo — treine quantas vezes quiser, ele so salva se melhorar
- Preparado para integracao futura com **Telegram**

## Estrutura do Projeto

| Arquivo | Funcao |
|---|---|
| `gui.py` | Interface grafica (CustomTkinter) — ponto de entrada |
| `modelo.py` | Treino MLP, Poisson, mercados, previsao, explicacao, Excel |
| `api_football.py` | API-Football + Groq (traducao, fallback, cache, rate limiting) |
| `nivel.py` | Sistema de nivel de eficiencia (0-10) |
| `config.py` | Constantes, paths, chaves API |
| `gerar_dataset.py` | Gera dataset de treino a partir da API-Football |
| `config_local.py` | Suas chaves de API (nao versionado) |
| `config_local.example.py` | Modelo de como preencher as chaves |

## Instalacao

```bash
pip install requests joblib scikit-learn pandas numpy scipy openpyxl groq customtkinter
```

## Configuracao

1. Crie uma conta gratuita na API-Football: https://dashboard.api-football.com/register
2. (Opcional) Crie uma chave no Groq: https://console.groq.com
3. Copie `config_local.example.py` para `config_local.py`
4. Preencha suas chaves:

```python
FOOTBALL_API_KEY = "sua_chave_aqui"
GROQ_API_KEY = "sua_chave_aqui"   # opcional
```

## Primeiros passos

```bash
# 1. Gerar o dataset de treino (roda uma vez, resultados ficam cacheados)
python gerar_dataset.py

# 2. Abrir o bot
python gui.py
```

Na primeira execucao, o bot treina o modelo automaticamente a partir do `historico_jogos.csv`.

---

# Manual de Uso

## Aba: Nova Previsao

Previsao completa usando dados historicos (2022-2024) + dados da Copa 2026 (se disponiveis), combinando Poisson + Rede Neural.

**Como usar:**
1. Digite o nome do time da casa (pode ser em portugues: "Brasil", "Alemanha")
2. Digite o nome do time de fora
3. Clique em **Gerar Previsao**

**O que aparece:**
- Probabilidades de Vitoria Casa / Empate / Vitoria Fora
- xG (gols esperados) de cada time
- Todos os mercados detalhados (Over/Under, BTTS, Placar Exato, etc.)
- Analise em linguagem natural explicando o "porque" da previsao

**Observacao:** os nomes dos times podem ser em portugues ou ingles. Se o Groq estiver configurado, ele traduz automaticamente (ex: "Brasil" vira "Brazil").

---

## Aba: Previsao Copa 2026

Previsao que usa **exclusivamente** os dados reais da Copa do Mundo 2026. Nao mistura com dados historicos. Ideal para apostar nos jogos do torneio em andamento.

**Como usar:**
1. Digite os times em **ingles** (como estao no CSV: Brazil, Argentina, Germany, etc.)
2. Clique em **Prever (Copa 2026)**

**Diferenca para a aba "Nova Previsao":**
- Usa **apenas** os jogos registrados em `copa_2026_resultados.csv`
- Modelo: Poisson Puro (sem Rede Neural — poucos jogos por selecao no torneio)
- Se o time nao tiver jogos registrados, aparece um erro pedindo para registrar

**Mercados exibidos:**
- Resultado 1X2 e Chance Dupla
- Over/Under 0.5, 1.5, 2.5, 3.5 gols
- Ambas Marcam (BTTS)
- Gols por equipe (Over 0.5, Over 1.5)
- Resultado do 1o Tempo
- Placar Exato (8 mais provaveis)
- Escanteios (~total esperado + Over 8.5, 9.5, 10.5)
- Cartoes (~total esperado + Over 3.5, 4.5, 5.5)
- Analise humanizada

---

## Aba: Jogos da Copa

Registra os resultados reais dos jogos da Copa do Mundo 2026. Esses dados alimentam a aba "Previsao Copa 2026".

**Como usar:**
1. Preencha: time Casa, time Fora, Gols Casa, Gols Fora
2. (Opcional) Preencha: Escanteios Casa/Fora, Cartoes Casa/Fora
3. Clique em **Registrar Resultado**

**Dica:** apos cada rodada da Copa, registre os jogos que aconteceram. Quanto mais jogos registrados, melhores as previsoes da aba Copa 2026.

**Alternativa:** voce pode editar diretamente o arquivo `copa_2026_resultados.csv` com os resultados. O formato e:

```
Data,Casa,Fora,Gols_Casa,Gols_Fora,Escanteios_Casa,Escanteios_Fora,Cartoes_Casa,Cartoes_Fora
2026-06-13,Brazil,Morocco,1,1,0,0,0,0
2026-06-29,Brazil,Japan,2,1,6,2,2,3
```

Os nomes devem estar em **ingles**.

---

## Aba: Resultados

Fecha previsoes feitas anteriormente com os resultados reais. Atualiza o nivel de eficiencia do bot.

**Como usar:**

1. Clique em **Sincronizar Resultados (API)** para fechar automaticamente jogos que a API-Football ja tem o resultado (temporadas 2022-2024)
2. Para jogos da Copa 2026 ou amistosos: use o fechamento manual
   - Informe o **ID** da previsao (aparece na lista), **Gols Casa** e **Gols Fora**
   - Clique em **Fechar**

**O que acontece ao fechar:**
- O bot compara o palpite dele com o resultado real
- Marca como ACERTOU ou ERROU
- Atualiza o nivel de eficiencia na sidebar
- O jogo e adicionado ao dataset de treino (para aprendizado continuo)

---

## Aba: Retreinar Bot

Treina a Rede Neural multiplas vezes com seeds diferentes e salva apenas o melhor resultado.

**Como usar:**
1. Defina o numero de tentativas (padrao: 50)
2. Clique em **Treinar Agora**
3. Acompanhe o progresso em tempo real
4. No final, o bot mostra se salvou um novo modelo ou manteve o anterior

**Regras do retreino:**
- O bot mede a acuracia do modelo **atual** antes de treinar
- Cada tentativa usa uma seed aleatoria diferente
- Todas sao avaliadas no **mesmo split** de dados (comparacao justa)
- So salva se a nova tentativa for **estritamente melhor** que o modelo atual
- O bot nunca piora — pode treinar quantas vezes quiser sem risco

**Quando treinar:**
- Apos registrar novos resultados (o dataset cresce, o bot pode aprender mais)
- 50-200 tentativas e suficiente para extrair o maximo do dataset atual
- Mais tentativas (500+) tem retorno decrescente com os mesmos dados

---

## Aba: Tabela de Grupos

Mostra a classificacao atual dos grupos da Copa do Mundo 2026.

**Como usar:**
- Clique em **Carregar Tabela**
- Requer `FOOTBALL_API_KEY` configurada
- Mostra: selecao, pontos, vitorias, empates, derrotas, gols pro e contra

**Nota:** depende do plano da API-Football ter acesso a temporada 2026. No plano gratuito, pode nao estar disponivel.

---

## Aba: Status APIs

Diagnostico das chaves de API e estado geral do bot.

**Mostra:**
- Se a `FOOTBALL_API_KEY` esta configurada e de onde foi lida (env ou arquivo)
- Plano da API e requisicoes usadas hoje / limite diario
- Se a `GROQ_API_KEY` esta configurada (traducao de nomes e explicacoes)
- Se o modelo treinado existe e se o dataset existe

---

## Sistema de Nivel

O bot comeca no nivel **5.0/10**. A cada resultado fechado:

| Situacao | Variacao |
|---|---|
| Acertou com confianca alta (>70%) | +0.20 |
| Acertou com confianca media (50-70%) | +0.15 |
| Acertou com confianca baixa (<50%) | +0.10 |
| Errou com confianca baixa (<50%) | -0.10 |
| Errou com confianca media (50-70%) | -0.15 |
| Errou com confianca alta (>70%) | -0.25 |

O nivel fica entre 0.0 e 10.0 e e salvo em `nivel_bot.json`. Aparece na sidebar junto com o percentual de acerto.

---

## Arquivos de dados (nao versionados)

| Arquivo | Conteudo |
|---|---|
| `historico_jogos.csv` | Dataset de treino do modelo (550+ jogos) |
| `copa_2026_resultados.csv` | Jogos reais da Copa 2026 (voce alimenta) |
| `cerebro_bot.joblib` | Modelo MLP treinado (salvo automaticamente) |
| `nivel_bot.json` | Nivel de eficiencia e historico de acertos |
| `historico_predicoes.xlsx` | Todas as previsoes feitas e seus resultados |
| `cache_api_football.json` | Cache de requisicoes da API (economiza cota) |

---

## Como o bot aprende

1. **Treino inicial**: modelo MLP treinado com 550 jogos do dataset (`historico_jogos.csv`)
2. **Dados da Copa**: jogos reais registrados em `copa_2026_resultados.csv` alimentam as previsoes Copa-only
3. **Retreino manual**: voce clica "Treinar Agora" e o bot tenta encontrar uma configuracao melhor
4. **Aprendizado continuo**: a cada resultado fechado, o jogo entra no dataset — o proximo retreino tem mais dados

O modelo e salvo em `cerebro_bot.joblib` e **persiste entre sessoes**. Pode desligar o bot por dias e ele volta com a mesma inteligencia.

---

## Limitacoes conhecidas

- **API-Football plano gratuito**: 100 req/dia, 10 req/min, temporadas 2022-2024 apenas
- **Copa 2026**: dados precisam ser registrados manualmente (plano gratuito nao cobre temporada 2026)
- **Escanteios e cartoes**: estimados por heuristica quando nao ha dados reais disponiveis
- **Casa/Fora**: na Copa, a maioria dos jogos e em campo neutro (exceto EUA, Mexico e Canada)
- **Explicacao IA**: o Groq reescreve dados em linguagem natural mas **nao inventa informacoes** — se ele estiver offline, o bot mostra os dados tecnicos diretamente
- **Gols de jogador**: nao disponivel (requer dados individuais que o plano gratuito nao fornece)
