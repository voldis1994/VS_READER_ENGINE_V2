# P31–P45 arhitektūras audits

**Datums:** 2026-07-07  
**Apjoms:** P31–P45 (analysis, decision, risk/rules)  
**Avoti:** `docs/SYSTEM_SPECIFICATION.md`, `docs/IMPLEMENTATION_PLAN.md`  
**Metode:** Statiska koda un atkarību pārbaude. Kods nav mainīts.

---

## Kopsavilkums

Audits **nav pilnībā iziets**. P31–P45 funkcionalitāte un testi (330) ir stabili, un BUY/SELL/WAIT/EDGE arhitektūras virziens atbilst SYSTEM kā edge discovery platformai. Tomēr konstatētas specifikācijas līguma un uzturēšanas drift problēmas, kas nākamajos posmos (P46–P48, `run_live`) prasīs koncentrētus labojumus.

**Kritiskākie punkti:** `buy.py`/`sell.py` masīva dublēšanās (A3). **A1 (spread_filter_passed) — labots.** **A2 (konfigurācijas centralizācija) — labots.**

---

## Kas ir kārtībā

### Atbilstība IMPLEMENTATION_PLAN.md (fāžu apjoms)

| Fāze | Modulis | Statuss |
|------|---------|---------|
| P31 | `analysis/momentum.py` | Ieviests |
| P32 | `analysis/pressure.py` | Ieviests |
| P33 | `analysis/behavior.py` | Ieviests |
| P34 | `analysis/impact.py` | Ieviests |
| P35 | `analysis/engine.py` | Ieviests, fiksēta secība |
| P36 | `decision/reason.py` | Ieviests |
| P37–P39 | `decision/filters/*` | Ieviesti |
| P40–P41 | `decision/buy.py`, `sell.py` | Ieviesti |
| P42 | `decision/scorer.py` | Ieviests |
| P43 | `decision/wait_block.py` | Ieviests |
| P44 | `decision/engine.py` | Ieviests |
| P45 | `risk/rules.py` | Ieviests |

### BUY/SELL/WAIT/EDGE arhitektūra

- **Virzienu simetrija:** `run_decision_engine()` vienmēr aprēķina gan `buy_candidate`, gan `sell_candidate` pirms lēmuma (P44 tests to apstiprina).
- **Edge salīdzināšana, ne filtrēšana:** `scorer.compare_candidates()` salīdzina `buy_score` un `sell_score`; augstākais nosaka `preferred_side`. Scoring neizdod BLOCK un neizlaiž SELL.
- **WAIT nav noklusējums:** `evaluate_wait_decision()` atgriež WAIT tikai `BOTH_DIRECTIONS_INVALID`, `EQUAL_SCORES` vai `EXECUTION_NOT_POSSIBLE` gadījumā. Ja derīgs tikai viens virziens → `preferred_side` ir tas virziens, nevis WAIT.
- **Risks nav bailīgs WAIT-bots:** P45 `risk/rules.py` atgriež tikai `allowed=True/False` ar BLOCK reason kodiem (`RISK_*`, `ACCOUNT_NOT_TRADEABLE`). Risks neizdod WAIT.
- **Analysis slānis netirgo:** `analysis/*` neimportē `decision`, `risk` vai `execution`. `test_analysis_engine_does_not_call_decision_or_risk` to apstiprina.

### Atkarības un cikli

```
normalizer/protocol/state
        ↓
    analysis (P29–P35)
        ↓
    decision (P36–P44)  ← journal (error log)
        ↓
    risk/rules (P45)    ← decision.reason (tikai build_reason)
```

- **Cikliskas atkarības:** Nav konstatētas.
- **Aizliegtie importi (spec §389):** `analysis → decision/risk` nav. `loader → analysis/decision/risk` nav.

### Publiskā API konsekvence (daļēji)

- `engine/analysis/__init__.py` un `engine/decision/__init__.py` eksportē galvenās datu klases un `run_*` funkcijas konsekventi.
- `DecisionResult` lauki atbilst spec §52.3 (`decision_id`, `decision`, `reason`, `preferred_side`, kandidāti, score).
- `BuyCandidate` / `SellCandidate` struktūra ir simetriska (spec §47–48).

---

## A1. `AnalysisContext` trūkst `spread_filter_passed` (spec §58.3) — **LABOTS**

**Smagums:** Vidējs–augsts  
**Spec:** `SYSTEM_SPECIFICATION.md` §58.3 — “Ja spread nav pieņemams, analīzes kontekstā tiek atzīmēts `spread_filter_passed: false`.”  
**Statuss:** **A1 fixed** (2026-07-07)

### Bija

