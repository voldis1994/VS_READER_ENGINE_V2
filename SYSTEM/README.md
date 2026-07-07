# SYSTEM

Pilnīgi jauna, daudzkontu un daudzinstrumentu M1 tirdzniecības platforma. Python pieņem visus lēmumus. MT4 eksportē datus un izpilda orderus. Dashboard tikai attēlo stāvokli.

Projekta sakne: `C:\SYSTEM`

## Prasības

| Komponents | Versija |
|------------|---------|
| Python | 3.11 vai jaunāks |
| MetaTrader 4 | Ar `SYSTEM_EA.mq4` |
| OS | Windows (MT4 datu ceļi) |

## Uzstādīšana

### Automātiski (Windows — ieteicams)

1. Lejupielādējiet `scripts/install_windows.bat` un `scripts/install_windows.ps1` no GitHub
2. Dubultklikšķis uz `install_windows.bat`
3. Pēc instalācijas viss būs mapē `C:\SYSTEM`

Ar MT4 failu kopēšanu:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1 `
  -Mt4DataPath "C:\Users\JŪSU_VĀRDS\AppData\Roaming\MetaQuotes\Terminal\XXXXXXXX\MQL4"
```

Papildu instrukcijas: `scripts/LEJUPIELADE.txt`

### Manuāli

```bash
cd C:\SYSTEM
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Linux/macOS izstrādes vidē:

```bash
cd /path/to/SYSTEM
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Pārbaude

```bash
python --version
pip install -r requirements.txt
pytest
```

`python --version` jābūt 3.11 vai jaunākam.

## Projekta struktūra

```
SYSTEM/
├── config/system.json      Vienīgā konfigurācija
├── data/                   Visi runtime dati
├── docs/                   Noteikumi, specifikācija, plāns
├── engine/                 Python loģika
├── mql4/                   MT4 EA
├── tests/                  Automatizētie testi
├── run_live.py             Live engine
└── dashboard.py            Dashboard
```

## Dokumentācija

| Dokuments | Mērķis |
|-----------|--------|
| `docs/RULES.md` | Obligātie sistēmas noteikumi |
| `docs/SYSTEM_SPECIFICATION.md` | Tehniskā specifikācija |
| `docs/IMPLEMENTATION_PLAN.md` | Izstrādes plāns (P01–P75) |

## Palaišana

```bash
python run_live.py
python dashboard.py
```

Pilna LIVE palaišana prasa pabeigtu `docs/IMPLEMENTATION_PLAN.md` līdz P74 un P75 audit fix posmu.

## Instance modelis

Katra izolēta instance ir definēta kā:

```
Account + Symbol + Magic
```

Katrai instancei ir savs state, spread modelis, journal, risks un execution kanāls.
