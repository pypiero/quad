# Come funziona il notebook — guida completa alla logica

Documento di studio: spiega **tutto** quello che c'è nel codice, cella per cella, con il perché delle
scelte. Non sostituisce il codice, lo rende leggibile.

Indice:

1. [Il problema in una pagina](#1-il-problema-in-una-pagina)
2. [Le tre chiavi di tutto il processo](#2-le-tre-chiavi-di-tutto-il-processo)
3. [Mappa del flusso](#3-mappa-del-flusso)
4. [Glossario dei codici](#4-glossario-dei-codici)
5. [Le 16 sezioni, una per una](#5-le-16-sezioni-una-per-una)
6. [Il blocco finale: il report](#6-il-blocco-finale-il-report)
7. [Le colonne di stato: come leggere il risultato](#7-le-colonne-di-stato-come-leggere-il-risultato)
8. [Casi limite e decisioni di progetto](#8-casi-limite-e-decisioni-di-progetto)
9. [Come si cerca un errore](#9-come-si-cerca-un-errore)
10. [Cosa il codice non fa](#10-cosa-il-codice-non-fa)
11. [Appendice: colonne di ogni tabella](#11-appendice-colonne-di-ogni-tabella)

---

## 1. Il problema in una pagina

Ci sono due sistemi che raccontano lo stesso fatto con parole diverse.

| | Fattura elettronica (XML) | Carichi (gestionale) |
|---|---|---|
| Arriva da | il fornitore, via SdI | l'operatore che registra la merce |
| Identifica il documento | nome file `CEAS` + numero fattura | campi `CEAS` + `NDOGIAA` |
| Identifica l'articolo | codici del fornitore (`CodiceArticolo`) | codici interni (`CART`, `CALA`, `CEAN`) |
| Identifica il trasporto | `NumeroDDT` nell'XML | campo `NDOGIAB` |
| Quantità e importi | dichiarati dal fornitore | registrati in accettazione |

Nessuno dei tre identificativi coincide mai per costruzione, perché sono tre **rappresentazioni**
dello stesso dato:

```
codice articolo:  XML "art-002"   ↔  carico CALA "ART-002"   ↔  carico CART "C002"
numero DDT:       XML "A/001"     ↔  carico NDOGIAB "A-001"
```

La riconciliazione consiste nel ricondurre le due rappresentazioni a una **chiave comune**, e poi
confrontare le misure. Le chiavi comuni sono tre, e sono l'intera architettura del notebook:

1. **documento** → `CEAS + numero fattura` (nessuna normalizzazione: sono codici tecnici);
2. **DDT** → numero normalizzato, con tre livelli di sicurezza (testo, data, residuo unico);
3. **articolo** → cascata `EAN → CART → CALA`.

Il risultato è un **full outer**: non si perde nulla. Ogni riga racconta cosa è successo, e le
colonne di stato dicono perché.

---

## 2. Le tre chiavi di tutto il processo

### 2.1 Documento: `CEAS + NDOGIAA`

`CEAS` è l'archiviazione ottica: **coincide con il nome del file XML senza `.xml`**.

```
IT01111111111_00001.xml  →  CEAS = "IT01111111111_00001"
```

Questo legame è la ragione per cui il notebook può permettersi di ignorare cosa c'è dentro il nome
del file: qualunque cosa sia, è la stessa stringa sull'altro lato.

`NDOGIAA` è il numero fattura, preso da `DatiGeneraliDocumento/Numero` e confrontato **così com'è**
(trim, stringa). Non viene normalizzato: è un identificativo, non un valore da interpretare.

Questa coppia serve a **due** cose:

- definire il **perimetro** (sezione 8): quali carichi entrano nel processo;
- ricavare il **CFOR lato XML** (sezione 11): l'XML non contiene il codice fornitore, quindi si
  guarda che fornitore ha quel determinato documento nei carichi.

### 2.2 DDT: numero normalizzato + tre livelli

Il numero DDT è il campo più sporco di tutti, perché nasce da una digitazione manuale. Lo stesso
trasporto può essere scritto `A/001`, `A-1`, `001`, `A 001`, `A/001/2024`.

La normalizzazione è governata dal **dizionario**, fornitore per fornitore, e produce una colonna
`*_Chiave`. Se il confronto sul testo fallisce, si prova la **data**, e infine si sfrutta il fatto
che in una fattura di solito c'è un solo DDT per lato.

### 2.3 Articolo: cascata EAN → CART → CALA

L'XML può contenere più codici per la stessa riga, con tipi diversi (`EAN`, `FORN`, `CLI`, …). Il
dizionario traduce ogni tipo in un **campo canonico** (`EAN`, `CODICE_CLIENTE`, `CODICE_FORNITORE`),
cioè nel nome della colonna su cui confrontarlo. Sul lato carichi ci sono gli stessi tre campi:
`CEAN`, `CART`, `CALA`.

Il confronto procede a cascata: si usa il primo livello che trova qualcosa.

| Livello | Lato XML | Lato carico | Note |
|---|---|---|---|
| 1 | `EAN` | `CEAN` | il più affidabile, quando c'è |
| 2 | `CODICE_CLIENTE` | `CART` | codice interno, stabile |
| 3 | `CODICE_FORNITORE` | `CALA` (da `CARF`) | ripiego, dipende dalla mappatura |

---

## 3. Mappa del flusso

```
                    ┌─────────────────────┐
     xml.zip ──────►│ [2] lettura XML     │
                    │  solo FPR12         │
                    │  -Allegati          │
                    └──────────┬──────────┘
                               │ xml_in_memoria
                    ┌──────────▼──────────┐
                    │ [3] esplosione      │
                    └──────────┬──────────┘
                 ┌─────────────┴──────────────┐
                 ▼                            ▼
        df_xml_fatture                df_xml_codici_articolo
      (1 riga per linea)              (1 riga per codice)
                 │                            │
                 │ [11] CFOR + DDT            │ [12] normalizzazione
                 │                            ▼
                 │                     (CampoCanonico, valore normalizzato)
                 │                            │
                 │                    [13] pivot + aggregazione
                 │                            ▼
                 │                     df_xml_righe
                 │                  (1 riga per articolo/DDT)
                 │                            │
                 └──────────────┬─────────────┘
                                ▼
                          [14] map_ddt
                    (DDT XML ↔ DDT carico)

  Excel carichi ──► [7] lettura + tipi + filtro CDOCIAA
                                │
                          [8] perimetro ──────────┘ (inner join con le testate XML)
                                │
                          [9] anagrafiche (CPCO, EAN, CARF→CALA)
                                │
                          [10] NDOGIAB_Chiave
                                ▼
                            df_fatture
                                │
                                ▼
                    [15] merge: full outer
                                ▼
                            df_merge ──► [16] export diagnostico
                                │
                                ▼
                    blocco finale: df_powerbi ──► export report
```

### Granularità delle tabelle

| Tabella | Una riga per | Quando nasce |
|---|---|---|
| `xml_in_memoria` | file XML | [2] |
| `df_xml_fatture` | linea di fattura | [3] |
| `df_xml_codici_articolo` | codice articolo | [3] |
| `df_xml_righe` | articolo dentro un DDT | [13] |
| `df_fatture` | riga di carico | [7]-[10] |
| `map_ddt` | coppia DDT XML ↔ DDT carico | [14] |
| `df_merge` | riga riconciliata (XML, carico o entrambe) | [15] |
| `df_powerbi` | come `df_merge`, 24 colonne | blocco finale |

**Questo è il punto più importante da capire**: i due lati arrivano al merge con granularità
diverse. L'XML parte da *linee* e arriva ad *articoli*; i carichi partono già da *articoli*. Se le
due granularità non coincidessero, il full outer produrrebbe duplicati a valanga. La sezione [13]
esiste esattamente per questo.

---

## 4. Glossario dei codici

| Codice | Significato | Dove vive |
|---|---|---|
| `CFOR` | codice fornitore | carichi; sull'XML va ricavato |
| `CEAS` | archiviazione ottica = nome file XML senza estensione | entrambi |
| `NDOGIAA` | numero documento (fattura) | entrambi |
| `NDOGIAB` | numero DDT | carichi |
| `TDATIAA` / `TDATIAB` | data fattura / data DDT | carichi |
| `CDOCIAA` | tipo documento; il perimetro è `60I` | carichi |
| `CART` | codice articolo interno | carichi |
| `CALA` | codice articolo fornitore "grezzo" | carichi |
| `CARF` | codice articolo fornitore da anagrafica | anagrafica |
| `CEAN` | codice EAN | anagrafica EAN → carichi |
| `CPCO` / `XPCO` | punto di consegna / sua descrizione | anagrafica PDV |
| `TDEC` | data validità anagrafica articolo fornitore | anagrafica CARF |

Colonne tecniche create dal notebook:

| Colonna | Significato |
|---|---|
| `ChiaveRigaXML` | identificativo della linea XML (progressivo) |
| `Indice` | identificativo della riga di carico nel perimetro (progressivo, da 1) |
| `*_Chiave` | valore normalizzato dal dizionario |
| `ID_Riga_XML` | identificativo della riga XML dopo il merge con `map_ddt` |
| `ID_Riga_Ordine` | `Indice` della riga carico agganciata a una riga XML |
| `ChiaveDDT_Comune` | `CFOR + NumeroFattura + ChiaveDDT_Carico` |

---

## 5. Le 16 sezioni, una per una

Ogni sezione nel codice è marcata da `# %% [n]`.

### [1] Configurazione

Un unico punto in cui si dichiara dove stanno le cose. Nessuna logica.

| Variabile | Uso |
|---|---|
| `cartella` | percorso OneLake (abfss://…) |
| `SOURCE_TYPE` | `"excel"` (attivo) o `"table"` (futuro: `spark.table(TABLE_NAME)`) |
| `CARICHI_FILE`, `CARICHI_SHEET` | Excel dei carichi |
| `CDOCIAA_FILTRO` | `"60I"`, il perimetro |
| `zip_path`, `zip_locale_python` | ZIP degli XML e sua copia locale |
| `percorso_dizionari` | Excel con le regole |
| `CPCO_FILE`, `EAN_FILE`, `CARF_FILE` | anagrafiche |

**Perché è separata**: quando i carichi arriveranno dal database basterà cambiare `SOURCE_TYPE` e
`TABLE_NAME`, senza toccare il resto.

### [2] Lettura degli XML

Passi:

1. copia `xml.zip` da OneLake in locale (`notebookutils.fs.cp`);
2. `zipfile.ZipFile.testzip()` per escludere archivi corrotti;
3. selezione dei soli file `.xml` (anche in sottocartelle);
4. per ciascuno, parsing con `ET.fromstring` (gestisce da sé la codifica dichiarata);
5. **scarto dei documenti non `FPR12`** (attributo `versione` sulla radice);
6. **rimozione dei blocchi `<Allegati>`** da ogni `FatturaElettronicaBody`;
7. memorizzazione in `xml_in_memoria` come `{"File", "Path", "Root"}`;
8. conteggio degli XML per fornitore (denominazione letta dall'intestazione).

**Perché si tolgono gli allegati**: contengono i PDF delle fatture, a volte diversi MB ciascuno. Il
notebook non li usa: tenerli in memoria moltiplicherebbe l'occupazione senza alcun beneficio.

**Perché si scarta `FPR12` diverso**: il processo è tarato sulle fatture verso privati. I documenti
`FPA12` (verso PA) hanno struttura simile ma codici destinatario diversi; escluderli è una scelta
esplicita, non una dimenticanza.

Il `finally` cancella sempre la copia locale dello ZIP, anche in caso di errore.

### [3] Esplosione in linee e codici

È la sezione che trasforma l'albero XML in tabelle. Produce due DataFrame contemporaneamente,
perché un solo passaggio sui documenti è più economico di due.

**Per ogni file, e per ogni `FatturaElettronicaBody`** (un file può contenerne più di uno: sono
documenti distinti, numerati da `IndiceBodyXML`):

- legge la **denominazione del fornitore** dall'intestazione (`CedentePrestatore/…/Denominazione`,
  con ripiego `Nome` + `Cognome` per le persone fisiche) e la riporta su ogni riga;
- legge i dati generali: `TipoDocumento`, `Divisa`, `Data` → `DataFattura`, `Numero` → `NumeroFattura`;
- legge i **blocchi DatiDDT** e costruisce due mappe:
  - `ddt_espliciti_per_linea`: numero linea → elenco di `NumeroDDT` che la citano;
  - `ddt_impliciti`: `NumeroDDT` che non citano alcuna linea.

**La regola del DDT implicito** (va capita bene):

> Un DDT senza `RiferimentoNumeroLinea` vale per **tutte** le linee, ma solo se nel documento
> esiste **un solo** `NumeroDDT` distinto **e nessun** `RiferimentoNumeroLinea`.

Se ci sono due DDT e uno solo cita le linee, il secondo non può essere attribuito alle linee non
citate: resterebbero `NON_ABBINATO` invece di ricevere un DDT sbagliato. Il codice lo verifica
contando `numeri_ddt_distinti` e `numero_riferimenti_riga`.

**La data del DDT**: `DataDDT` è facoltativa nel tracciato (2.1.8.2). Il codice raccoglie tutte le
date dichiarate per ogni numero DDT e assegna una data alla linea **solo se ne esiste una sola**;
con date discordanti lascia vuoto e incrementa un contatore stampato nel riepilogo. Nessun
abbinamento deve poggiare su una data scelta a caso.

Per ogni `DettaglioLinee` produce una riga con: numero linea, natura (`TipoCessionePrestazione`),
descrizione, quantità, unità di misura, prezzo unitario, prezzo totale, riferimento amministrazione,
`NumeroDDT`, `DataDDT`, `TipoAbbinamentoDDT` (`ESPLICITO`, `IMPLICITO`, `NON_ABBINATO`,
`NESSUN_DDT`).

Per ogni `CodiceArticolo` produce una riga in formato **lungo** (`CodiceTipoXML`, `CodiceValoreXML`),
più una riga aggiuntiva per `RiferimentoAmministrazione`, trattato come tipo virtuale.

Alla fine: conversione dei tipi (`DataFattura` e `DataDDT` a data, campi numerici a numero con
`errors="coerce"`) e ordinamento stabile.

### [4] Funzioni di normalizzazione

Qui c'è il motore che rende confrontabili le stringhe. **Ogni** valore passa da qui.

**Livello 1 — sempre applicato, qualunque regola:**

```
in_testo        → converte in stringa gestendo None/NaN/NaT e i float interi ("1.0" → "1")
valore_pulito   → rimuove i caratteri di controllo (equivalente di Text.Clean)
                  trim, toglie lo spazio non separabile (\u00a0)
                  se resta vuoto → None
                  altrimenti MAIUSCOLO
```

**Livello 2 — la regola scelta nel dizionario:**

| Regola | Cosa fa |
|---|---|
| `DDT_BASE` (default) | toglie i separatori `" -/._:"`, e se il risultato è tutto numerico toglie gli zeri iniziali |
| `RIMUOVI_ZERI` | identica a `DDT_BASE` |
| `NESSUNA_REGOLA` | si ferma al livello 1 |
| `TESTO_MAIUSCOLO` | identica a `NESSUNA_REGOLA` (il maiuscolo è già nel livello 1) |
| `SOLO_NUMERI` | tiene solo le cifre e toglie gli zeri iniziali; se non resta nulla → None |
| `ESTRAI_PRIMA_STRINGA` | parte fino al primo carattere non alfanumerico, poi `finalizza` |
| `ESTRAI_ULTIMA_STRINGA` | ultima parte dopo spazio, trattino o slash, poi `finalizza` |

Funzioni di supporto: `riduci_zeri`, `solo_cifre`, `finalizza` (separatori + zeri), `prima_stringa`,
`dividi` (equivalente di `Text.SplitAny`).

**Regola non riconosciuta: non blocca.** Si applica `DDT_BASE` e `stato_regola()` restituisce
`NON RICONOSCIUTA: <valore>`, così la sezione [6] la elenca. È una scelta deliberata: un errore di
battitura nel dizionario non deve fermare la produzione, ma non deve nemmeno passare inosservato.

**Perché il confronto è ordinale**: `prima_stringa` considerare alfanumerico solo `0-9` e `A-Z`
significa che le lettere accentate fanno da separatore. È voluto: `À` e `A` in un codice articolo
sono quasi sempre un errore di codifica, non una distinzione.

### [5] Dizionari

Tre fogli Excel, tre mappe in memoria.

| Foglio | Chiave | Valore |
|---|---|---|
| `RegoleCodiciXML` | `(CFOR, CodiceTipoXML)` | `(CampoCanonico, regola)` |
| `RegoleCodiciCarico` | `(CFOR, CampoCanonico)` | `regola` |
| `RegoleDDT` | `CFOR` | `(regola XML, regola carico)` |

**Perché fogli separati**: sul lato XML uno stesso campo canonico può essere raggiunto da più
`CodiceTipoXML` (per esempio `EAN` e `GTIN` puntano entrambi a `EAN`); sul lato carico la coppia
`(CFOR, CampoCanonico)` deve invece essere unica, altrimenti non si saprebbe quale regola applicare.

Funzioni:

- `prepara_dizionari(...)` costruisce le tre mappe e restituisce anche due DataFrame di diagnostica:
  `Anomalie` (regole non riconosciute) e `ChiaviDuplicate`;
- `chiave_cfor` / `chiave_testo` normalizzano le chiavi (trim + maiuscolo);
- `regola_codice_xml`, `regola_codice_carico`, `regola_ddt_xml`, `regola_ddt_carico` leggono una
  regola;
- `normalizza_ddt_xml|carico` e `normalizza_codice_xml|carico` sono i quattro punti di ingresso che
  applicano la regola giusta al valore giusto.

**Duplicati**: vince la prima riga letta (`setdefault`). Non è un caso teorico: un foglio Excel
ordinato a mano produce doppioni, e il notebook li segnala invece di fallire.

**Righe senza `CFOR`**: ignorate. Senza fornitore la regola non è applicabile.

### [6] Diagnostica del dizionario

Blocco **rimovibile** (`INIZIO/FINE BLOCCO DIAGNOSTICA`): copia il file dei dizionari in locale, lo
legge con `sheet_name=None`, stampa quante righe ha ogni foglio e quante hanno un `CFOR`, poi
chiama `prepara_dizionari`. Non produce dati usati a valle: cancellando il blocco il flusso
continua a funzionare.

### [7] Carichi: lettura, tipi, filtro

`read_source()` legge da Excel o da tabella (`spark.table`). `apply_schema()` impone i tipi:

| Gruppo | Colonne | Tipo |
|---|---|---|
| stringhe | `CAZI`, `CFOR`, `CEDI`, `CDOCIAA`, `CART`, `XART`, `NDOGIAA`, `NDOGIAB`, `CSTQ`, `CUMF`, `CEAS`, `CALA` | `string` |
| interi | `CPCO` | `Int64` |
| decimali | `Qtà`, `Importo_ns_fattura`, `PF02IAL`, `QTA ORDINE`, `QTA ACCETT` | `Float64` |
| date | `TDATIAA`, `TDATIAB` | `datetime64` |

`validate_schema()` blocca l'esecuzione se manca una colonna attesa: meglio un errore chiaro subito
che un merge silenziosamente sbagliato dopo.

Poi il **filtro sul tipo documento** (`CDOCIAA == "60I"`) e la rinomina in nomi parlanti, per
esempio `CFOR` → `mersy_fornitore(CFOR)`. La rinomina serve a non confondere mai i due lati: se in
`df_merge` leggi `mersy_*` sai che il valore viene dal gestionale.

### [8] Carichi: perimetro e indice

Il cuore del "cosa entra nel processo".

1. **pulizia delle chiavi** (`vuota_in_mancante`): trim e stringa vuota → `pd.NA`. Serve perché in
   pandas due celle vuote **si incontrano** in un merge, a differenza di SQL: senza questa pulizia
   righe diverse si aggancerebbero sul nulla.
2. **chiavi delle fatture XML**: `CEAS_XML` (da `ceas_da_nome_file`) e `NDOGIAA_XML`, deduplicate e
   senza nulli.
3. **inner join** `df_fatture` × fatture XML: chi non ha una fattura XML corrispondente **esce dal
   processo**. Il numero di righe escluse viene stampato.
4. **indice progressivo** `Indice`, da 1, assegnato **dopo** i filtri: identifica univocamente la
   riga di carico e serve a tutti i lookup successivi (si sceglie sempre l'`Indice` più basso).

`ceas_da_nome_file` prende il **solo nome del file** e toglie `.xml`: se nello ZIP i file stanno in
sottocartelle, il percorso interno non conta.

### [9] Anagrafiche

Tre join, tutti `many_to_one` con assert sul numero di righe.

**Punti di consegna**: `CPCO → XPCO` (descrizione), con controllo esplicito dei `CPCO` duplicati, che
duplicherebbero i carichi.

**EAN**: `CART → CEAN` (e `SBAR`, il tipo di barcode). Si controlla che ogni `CART` compaia una volta
sola.

**Codici fornitore (`CARF`)**: chiave `CART + CFOR`, non il solo `CART`. Questo è un punto in cui la
logica è stata corretta rispetto al passato: raggruppando sul solo `CART`, un articolo venduto da
due fornitori riceveva un codice unico e il match sul codice fornitore falliva sempre per uno dei
due. In caso di più righe per la stessa coppia vince quella con `TDEC` più recente (le date mancanti
contano come meno recenti).

Infine **`CALA` viene sostituita da `CARF`**: da quel momento la colonna `mersy_articolo_fornitore(CALA)`
contiene il codice dell'anagrafica. La sostituzione **non normalizza**: la normalizzazione è
competenza del dizionario.

### [10] Chiave DDT lato carichi

Si prendono le coppie distinte `(CFOR, NDOGIAB)`, si normalizzano **una volta sola** (la
normalizzazione è costosa) e si riportano nel DataFrame come `NDOGIAB_Chiave`. Il valore originale
resta.

Il merge usa `validate="many_to_one"` e un assert sul numero di righe: se la deduplica fosse sbagliata,
il numero cambierebbe e ce ne accorgeremmo subito.

### [11] CFOR e chiave DDT lato XML

L'XML non contiene il codice fornitore. Si ricava **dai carichi**, con la stessa coppia del perimetro
(`CEAS + NDOGIAA`). Costruzione della mappa:

1. coppie distinte `(CEAS, NDOGIAA, CFOR)` dai carichi;
2. se una stessa fattura risultasse associata a più `CFOR`, il notebook **lo segnala** e tiene il
   primo in ordine alfabetico;
3. merge sulla coppia, assert sul numero di righe, rinomina in `CFOR_XML`.

Poi, come nella [10], `NumeroDDT_Chiave` si calcola sulle coppie distinte `(CFOR_XML, NumeroDDT)`
con la regola del foglio `RegoleDDT` colonna `RegolaDDTXML`.

**Conseguenza importante**: una fattura fuori perimetro (senza carichi) resta **senza `CFOR`**, e
quindi non può entrare nei livelli successivi che ragionano per fornitore.

### [12] Codici articolo normalizzati

`df_xml_codici_articolo` è in formato lungo. Si aggiungono tre colonne:

| Colonna | Da dove |
|---|---|
| `CFOR_XML` | dalla riga di fattura, tramite `ChiaveRigaXML` |
| `CampoCanonico` | dal dizionario: tipo XML → campo (`EAN`, `CODICE_CLIENTE`, `CODICE_FORNITORE`) |
| `CodiceValoreNormalizzato` | dal dizionario: regola per `(CFOR, tipo)` applicata al valore |

La normalizzazione avviene sulle **terne distinte** `(CFOR, CodiceTipoXML, CodiceValoreXML)`, non su
ogni riga: stesso valore, stesso risultato, meno lavoro.

Se il tipo non è mappato, `CampoCanonico` resta vuoto ma il valore viene comunque normalizzato con la
regola di default: non si perde il dato, semplicemente non finisce in una colonna canonica (vedi [13]).

### [13] Righe aggregate (`df_xml_righe`)

Questa sezione porta l'XML dalla granularità *linea* a quella *articolo*, la stessa dei carichi. È
la sezione più delicata.

**Passo 1 — righe senza codice.** Una linea senza `CodiceArticolo` riceve un codice tecnico
`__NESSUN_CODICE` con valore `"1"`. Senza questo passaggio, le righe descrittive (sconti, abbuoni,
spese accessorie, premi) **sparirebbero** dal pivot.

**Passo 2 — campo di pivot.** Per ogni codice si decide in quale colonna finirà:

```
tipo == __NESSUN_CODICE          → __NESSUN_CODICE
CampoCanonico presente           → quel campo (EAN / CODICE_FORNITORE / CODICE_CLIENTE)
CampoCanonico vuoto (non mappato)→ NON_MAPPATO|tipo   (una colonna per tipo)
```

**Passo 3 — pivot.** Per ogni coppia `(linea, campo)` si tiene il **primo valore non nullo** in ordine
di `ProgressivoCodiceXML`: se una riga ha due EAN, vince il primo scritto nell'XML.

**Passo 4 — chiave articolo.** Gerarchia:

```
EAN presente            → "EAN|{ean}"
CODICE_CLIENTE presente → "CART|{cliente}"
CODICE_FORNITORE        → "FORN|{fornitore}"
natura della riga       → "ABBUONO|{n}" / "SPESA ACCESSORIA|" / "PREMIO|" / "SCONTO|"
nessun codice           → "RIGA DESCRITTIVA|{numero linea}"
```

**Passo 5 — aggregazione.** Raggruppa per `IdFile, CFOR, NumeroFattura, NumeroDDT,
NumeroDDT_Chiave, DataDDT, ChiaveArticoloXML` e applica:
`first` alle colonne descrittive, `sum(min_count=1)` a `Quantita` e `PrezzoTotale` (nullo se il
gruppo non ha nessun valore), `numeri_linea_xml` per l'elenco delle linee (`"01, 02"`), `size` per il
conteggio.

**Passo 6 — colonne derivate**: `ChiaveAggregataXML` (stringa di lettura), `Indicerighe`, e
`PrezzoUnitarioNetto = PrezzoTotale / Quantita` (nullo se quantità nulla o zero).

**Insidia da ricordare**: `DataDDT` è **chiave di aggregazione**, quindi non deve comparire anche fra
le colonne di output, altrimenti `groupby().agg()` va in errore con
`ValueError: cannot insert DataDDT, already exists`. Nel codice c'è un filtro esplicito che la
esclude.

### [14] Abbinamento DDT (`map_ddt`)

Obiettivo: dare a ogni DDT dei due lati una **chiave comune**. Lavora **dentro** ogni coppia
`CFOR + numero fattura`: due DDT con lo stesso numero ma fatture diverse non si devono incontrare.

Si parte da due tabelle distinte:

- `xml_ddt`: `(IdFile, CFOR, NumeroFattura, NumeroDDT, NumeroDDT_Chiave, DataDDT)`;
- `carichi_ddt`: `(CFOR, NDOGIAA, NDOGIAB, NDOGIAB_Chiave, TDATIAB)`.

Entrambe filtrate sulle chiavi valide. Poi, per ogni gruppo, `abbina_gruppo` applica tre livelli:

**Livello 1 — `TESTO`**
Chiavi normalizzate identiche sui due lati.

**Livello 2 — `DATA_UNIVOCA`**
Fra i DDT rimasti, si raggruppa per data. Se su una certa data resta **un solo** DDT XML e **un
solo** DDT carico, si abbinano. Se ce ne sono due o più, la data non basta e si passa al livello 3.

**Livello 3 — `UNICO_RESIDUO`**
Dopo i livelli precedenti, se resta **un solo** DDT per parte, si abbinano. Se una delle due date
manca, l'abbinamento è accettato col metodo `UNICO_RESIDUO_DATA_MANCANTE`; se entrambe esistono e
sono diverse, **non** si abbina.

Poi la priorità: se lo stesso DDT XML comparirebbe con metodi diversi, vince il più sicuro
(`TESTO` < `DATA_UNIVOCA` < `UNICO_RESIDUO`) e la stessa regola si applica sul lato carico. La chiave
comune è costruita **sul lato carico**, che è il riferimento canonico:

```
ChiaveDDT_Comune = CFOR + "|" + NumeroFattura + "|" + ChiaveDDT_Carico
```

I DDT non abbinati non ricevono una chiave comune: più avanti ciascun lato costruisce una chiave
"orfano" (`XML_ORFANO` / `CARICO_ORFANO`) che **per costruzione** non può incontrare nulla
sull'altro lato.

### [15] Merge finale

Cinque passaggi.

**1. Lato XML.** Ogni riga di `df_xml_righe` riceve la `ChiaveDDT_Comune` dalla `map_ddt` sulla terna
`(CFOR, NumeroFattura, NumeroDDT_Chiave)`. Se non la trova, costruisce la chiave orfano. Viene
creato `ID_Riga_XML`.

**2. Lato carichi.** Stessa cosa su `df_fatture` con `(CFOR, NDOGIAA, NDOGIAB_Chiave)`, chiave orfano
se manca.

**3. Lookup in cascata.** Tre tabelle di lookup, una per livello di codice:

```
(CFOR, NDOGIAA, ChiaveDDT_ComuneCarico, EAN)  → Indice minimo + numero di righe
(..., CART)                                  → idem
(..., CALA)                                  → idem
```

Per ogni riga XML si prova prima `EAN`, poi `CART`, poi `CALA`; il primo che trova qualcosa
determina `TipoMatch`. Fra più righe compatibili si prende **l'`Indice` più basso**, quindi il
risultato è deterministico.

**4. Lookup di contesto.** Servono a spiegare *perché* un abbinamento non è avvenuto:

| Lookup | Granularità | Colonna prodotta |
|---|---|---|
| documento | `CFOR + fattura + DDT` | `NumeroRigheDocumento` |
| fattura | `CFOR + fattura` | `NumeroRigheFattura`, DDT distinti, elenco DDT |
| fattura globale | solo numero fattura | `NumeroRigheFatturaGlobale` |

**5. Full outer.** `df_xml_merge` (righe XML) × `carichi_univoci` (una riga per `Indice`) su
`ID_Riga_Ordine == Indice`. Da qui `StatoAbbinamento`:

```
solo carico                        → "Solo carico"
riga XML senza ID_Riga_Ordine      → "Solo XML"
entrambi                           → "Abbinato"
altro                              → "Da verificare"
```

Infine: aggancio dell'anagrafica per `CARF` (per segnalare i codici fornitore usati su più articoli)
e la colonna di lettura `NumeroDDT_Comune` (DDT XML → DDT abbinato → `NDOGIAB` → `"Senza DDT"`).

### [16] Export diagnostico

Sei fogli in `export/riconciliazione.xlsx`: `df_merge`, `map_ddt`, `df_xml_righe`, `df_fatture`,
`df_xml_fatture`, `df_xml_codici_articolo`. È il file da aprire quando un abbinamento non torna:
permette di risalire a ogni passaggio.

---

## 6. Il blocco finale: il report

La seconda cella del notebook costruisce `df_powerbi` e lo salva in
`export/riconciliazione_powerbi.xlsx` (un foglio, 24 colonne).

### 6.1 `coalesce_colonne`

Il cuore del report. Riceve un elenco ordinato di colonne e restituisce, riga per riga, **il primo
valore valido** da sinistra a destra. Prima di confrontare, le colonne testuali vengono pulite
(trim, stringa vuota → nullo). Il parametro `ignora_colonne_assenti=True` serve per le colonne XML
opzionali, che potrebbero non esistere.

### 6.2 Come nasce ogni colonna

| Colonna report | Prima scelta | Poi | Default |
|---|---|---|---|
| `Fattura` | `NumeroFattura` (XML) | `mersy_n_fattura(NDOGIAA)` | `Senza fattura` |
| `Data fattura` | `DataFattura` | `mersy_data_fattura(TDATIAA)` | — |
| `CEAS` | solo `mersy_archiviazione_ottica(CEAS)` | — | — |
| `CFOR` | `Fornitore_consolidato` | — | — |
| `Denominazione` | etichetta `(CFOR) Nome` | — | — |
| `Bolla` | `NumeroDDT_Comune` | — | `Senza DDT` |
| `Data bolla` | `DataDDT` | `DataDDT_XML`, `mersy_data_DDT(TDATIAB)` | — |
| `Descrizione` | `Descrizione` | `mersy_descrizione_articolo(XART)` | `Descrizione non disponibile` |
| `Numero riga fattura` | `NumeriLineaXML` | — | — (vuoto senza lato XML) |
| `Unità di misura` | `UnitaMisura` | `mersy_um_prezzo(CUMF)` | — |
| `Codice articolo interno` | `Codice Art. Cliente` | `mersy_articolo(CART)` | — |
| `Codice articolo fornitore` | `Codice Art. Fornitore` | `mersy_articolo_fornitore(CALA)` | — |
| `Codice EAN` | `EAN` | `mersy_ean(CEAN)` | — |
| `Quantità XML` | `Quantita` | — | — |
| `Quantità carico` | `mersy_qta_fattura(Qtà)` | — | — |
| `Differenza quantità` | `Quantità XML − Quantità carico` | — | — |
| `Prezzo unitario XML` | `PrezzoUnitarioNetto` | — | — |
| `Prezzo unitario carico` | `mersy_prezzo_fattura(PF02IAL)` | — | — |
| `Totale XML` | `PrezzoTotale` | — | — |
| `Totale Mersy` | `mersy_importo_ns_accettazione(Importo_ns_fattura)` | — | — |
| `Differenza totali` | `Totale XML − Totale Mersy` | — | — |
| `CPCO` | `mersy_punto_consegna(CPCO)` | — | — (vuoto senza carico) |
| `CPCO descrizione` | `mersy_descrizione_punto_consegna(XPCO)` | — | — |
| `Stato abbinamento` | `StatoAbbinamento` | — | — |

`CEAS`, `CPCO` e la sua descrizione arrivano **solo dal lato carichi**: sulle righe `Solo XML`
restano vuote. È corretto: una bolla non ancora consegnata non ha punto di consegna, e nell'XML il
`CEAS` non è un dato del documento ma il nome del file.

Le differenze si calcolano **dopo** il coalesce: se manca un lato, la differenza è vuota (non zero).
Questo è voluto: "non ho il dato" e "differenza zero" sono due cose diverse.

### 6.3 La denominazione e il suo limite

1. `Fornitore_consolidato` = CFOR dell'XML, altrimenti quello dei carichi;
2. mappa `CFOR → Denominazione` costruita dalle righe che hanno entrambi;
3. ogni riga riceve il nome cercando il proprio CFOR nella mappa;
4. `crea_etichetta_fornitore` compone `(CFOR) Nome`, oppure `(CFOR)`, oppure `Nome`, oppure
   `Fornitore non disponibile`.

**Limite noto**: una fattura fuori perimetro non ha CFOR, quindi non trova il nome nella mappa ed
esce come `Fornitore non disponibile`, anche se il suo XML lo contiene. Il caso è documentato nel
codice con le possibili strade, se in futuro diventasse rilevante.

---

## 7. Le colonne di stato: come leggere il risultato

Ogni riga di `df_merge` ha quattro indicatori. La combinazione racconta la storia.

| `StatoAbbinamento` | Significato |
|---|---|
| `Abbinato` | riga XML e riga carico unite |
| `Solo XML` | la fattura c'è, il carico no (o non è stato agganciato) |
| `Solo carico` | il carico c'è, la fattura no |
| `Da verificare` | caso residuo (non dovrebbe capitare) |

| `TipoMatch` | Significato |
|---|---|
| `EAN` / `CART` / `CALA` | su quale livello di codice è avvenuto l'abbinamento |
| `Nessun match` | la riga XML non ha trovato alcun carico |
| `Solo carico` | riga di carico non raggiunta da nessuna riga XML |

| `MetodoMatchDDT` | Significato |
|---|---|
| `TESTO` | numeri DDT identici dopo normalizzazione (il più affidabile) |
| `DATA_UNIVOCA` | numeri diversi, ma un solo DDT per lato su quella data |
| `UNICO_RESIDUO` | numeri diversi, resta un solo DDT per parte, date compatibili |
| `UNICO_RESIDUO_DATA_MANCANTE` | come sopra, ma mancava almeno una data |

| `StatoDocumento` | Significato | Cosa guardare |
|---|---|---|
| `Documento trovato` | il DDT esiste nei carichi | se la riga è `Solo XML`, manca il carico dell'articolo |
| `DDT non corrispondente` | il documento c'è, il DDT no | numero DDT scritto diversamente → nuova regola nel dizionario |
| `CFOR non corrispondente` | la fattura c'è, ma sotto un altro fornitore | errore di `CEAS`/fornitore nei dati |
| `Fattura non trovata` | nessun carico con quella fattura | fattura fuori perimetro o non ancora caricata |
| `DDT XML nullo` | la linea XML non ha un DDT | riga descrittiva o XML incompleto |
| `Solo carico` | riga solo carico | — |

**Combinazione tipica da cercare**: `Solo XML` + `Documento trovato` significa "il trasporto è
registrato ma la riga articolo non si è agganciata": quasi sempre un codice articolo non mappato o
una quantità su un'altra riga.

---

## 8. Casi limite e decisioni di progetto

**Perché tanti `validate=` sui merge**
`validate="many_to_one"` fa fallire il merge se la chiave di destra non è unica. È la rete che
impedisce a un'anagrafica duplicata di moltiplicare le righe del risultato. Negli stessi punti ci
sono assert espliciti sul numero di righe prima/dopo.

**Perché le stringhe vuote diventano `pd.NA`**
In pandas due `None` si agganciano in un merge; in SQL no. Senza la conversione, righe diverse con
campo vuoto finirebbero nella stessa riga di risultato.

**Perché le chiavi "orfano"**
Un DDT non abbinato deve restare non abbinato. Invece di affidarsi a un `NaN` (che in un merge si
comporta in modo sorprendente), si costruisce una chiave che contiene la parola `XML_ORFANO` o
`CARICO_ORFANO`: non potrà mai coincidere con l'altra.

**Perché vince la prima riga in caso di duplicato**
Il dizionario è un file Excel modificato a mano: il duplicato è quasi sempre una copia dimenticata.
Scegliere la prima riga è deterministico e il duplicato viene comunque segnalato.

**Perché `TDEC` più recente per `CARF`**
Le anagrafiche non si cancellano, si chiudono: la riga valida è quella più recente.

**Perché la data DDT discordante resta vuota**
Meglio un dato mancante che un abbinamento costruito su una data scelta per caso. Il contatore
stampato nel riepilogo dice quante volte è successo.

**Perché le somme usano `min_count=1`**
`sum()` su un gruppo di soli nulli restituisce `0`, che falserebbe la differenza. Con `min_count=1`
restituisce nullo.

**Perché il perimetro è un inner join**
Il processo riconcilia fatture con carichi: una fattura senza carichi o un carico senza fattura XML
non hanno un termine di confronto. I carichi fuori perimetro vengono esclusi *prima* di tutto, e il
numero di esclusi è stampato: è il primo controllo da guardare se i totali non tornano.

---

## 9. Come si cerca un errore

Parti sempre dal sintomo.

| Sintomo | Dove guardare | Cosa cercare |
|---|---|---|
| manca una fattura nel risultato | [2] e [8] | XML scartato (non FPR12), `CEAS` non combacia, righe escluse dal perimetro |
| una riga è `Solo XML` con `Documento trovato` | [15] | `TipoMatch`: nessun codice agganciato → controlla [12] e il dizionario |
| una riga è `Solo XML` con `DDT non corrispondente` | [14] e [10]-[11] | la chiave DDT: aggiungi/correggi una regola in `RegoleDDT` |
| una riga è `Solo carico` | [15] | `Indice` mai raggiunto: la riga XML esiste ma con DDT o codice diverso |
| differenze quantità a zero ma prezzi diversi | report | il match è avvenuto sull'articolo giusto ma su un'altra riga di carico (vince l'`Indice` più basso) |
| stesso articolo due volte | [13] | `ChiaveArticoloXML` diversa: uno dei due codici non è mappato e finisce in una colonna `NON_MAPPATO\|tipo` |
| colonna del report vuota | blocco finale | guarda la catena del `coalesce` per quella colonna |
| regola ignorata | [6] | `Anomalie`: `NON RICONOSCIUTA` |
| `IndexError`/`ValueError` in [13] | [13] | colonna sia chiave sia output; `DataDDT` è il caso già noto |

**Le tre domande da farsi, in ordine**: la fattura è entrata (perimetro)? il DDT è stato abbinato
(`map_ddt`)? l'articolo è stato agganciato (`TipoMatch`)? La prima che risponde "no" è il punto in
cui intervenire.

---

## 10. Cosa il codice non fa

- **non calcola l'IVA** né alcun totale di documento: lavora solo sulle righe;
- **non gestisce le note di credito** come casi speciali: filtra `CDOCIAA = 60I`, quindi se una
  fattura è collegata a una nota di credito la differenza emerge come differenza, non viene stornata;
- **non verifica la quadratura** (`CSTQ`) né gli ordini (`QTA ORDINE`, `QTA ACCETT`): le colonne
  sono lette e portate nel merge, ma non usate nelle regole;
- **non estrae `AliquotaIVA`** né `CodiceFiscale` di linea: se servissero, la sezione [13] li
  aggregherebbe da sola una volta presenti in `df_xml_fatture`;
- **tratta `RiferimentoAmministrazione`** come un normale codice articolo (tipo virtuale): un
  trattamento dedicato è una decisione ancora aperta;
- **non è incrementale**: ricalcola tutto a ogni esecuzione. Non c'è memoria fra un run e l'altro, e
  `Indice` non è stabile se cambia il perimetro.

---

## 11. Appendice: colonne di ogni tabella

### `df_xml_fatture` (una riga per linea)

```
ChiaveRigaXML, FileXML, IndiceBodyXML, Denominazione, TipoDocumento, Divisa,
DataFattura, NumeroFattura, NumeroLinea, TipoCessionePrestazione, Descrizione,
Quantita, UnitaMisura, PrezzoUnitario, PrezzoTotale, RiferimentoAmministrazione,
NumeroDDT, DataDDT, TipoAbbinamentoDDT, CEAS_XML, NDOGIAA_XML, CFOR_XML,
NumeroDDT_Chiave
```

### `df_xml_codici_articolo` (una riga per codice)

```
ChiaveRigaXML, ProgressivoCodiceXML, CodiceTipoXML, CodiceValoreXML,
CFOR_XML, CampoCanonico, CodiceValoreNormalizzato
```

### `df_xml_righe` (una riga per articolo dentro un DDT)

```
IdFile, CFOR, NumeroFattura, NumeroDDT, NumeroDDT_Chiave, DataDDT,
ChiaveArticoloXML, Descrizione, UnitaMisura, EAN, Codice Art. Fornitore,
Codice Art. Cliente, TipoCessionePrestazione, TipoAbbinamentoDDT, DataFattura,
Denominazione, Quantita, PrezzoTotale, NumeriLineaXML, NumeroRigheAggregate,
ChiaveAggregataXML, Indicerighe, PrezzoUnitarioNetto
```

### `df_fatture` (una riga per carico nel perimetro)

```
mersy_azienda(CAZI), mersy_cedi(CEDI), mersy_punto_consegna(CPCO),
mersy_tipo_documento(CDOCIAA), mersy_um_prezzo(CUMF),
mersy_stato_quadratura(CSTQ), mersy_qta_ordine(QTA ORDINE),
mersy_qta_accettata(QTA ACCETT), mersy_fornitore(CFOR), mersy_n_fattura(NDOGIAA),
mersy_data_fattura(TDATIAA), mersy_n_DDT(NDOGIAB), mersy_data_DDT(TDATIAB),
mersy_articolo(CART), mersy_descrizione_articolo(XART),
mersy_archiviazione_ottica(CEAS), mersy_qta_fattura(Qtà),
mersy_importo_ns_accettazione(Importo_ns_fattura), mersy_prezzo_fattura(PF02IAL),
Indice, mersy_descrizione_punto_consegna(XPCO), mersy_tipo_ean(SBAR),
mersy_ean(CEAN), mersy_articolo_fornitore(CALA), mersy_descrizione_fornitore(XARF),
NDOGIAB_Chiave
```

### `map_ddt` (una riga per coppia DDT abbinata)

```
CFOR, NumeroFattura, ChiaveDDT_XML, ChiaveDDT_Carico, ChiaveDDT_Comune,
MetodoMatchDDT, NumeroDDT_XML, NDOGIAB_Carico, DataDDT_XML, TDATIAB_Carico
```

### `df_merge` (73 colonne: l'unione dei due lati più le colonne di stato)

Contiene tutto `df_xml_righe` (23 colonne), tutte le colonne dei carichi (26), i lookup
(`ID_Riga_Ordine_*`, `NumeroMatch*`), le diagnostiche (`NumeroRigheDocumento`,
`NumeroRigheFattura`, `NumeroRigheFatturaGlobale`, `DDTCarico*`), gli stati (`TipoMatch`,
`StatoDocumento`, `StatoAbbinamento`) e `NumeroDDT_Comune`.

### `df_powerbi` (24 colonne, il report)

```
Fattura, Data fattura, CEAS, CFOR, Denominazione, Bolla, Data bolla,
CPCO, CPCO descrizione, Descrizione, Numero riga fattura, Unità di misura,
Codice articolo interno, Codice articolo fornitore, Codice EAN,
Quantità XML, Quantità carico, Differenza quantità, Prezzo unitario XML,
Prezzo unitario carico, Totale XML, Totale Mersy, Differenza totali,
Stato abbinamento
```

### Funzioni, sezione per sezione

| Sezione | Funzioni |
|---|---|
| [3] | `testo` |
| [4] | `in_testo`, `valore_pulito`, `regola_normalizzata`, `riduci_zeri`, `solo_cifre`, `finalizza`, `prima_stringa`, `dividi`, `normalizza`, `stato_regola` |
| [5] | `chiave_cfor`, `chiave_testo`, `_leggi`, `prepara_dizionari`, `regola_codice_xml`, `regola_codice_carico`, `regola_ddt_xml`, `regola_ddt_carico`, `normalizza_*` |
| [6] | `prendi_foglio` |
| [7] | `read_source`, `apply_schema`, `validate_schema` |
| [8] | `vuota_in_mancante`, `solo_chiavi_valide`, `ceas_da_nome_file` |
| [13] | `campo_pivot`, `chiave_articolo_xml`, `somma_o_nulla`, `numeri_linea_xml` |
| [14] | `valore_valido`, `maschera_valida`, `primo_valido`, `abbina_gruppo` |
| [15] | `crea_lookup_codice`, `tipo_match`, `stato_documento`, `stato_abbinamento`, `numero_ddt_comune` |
| report | `pulisci_testo`, `coalesce_colonne`, `crea_etichetta_fornitore` |

---

## Percorso di lettura consigliato

Se devi capirlo a fondo, in tre passate:

1. **prima passata (30 minuti)** — sezioni 1, 2 e 3 di questo documento, poi il codice delle sezioni
   [1], [7], [8]. Sono le fondamenta: sorgenti, perimetro, indice.
2. **seconda passata (1 ora)** — sezioni [4], [5], [10], [11], [14]. È il cuore logico: come due
   stringhe diventano confrontabili.
3. **terza passata (1 ora)** — sezioni [3], [12], [13], [15] e il blocco del report. È la parte
   meccanica: come i dati cambiano forma e granularità.

Alla fine, la prova del nove: prendi una riga di `df_merge` con `StatoAbbinamento = "Solo XML"` e
risali all'indietro fino al file XML da cui viene. Se ci riesci senza guardare il codice, hai capito
tutto il flusso.
