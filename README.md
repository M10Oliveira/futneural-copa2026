# FutNeural — Bot Preditivo Copa do Mundo 2026

Bot com interface grafica (CustomTkinter) que preve resultados de jogos
da Copa do Mundo 2026 combinando modelo de Poisson com Rede Neural (MLP).

## Estrutura

| Arquivo | Funcao |
|---|---|
| `config.py` | Constantes, paths, carregamento de chaves API |
| `api_football.py` | API-Football (rate limiting, cache) + Groq (traducao de nomes, fallback) |
| `modelo.py` | Treino do modelo MLP, calculo Poisson, blend, previsao, Excel I/O |
| `gerar_dataset.py` | Gera dataset de treino a partir de jogos reais (API-Football) |
| `gui.py` | Interface grafica — ponto de entrada principal |
| `config_local.py` | Suas chaves de API (nao versionado) |

## Instalacao

```bash
pip install requests joblib scikit-learn pandas numpy scipy openpyxl groq customtkinter
```

## Configuracao

1. Crie conta gratuita em https://dashboard.api-football.com/register
2. Copie `config_local.example.py` para `config_local.py`
3. Preencha `FOOTBALL_API_KEY` (obrigatoria) e `GROQ_API_KEY` (opcional)

## Como usar

```bash
# 1. Gerar dataset de treino (roda uma vez, resultados ficam cacheados)
python gerar_dataset.py

# 2. Abrir a interface grafica
python gui.py
```

### Abas da GUI

- **Nova Previsao**: digite os dois times e veja probabilidades, xG e escanteios
- **Jogos da Copa**: registre resultados reais da Copa 2026 — o bot usa esses
  dados para calcular a forma atual de cada selecao no torneio
- **Resultados**: sincronize previsoes com resultados reais (automatico via API
  para jogos 2022-2024, manual para Copa 2026)
- **Tabela de Grupos**: classificacao atual dos grupos
- **Status APIs**: diagnostico das chaves e cota restante

## Dados da Copa 2026

O plano gratuito da API-Football so cobre temporadas de 2022 a 2024.
Para usar dados reais da Copa 2026, registre os resultados na aba
"Jogos da Copa" — eles ficam salvos em `copa_2026_resultados.csv` e sao
usados automaticamente nas previsoes.

## Limitacoes

- Plano gratuito: 100 req/dia, 10 req/min (rate limiting automatico incluso)
- Escanteios sao estimados por heuristica (sem fonte de dados real)
- "Casa"/"Fora" refletem o calendario oficial — maioria dos jogos e em campo neutro