- `engine/analysis/context.py` — `AnalysisContext` nesaturēja `spread_filter_passed`.
- Spread filtrs (P37) darbojās atsevišķi `decision/filters/spread_filter.py`, bet konteksta objektā netika atspoguļots.
- `buy.py`/`sell.py` lasīja `spread_filter.spread_acceptable` tieši, nevis kontekstu.

### Labojums

- `AnalysisContext` paplašināts ar `spread_filter_passed: bool` un `to_dict()` / `from_dict()` serializāciju.
- `with_spread_filter_passed()` un `with_analysis_context()` atjaunina kontekstu uzreiz pēc spread filtra novērtēšanas `run_decision_engine()` plūsmā.
- `buy.py`/`sell.py` izmanto `analysis.context.spread_filter_passed` kā vienīgo avotu spread pass/fail stāvoklim.
- `DecisionResult` ietver `analysis_context`, lai lauks būtu pieejams visos lēmumu ceļos (BUY, SELL, WAIT, BLOCK).
- Testi: spread accepted/rejected, pilna decision pipeline propagācija.

### Sekas (pēc labojuma)

- Specifikācijas līgums starp analīzi un lēmumu posmu ir pilnīgāks.
- Dashboard/žurnāli var nolasīt spread filtra stāvokli no `AnalysisContext`.

---

## A2. Lēmumu un scoring parametri nav `config/system.json` shēmā — **LABOTS**

**Smagums:** Augsts (patch risks P46–P48, `run_live`)  
**Spec:** §46.5 (`analysis.weights`), §58.2 (`spread_relative_threshold`), §59.3 (`volatility_relative_threshold`), §60.2 (`block_high_impact_news`), §55–56 (`reward_ratio`, SL buffer)  
**Statuss:** **A2 fixed** (2026-07-07)

### Bija

- `protocol.models.AnalysisConfig` saturēja tikai `lookback_bars`.
- `protocol.models.RiskConfig` nesaturēja `reward_ratio`.
- `run_decision_engine()` saņēma kā brīvus argumentus: `weights`, `spread_threshold`, `volatility_threshold`, `block_high_impact_news`, `stop_loss_buffer`, `reward_ratio`.

### Labojums

- `config/system.json` un `AnalysisConfig` paplašināti ar: `spread_relative_threshold`, `volatility_relative_threshold`, `block_high_impact_news`, `stop_loss_buffer`, `weights` (`AnalysisWeights`).
- `RiskConfig` paplašināts ar `reward_ratio`.
- `run_decision_engine()` lasa parametrus no `system_config: SystemConfig` caur `engine/core/config.py` loader/validator.
- Testi: noklusētās vērtības, trūkstošo lauku kļūdas, decision flow izmanto config (ne hardcoded).

### Sekas (pēc labojuma)

- Konfigurācijas vienīgais avots (`config/system.json`) princips (spec §19) šiem parametriem tiek ievērots.
- Orchestrācijas slānis (`run_live`, P48) var ielādēt parametrus no config bez ad-hoc padošanas.

---

## A3. `buy.py` un `sell.py` masīva koda dublēšanās

**Smagums:** Vidējs  
**Plāns:** P40/P41 atsevišķi moduļi (pareizi), bet implementācija ir ~95% spoguļota.

### Dublētie bloki

- `_COMPONENT_KEYS`, `_round_price`, `calculate_*_score` (identiska loģika)
- Filtru ķēde (`spread` → `volatility` → `news` → `market_bars`) — identiska struktūra
- `_invalid_candidate` — identiska struktūra

### Sekas

- Jebkura filtra vai validācijas izmaiņa prasa sinhronizēt abus failus — augsts patch un regressijas risks.
- Nav dead code, bet ir strukturāla dublēšanās, kas apgrūtina uzturēšanu.

---

## A4. `risk` slānis importē `decision.reason`

**Smagums:** Zemējs–vidējs  
**Spec:** §389 — slāņu virziens: `decision → risk`, ne otrādi.

### Pierādījumi

- `engine/risk/rules.py:5` — `from engine.decision.reason import build_reason`

### Sekas

- Neliela slāņu inversija. `reason.py` ir utilīta, nevis lēmumu loģika, tāpēc praktiskā kaitējuma nav šodien.
- Ilgtermīnā `build_reason` loģiskāk dzīvotu `protocol` vai kopīgā `engine/reason` modulī, lai `risk` nebūtu atkarīgs no `decision`.

---

## A5. `TrendAnalysis` dublē `MomentumAnalysis` trend laukus

**Smagums:** Zems  
**Vieta:** `engine/analysis/engine.py`

### Pierādījumi

