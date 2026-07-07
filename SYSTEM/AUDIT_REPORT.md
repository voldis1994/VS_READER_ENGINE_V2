# P01–P30 arhitektūras audits

**Datums:** 2026-07-07  
**Apjoms:** P01–P30  
**Avoti:** `docs/SYSTEM_SPECIFICATION.md`, `docs/IMPLEMENTATION_PLAN.md`

---

## Kopsavilkums

Audits **nav pilnībā iziets**. Atrastas vairākas būtiskas neatbilstības P21–P30 implementācijā, kas ietekmē:

- atbilstību specifikācijas cache/journal/state principiem,
- publiskā API konsekvenci starp `state` un `protocol`,
- dead code/dublēšanas risku.

Kritiskākie punkti: `core/cache.py` faktiski nav integrēts darba plūsmā, `error_journal` nav reāli append-only implementācijas ziņā, un `instance_state` formāts ir nekonsekvents ar esošo protocol state API.

---

## A1. P27 cache modulis nav integrēts (dead code + arhitektūras dublēšanās)

**Smagums:** Augsts  
**Spec/Plāns:** `IMPLEMENTATION_PLAN.md` P27; `SYSTEM_SPECIFICATION.md` §30.5, §75 (cache hash kā I/O optimizācijas mehānisms)

### Pierādījumi

- `engine/core/cache.py` ir izveidots, bet netiek izmantots loaderos.
- Meklējums pēc lietojuma:
  - `engine/core/__init__.py` importē `core.cache`
  - citos moduļos `core.cache` netiek importēts.
- `market_loader.py` un `sensor_loader.py` uztur **atsevišķu iekšējo cache** (`_CacheEntry`, `_content_hash`) neatkarīgi no P27 moduļa.

### Sekas

- P27 modulis praktiski ir neizmantots produkcijas plūsmā (dead code risks).
- Vienlaicīgi pastāv 2 cache pieejas (loader-lokālā un `core/cache.py`) → dublēšanās un patch risks nākamajos posmos.

---

## A2. `core/cache.py` neatbilst pašas specifikācijas modified-time prasībai

**Smagums:** Vidējs  
**Spec/Plāns:** `SYSTEM_SPECIFICATION.md` §75 (“hash tiek salīdzināts ar faila modified time; konflikta gadījumā prioritāte ir saturs”)

### Pierādījumi

- `engine/core/cache.py:32` aprēķina `current_mtime_ns`, bet neizmanto lēmumā.
- `should_reload(...)` atgriež tikai `cached["hash"] != current_hash`.
- `modified_ns` tiek glabāts (`write_hash`) un parsēts (`parse_hash_record`), bet faktiski netiek izmantots.

### Sekas

- Prasība par hash+mtime salīdzināšanu nav pilnībā realizēta.
- Modulis satur daļēji “nepabeigtu” loģiku (future patch indicator).

---

## A3. P28 Error Journal nav īsti append-only ieviešanas līmenī

**Smagums:** Augsts  
**Spec/Plāns:** `IMPLEMENTATION_PLAN.md` P28 (“Append-only”); `SYSTEM_SPECIFICATION.md` §19.10, §65, §1147 (journal faili append-only)

### Pierādījumi

- `engine/journal/error_journal.py:21-28`:
  - nolasa visu esošo failu saturu,
  - pievieno jaunu rindu atmiņā,
  - pārraksta visu failu ar `atomic_write_text(...)`.

### Sekas

- Semantiski saturs tiek pievienots, bet implementācija ir “read+rewrite whole file”, nevis īsta append pieeja.
- Pie konkurējošas rakstīšanas iespējami lost-update scenāriji.
- Lieliem journal failiem aug I/O izmaksas.

---

## A4. P25 `instance_state` publiskais API nav konsekvents ar protocol state API

**Smagums:** Augsts  
**Spec/Plāns:** `IMPLEMENTATION_PLAN.md` P25; `SYSTEM_SPECIFICATION.md` §19.6 un §72.3; publiskā API konsekvence

### Pierādījumi

- `engine/state/instance_state.py` raksta state ar papildu laukiem:
  - `last_command_id`, `last_ack_status`, `instrument_digits`, `instrument_point`, `instrument_pip`, `cycle_count`.
- `engine/protocol/models.py::InstanceStateRecord` / `parse_instance_state` / `write_instance_state` šos laukus neaptver kā vienotu modeli.
- Tātad vienā repo pastāv 2 daļēji atšķirīgi “instance state” kontrakti.

### Sekas

- Nekonsekvents publiskais API starp `state` un `protocol` slāņiem.
- Palielināts risks nākamajiem moduļiem (daži izmantos `state.InstanceState`, citi `protocol.InstanceStateRecord`).

---

## A5. BUY/SELL/WAIT/EDGE arhitektūras gatavība: daļēja, bet nav degradēta uz “parastu MT4 robotu”

**Smagums:** Novērojums (ne bloķējošs)

### Secinājums

- Šajā posmā nav pazīmju, ka analysis moduļi paši sāktu izpildīt trade komandas.
- `analysis/context.py` un `analysis/structure.py` ģenerē analītisku izvadi, nevis order darbības.
- Aizliegto importa virzienu pārkāpumi (analysis→decision/risk/execution, loader→analysis/decision/risk/execution) netika konstatēti.

### Piezīme

- Pilna BUY/SELL/WAIT/EDGE plūsmas verifikācija būs iespējama pēc decision/risk/execution posmu ieviešanas.

---

## Kas ir kārtībā

- Cikliskas atkarības acīmredzami netika konstatētas auditētajā P01–P30 modulī.
- `protocol/__init__.py` publiskais eksports ir plašs un konsekvents.
- `analysis` slānis šobrīd nav sācis tieši tirgot.
- Testu kopa lokāli iziet, taču tests šobrīd nepietiekami noķer A1–A4 arhitektūras driftu.

---

## Kopējais secinājums

P01–P30 audits atklāj būtiskas arhitektūras neatbilstības (A1–A4), tāpēc rezultāts nav “pilnībā iziets”.
