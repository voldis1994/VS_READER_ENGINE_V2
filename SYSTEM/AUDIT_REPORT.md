# P01–P05 koda audits

**Datums:** 2026-07-07  
**Apjoms:** P01 (projekta pamats), P02 (konstantes un kļūdas), P03 (modeļi), P04 (parseris), P05 (writer)  
**Avoti:** `docs/SYSTEM_SPECIFICATION.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/RULES.md`

**Tests:** 106/106 iziet (`tests/protocol/`)

---

## Kopsavilkums

Audits **nav iziets bez arhitektūras problēmām**. Konstatētas 4 būtiskas neatbilstības un 2 mazākas riska zonas. Protokola moduļa slāņošana (constants → errors → models → parser/writer), ciklisko atkarību neesamība un specifikācijas §19–§20 lauku pārklājums modeļos ir korekti. Galvenās problēmas skar kļūdu līgumu parserī, ACK statusu validāciju un publiskā API konsekvenci.

---

## A1. `parse_system_config` izraisa `KeyError`/`TypeError`, nevis `ProtocolError`

| | |
|---|---|
| **Smagums** | Augsts |
| **Vieta** | `engine/protocol/parser.py` — `parse_system_config()` |
| **Specifikācija** | P04 prasība: nederīgs saturs izraisa `ProtocolError`; §28, §91.3 |
| **Apraksts** | Top-level sekcijas (`system`, `paths`, `runtime` u.c.) tiek nolasītas ar `_require_key()`, bet iekšējie lauki tiek lasīti ar tiešu indeksēšanu (`item["account_id"]`, `system_data["name"]` u.tml.). Trūkstošs vai nepareiza tipa iekšējais lauks izraisa `KeyError` vai `TypeError`, nevis `ProtocolError`. |
| **Pierādījums** | `instances: [{}]` → `KeyError: 'account_id'`; `system: "not-a-dict"` → `TypeError`. Citi parseri (`parse_status`, `parse_control` u.c.) izmanto `_require_key()` konsekventi. |
| **Risks** | Augstāki moduļi (P09 `core/config.py`, P13+ loaderi) nevar uzticami noķert visas protokola kļūdas kā `ProtocolError`; atšķiras no P04 līguma un testēšanas gaidām. |
| **Ieteikums** | P04 labojums: visām `parse_system_config` iekšējām vērtībām izmantot `_require_key()` un tipu pārbaudes ar `ProtocolError` pārveidi (bez jaunas funkcionalitātes, tikai kļūdu līguma vienotība). |

---

## A2. `AckStatus.TIMEOUT` pieļauts ārējā protokolā, kur specifikācija to aizliedz

| | |
|---|---|
| **Smagums** | Augsts |
| **Vieta** | `engine/protocol/constants.py` (`AckStatus`, `is_valid_ack_status`); `engine/protocol/models.py` (`AckRecord`, `TradeJournalEntry`) |
| **Specifikācija** | §19.5 ACK JSON: `status` ∈ {SUCCESS, FAILED, REJECTED}; §19.9 trade journal: `ack_status` ∈ {SUCCESS, FAILED, REJECTED}; §79.2 `TIMEOUT` ir **iekšējs** `last_ack_status` stāvoklis, nevis MT4 ACK fails |
| **Apraksts** | `AckStatus` enum satur `TIMEOUT`, un `is_valid_ack_status()` to uzskata par derīgu. `AckRecord` un `TradeJournalEntry` validācija izmanto šo helperi, tādējādi parsers un modeļi pieņem `TIMEOUT` ārējā JSON/JSONL formātā. |
| **Risks** | P51 (`trade_journal`) un P54 (`ack_reader`) var neapzināti serializēt/pieņemt nederīgu ārējo statusu; MT4 ACK un trade journal neatbildīs specifikācijas robežām; būs jāšķir iekšējais stāvoklis no vadu formāta. |
| **Ieteikums** | Atseviot ārējā protokola statusu kopu (SUCCESS/FAILED/REJECTED) no iekšējā stāvokļa (`TIMEOUT`); `AckRecord` un `TradeJournalEntry` validācijai izmantot tikai ārējo kopu. |

---

## A3. Publiskais API `engine/protocol/__init__.py` nav konsekvents pēc P05

| | |
|---|---|
| **Smagums** | Vidējs |
| **Vieta** | `engine/protocol/__init__.py` |
| **Specifikācija** | P02: konstantes un kļūdas ir «eksportējamas» caur `__init__.py`; P05: `protocol` modulis ir «pilnībā pabeigts»; §6: protocol atbild par modeļiem, parsēšanu un rakstīšanu |
| **Apraksts** | `__init__.py` eksportē tikai P02 saturu (konstantes + `errors`). P03–P05 pievienotie modeļi, parsera un writer funkcijas nav iekļautas `__all__` un nav pieejamas kā `from engine.protocol import ...`. Testi un nākamie moduļi importē tieši no apakšmoduļiem (`engine.protocol.models`, `engine.protocol.parser`, `engine.protocol.writer`). |
| **Risks** | Divi paralēli importa modeļi vienam modulim; neskaidra publiskā robeža; P13+ implementētāji var neapzināti izvēlēties nekonsekventu importa stilu. |
| **Ieteikums** | Pēc P05 `__init__.py` jāpapildina ar visu publisko protocol API (modeļi, parse_*, write_*) vai jādokumentē apzināts lēmums par apakšmoduļu importiem. |