- `TrendAnalysis` satur `trend_direction`, `trend_strength`, `trend_duration_bars`, `higher_highs`, `lower_lows`.
- Tie paši lauki jau ir `MomentumAnalysis` (P31).
- `AnalysisEngineResult` glabā gan `momentum`, gan `trend` ar kopētiem datiem.

### Sekas

- Nav funkcionāla kļūda, bet lieks datu dublikāts un potenciāla neskaidrība API patērētājiem (`result.momentum.trend_direction` vs `result.trend.trend_direction`).

---

## A6. `resolve_preferred_side` un `compare_candidates` score avoti atšķiras

**Smagums:** Zems  
**Vieta:** `engine/decision/scorer.py`

### Pierādījumi

- `resolve_preferred_side()` lieto neapstrādātus `buy_candidate.buy_score` / `sell_candidate.sell_score`.
- `compare_candidates()` reizina abus ar `context.context_quality` pirms `preferred_side` noteikšanas.

### Sekas

- `preferred_side` secība parasti saglabājas (simetriska reizināšana), bet publiskais API atgriež atšķirīgus score lielumus atkarībā no izsauktās funkcijas.
- `decision/engine.py` izmanto tikai `compare_candidates()`, nevis `resolve_preferred_side()` — nav runtime kļūdas, bet API dokumentācijas/līguma neskaidrība.

---

## A7. `RiskContext` metrikas nav saistītas ar persistētu avotu

**Smagums:** Zemējs (gaidāms P48+)  
**Spec:** §53.3 — risk engine ievade ietver status un instance state.

### Pierādījumi

- `RiskContext` satur `daily_loss_percent` un `drawdown_percent`, kas tiek padoti no ārpuses.
- Nav moduļa, kas šīs vērtības aprēķina no trade journal, state vai status.

### Sekas

- P45 apjomā pareizi (tikai noteikumu definīcijas), bet integrācijā (P48) obligāti jāievieš metrikas avots — citādi `run_live` patch.

---

## A8. Testa faila nosaukums atšķiras no plāna (P44)

**Smagums:** Niecs  
**Plāns:** `tests/decision/test_engine.py`  
**Faktiski:** `tests/decision/test_decision_engine.py`

### Iemesls

- Pytest importa konflikts ar `tests/analysis/test_engine.py`.

### Sekas

- Nav funkcionālas ietekmes. Dokumentācijas/plāna atšķirība.

---

## Pārbaudes, kas **nav** problēmas

| Jautājums | Secinājums |
|-----------|------------|
| Vai sistēma ir kļuvusi par bailīgu WAIT-default botu? | **Nē.** WAIT ir ierobežots; risks dod BLOCK; viens derīgs virziens dod BUY/SELL. |
| Vai Decision Engine dod vienpusēju signālu? | **Nē.** Abi virzieni tiek aprēķināti un salīdzināti ar scoring. |
| Vai ir dead code P31–P45? | **Nav būtiska.** `resolve_preferred_side` ir publisks P42 API, lietots testos. |
| Vai P45 risk rules integrētas decision engine? | **Vēl ne** — paredzēts P48; nav P31–P45 apjoma kļūda. |
| Vai filtri izraisa BLOCK tieši decision engine? | **Nē** — filtri atzīmē kandidātu `valid=false`; BLOCK tikai caur `evaluate_block_decision(block_reason=...)`. Atbilst spec §58.3 virziena invalidācijai. |

---

## Testu stāvoklis

```
340 passed (P01–P45, A1–A2)
```

Testi apstiprina fāžu funkcionalitāti, A1 spread konteksta lauku un A2 config centralizāciju; A3–A8 specifikācijas driftu vēl sedz daļēji.

---

## Kopējais secinājums

P31–P45 audits **nav pilnībā iziets** konstatēto problēmu dēļ (īpaši **A3**). **A1 un A2 ir laboti.**

Arhitektūras virziens — simetriska BUY/SELL edge discovery ar atsevišķu riska BLOCK slāni — ir **saglabāts** un atbilst SYSTEM filozofijai. Problēmas ir galvenokārt **līguma pilnīguma** un **integrācijas gatavības**, nevis fundamentālas lēmumu arhitektūras kļūdas.

**Ieteicamā secība labojumiem (ārpus šī audita):**
1. ~~Pievienot `spread_filter_passed` kontekstam (A1).~~ **Done.**
2. ~~Paplašināt `AnalysisConfig` / `RiskConfig` ar spec parametriem (A2).~~ **Done.**
3. Pārdomāt `buy`/`sell` kopīgo kodu pirms P48, lai samazinātu dublēšanu (A3).