---

## A4. Nosaukumu standartu nekonsekvence: `key` pret `instance_key`

| | |
|---|---|
| **Smagums** | Zems–vidējs |
| **Vieta** | `engine/protocol/models.py` |
| **Specifikācija** | §92.3 (`snake_case` īpašībām); §92.7 instance atslēga kā `(account_id, symbol, magic)` |
| **Apraksts** | `InstanceDefinition` izmanto īpašību `.key`, bet visi pārējie modeļi ar instance identitāti izmanto `.instance_key` (`ControlCommand`, `AckRecord`, `InstanceStateRecord`, `SpreadStateRecord`, `DecisionJournalEntry`, `TradeJournalEntry`). |
| **Risks** | P08 (`core/instance.py`) un P25 (`state/instance_state.py`) izstrādātājiem jāatceras divi dažādi API nosaukumi vienai semantikai. |
| **Ieteikums** | Vienot uz `instance_key` visos modeļos. |

---

## A5. Dublēti obligāto lauku saraksti `writer.py`

| | |
|---|---|
| **Smagums** | Zems |
| **Vieta** | `engine/protocol/writer.py` — `*_REQUIRED_FIELDS`, `required_fields_present()` |
| **Apraksts** | Obligāto lauku saraksti atkārto specifikācijas §19 laukus un faktiski dublē parsera `_require_key()` izsaukumu sarakstus. Šobrīd galvenokārt izmanto testos (`test_writer.py`). |
| **Risks** | Shēmas izmaiņas prasīs sinhronizāciju trim vietām (modeļi, parsers, writer konstantes) — patch risks. |
| **Ieteikums** | Ilgtermīnā lauku metadatus turēt vienā avotā (piem., modeļos vai `constants.py`); nav bloķējošs P05 pabeigšanai. |

---

## A6. Specifikācijas iekšējā atstarpe: `RuntimeConfig` pret vēlāk minētiem `runtime.*` laukiem

| | |
|---|---|
| **Smagums** | Zems (informatīvs) |
| **Vieta** | `engine/protocol/models.py` — `RuntimeConfig`; `docs/SYSTEM_SPECIFICATION.md` §19.1 pret §78.2, §79.1, §68 |
| **Apraksts** | `RuntimeConfig` implementē tieši §19.1 laukus (`cycle_interval_ms`, `ack_timeout_ms`, `retry_max`, `auto_discover_instances`). Citās specifikācijas sadaļās minēti arī `retry_delay_ms`, `data_stale_threshold_ms`, `cycle_max_duration_ms`, `metrics_interval_ms`, kas §19.1 tabulā nav. |
| **Risks** | P09/P10 implementācijā būs jāpaplašina `RuntimeConfig` un/vai jāprecizē specifikācijas §19.1 — potenciāls patch posms. |
| **Piezīme** | Pašreizējā P03 implementācija ir korekta attiecībā pret §19.1; problēma ir specifikācijas pilnīgumā, nevis lauku interpretācijā. |

---

## Kas ir kārtībā (pozitīvie atradumi)

| Kritērijs | Rezultāts |
|-----------|-----------|
| Arhitektūras slāņi (§6–§7) | `protocol` neimportē augstākus moduļus; atkarību virziens atbilst |
| Cikliskas atkarības | Nav (constants ← errors ← models ← parser/writer) |
| Specifikācijas §19–§20 modeļi | Visi JSON/CSV objekti definēti; kolonnu secība no `MARKET_CSV_COLUMNS` / `SENSOR_CSV_COLUMNS` |
| Kļūdu hierarhija (P02) | `SystemError` → specializētie tipi; `wrap_exception`, `get_error_type` |
| Mirušais kods | Nav neizmantotu publisku funkciju produkcijas ceļā; `validate_instance_key` un `required_fields_present` izmanto testi |
| Nosaukumi (§92) | Moduļi `snake_case`, klases `PascalCase`, konstantes `UPPER_SNAKE_CASE` — atbilst (izņemot A4) |
| P01 | `requirements.txt` (Python 3.11+, pytest, psutil), `README.md` operacionālais minimums |
| Round-trip | Writer ↔ parser testi iziet visiem formātiem |
| Universe aizliegtie lauki | Pārbaudīti parserī (root) un modeļos (`metadata`) |

---

## Secinājums

P01–P05 ir funkcionāli stabili (106 testi), bet **arhitektūras audits konstatē problēmas**, kas jānovērš pirms P06+ turpināšanas:

1. **A1** — `ProtocolError` līguma pārkāpums `parse_system_config` (obligāti)
2. **A2** — `TIMEOUT` statusa jaukšana ārējā un iekšējā līmenī (obligāti)
3. **A3** — nepilnīgs publiskais API `__init__.py` (ieteicams)
4. **A4** — `key` / `instance_key` nosaukumu vienotība (ieteicams)

A5 un A6 ir uzturēšanas un specifikācijas precizēšanas riski, nevis funkcionāli bojājumi pašreizējā posmā.
