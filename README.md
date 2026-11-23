# quad — riconciliazione fatture

Notebook Fabric/Synapse che confronta le righe delle **fatture elettroniche** (XML in formato
`FPR12`) con le righe dei **carichi a magazzino** del gestionale, e produce un file Excel di
riconciliazione: per ogni articolo, quantità / prezzo / totale lato fattura contro gli stessi
valori lato carico, con la differenza e lo stato dell'abbinamento.

Il repository contiene:

```
Notebook_2 (1).ipynb    tutto il processo (celle [1]–[18], ciascuna preceduta da Markdown)
README.md               questo file
docs/LOGICA.md          guida completa alla logica, cella per cella
tests/                  test eseguibile su dati sintetici
```

Per capire il codice in dettaglio, la guida di riferimento è [`docs/LOGICA.md`](docs/LOGICA.md):
le tre chiavi del processo, le celle una per una, le decisioni di progetto e come cercare un
errore.

---

## 1. A cosa serve

Per ogni fattura ricevuta il fornitore dichiara righe e importi; il gestionale registra i carichi
con i propri codici articolo e i propri riferimenti ai documenti di trasporto (DDT). I due mondi
non coincidono mai perfettamente:

- i codici articolo del fornitore vanno mappati su quelli interni (EAN, codice cliente, codice
  fornitore);
- i numeri DDT sono scritti in modo diverso nei due sistemi (`00123`, `A-123`, `123/2024`…);
- alcune righe esistono solo nella fattura, altre solo nei carichi.

Il notebook risolve questi tre problemi e consegna una tabella in cui ogni riga racconta cosa è
successo, così le differenze si leggono e si contestano al fornitore.

---

## 2. Input

Tutti i file stanno in un'unica cartella OneLake (parametro `cartella` nella sezione `[1]`):

| File | Contenuto |
|---|---|
| `xml.zip` | archivio con gli XML delle fatture (anche in sottocartelle) |
| `TAB_CM_Fatture_BI.xlsx` | carichi: una riga per articolo caricato |
| `ANAGRAFICA_PDV.xlsx` | punti di consegna (`CPCO` → `XPCO`) |
| `TAB_ANAGRAFICA_EAN.xlsx` | anagrafica EAN (`CART` → `CEAN`) |
| `TAB_ANAGRAFICA_CARF.xlsx` | codici articolo fornitore (`CART` + `CFOR` → `CARF`) |
| `Dizionario codici.xlsx` | regole di normalizzazione (3 fogli, vedi §4) |

Sorgente dei carichi selezionabile con `SOURCE_TYPE`:

- `"excel"` (attuale) → legge `TAB_CM_Fatture_BI.xlsx`;
- `"table"` → predisposto per leggere la tabella direttamente da Fabric.

### Perimetro

Il processo non lavora su tutto: valgono contemporaneamente due filtri.

1. **Tipo documento**: `CDOCIAA` in `60I` (fattura) o `60C` (nota di credito) — costante
   `CDOCIAA_FILTRO`, una lista — applicato subito dopo la tipizzazione, prima di ogni join. Per
   aggiungere una sigla basta scriverla nella lista.
2. **Presenza dell'XML**: i carichi vengono messi in inner join con le testate XML sulla coppia
   `CEAS + NDOGIAA`, dove `CEAS` è il nome del file XML senza estensione (es. `IT01234567890_00007.xml`
   → `IT01234567890_00007`) e `NDOGIAA` è il numero fattura.

Le righe che non superano il perimetro non compaiono nel risultato.

---

## 3. Struttura del notebook

Il notebook è suddiviso in 19 celle di codice separate (`[1]`–`[18]`, inclusa `[6-bis]`), ciascuna
preceduta da una breve cella Markdown che ne descrive il ruolo, oltre a un'introduzione iniziale.

| # | Cella | Cosa produce |
|---|---|---|
| 1 | Configurazione e sorgenti | librerie, percorsi, nomi fogli, filtro documento |
| 2 | Lettura XML dallo ZIP | `xml_in_memoria`, `df_errori` |
| 3 | Esplosione righe e codici | `df_xml_fatture` (1 riga per linea, con `DataDDT` e `Denominazione`), `df_xml_codici_articolo` (formato lungo) |
| 4 | Funzioni di normalizzazione | registro `REGOLE`, funzioni `normalizza()`, `valore_pulito()`, … |
| 5 | Dizionari e risoluzione delle regole | schema fogli, `prepara_dizionari()`, funzioni `normalizza_*` |
| 6 | Lettura del dizionario | struttura `dizionari` (mappe di lookup + anomalie e duplicati) |
| 6-bis | Diagnostica del dizionario *(opzionale)* | stampa di regole non riconosciute e chiavi duplicate, rimovibile |
| 7 | Carichi: lettura, tipizzazione e filtro | `df_fatture` tipizzato e filtrato, costanti `COL_*` |
| 8 | Carichi: perimetro XML e indice | `df_fatture` ristretto alle fatture con XML, colonna `Indice` |
| 9 | Carichi: anagrafiche | punti di consegna, EAN, CARF (al posto di `CALA`) in `df_fatture` |
| 10 | Carichi: chiavi di confronto | `NDOGIAB_Chiave`, `CEAN_Chiave`, `CART_Chiave`, `CALA_Chiave` |
| 11 | XML: fornitore e chiave DDT | `CFOR_XML`, `NumeroDDT_Chiave` |
| 12 | XML: codici articolo normalizzati | `CampoCanonico` + `CodiceValoreNormalizzato` (solo tipi codificati) |
| 13 | XML: righe aggregate | `df_xml_righe` (1 riga per articolo dentro un DDT) |
| 14 | Abbinamento DDT | `map_ddt` |
| 15 | Merge finale | `df_merge` (full outer), chiave DDT derivata se l'XML non ha bolla |
| 16 | Esportazione completa *(opzionale)* | `export/riconciliazione.xlsx`, un foglio (`df_merge`, 82 colonne), se `ESPORTA_DIAGNOSTICA = True` |
| 17 | Dataset report Power BI | `df_powerbi` (28 colonne); Excel opzionale con `ESPORTA_EXCEL_POWERBI = True` |
| 18 | Scrittura tabella Delta | tabella `quadratura_powerbi`, sovrascritta solo se `df_powerbi` non è vuoto; i nomi delle colonne di `df_powerbi` vengono modificati sostituendo gli spazi con `_` |

### Dettagli sulle sorgenti XML

- vengono considerati solo i documenti con `versione="FPR12"`;
- i blocchi `<Allegati>` vengono eliminati subito dopo il parsing, per non tenere in memoria i PDF
  allegati;
- un file può contenere più `FatturaElettronicaBody`: vengono trattati come documenti distinti
  (colonna `IndiceBodyXML`);
- la denominazione del fornitore viene letta da `CedentePrestatore/DatiAnagrafici/Anagrafica`
  (`Denominazione`, oppure `Nome` + `Cognome` per le persone fisiche) e riportata su ogni riga di
  linea: da lì arriva a `df_merge` e al report, dove viene propagata a tutte le righe dello stesso
  fornitore, comprese quelle `Solo carico`;
- `DatiDDT` può contenere più blocchi, ciascuno con `NumeroDDT`, `DataDDT` (facoltativa) ed
  eventuali `RiferimentoNumeroLinea`. Se il DDT non cita alcuna linea vale per l'intera fattura,
  ma solo quando esiste **un solo** `NumeroDDT` distinto e **nessun** `RiferimentoNumeroLinea`;
  altrimenti le linee non citate restano `NON_ABBINATO`.

---

## 4. Dizionario delle regole

`Dizionario codici.xlsx` contiene tre fogli. Ogni regola è **per fornitore** (`CFOR`), lato XML e
lato carico sono configurati separatamente perché hanno granularità diverse.

| Foglio | Chiave | Contenuto |
|---|---|---|
| `RegoleCodiciXML` | `CFOR` + `CodiceTipoXML` | → `CampoCanonico`, `RegolaNormalizzazione` |
| `RegoleCodiciCarico` | `CFOR` + `CampoCanonico` | → `RegolaNormalizzazione` |
| `RegoleDDT` | `CFOR` | → `RegolaDDTXML`, `RegolaDDTCarico` |

Nel foglio `RegoleCodiciCarico` la colonna `CampoCanonico` deve contenere **esattamente** `EAN`,
`CODICE_CLIENTE` o `CODICE_FORNITORE` (gli stessi nomi usati in `RegoleCodiciXML`); un valore
diverso — per esempio `CODICE_FORNTORE` — non viene applicato e il notebook lo segnala a runtime
nella sezione `[10]`.

Regole disponibili (le stesse per DDT e codici articolo):

| Regola | Effetto |
|---|---|
| `RIMUOVI_SEPARATORI` *(default)* | rimuove i separatori ` - / . _ :` e gli zeri iniziali se il valore è tutto numerico |
| `RIMUOVI_ZERI` | come `RIMUOVI_SEPARATORI` |
| `NESSUNA_REGOLA` | solo pulizia di base (trim, caratteri non stampabili, maiuscolo) |
| `TESTO_MAIUSCOLO` | come `NESSUNA_REGOLA` |
| `SOLO_NUMERI` | tiene solo le cifre, poi toglie gli zeri iniziali |
| `ESTRAI_PRIMA_STRINGA` | parte fino al primo carattere non alfanumerico |
| `ESTRAI_ULTIMA_STRINGA` | ultima parte dopo spazio, trattino o slash |

La pulizia di base è **sempre** applicata: `Text.Clean`-equivalente (rimozione dei caratteri non
stampabili), trim, rimozione dello spazio non separabile, maiuscolo.

Le regole sono definite in **un unico registro** nella sezione `[4]`: ogni voce associa il nome alla
funzione e a una descrizione, e la tabella viene stampata a runtime insieme al default. Per
aggiungere o modificare una regola si tocca solo quel blocco — `normalizza()` e la diagnostica lo
leggono da soli. Prima servivano tre modifiche in due punti diversi.

### Un tipo di codice conta solo se è nel dizionario

Nel foglio `RegoleCodiciXML` finisce solo ciò che il dizionario codifica: un `CodiceTipoXML` che non
compare per quel `CFOR` viene **scartato** dalla tabella dei codici (sezione `[12]`). Non è una
perdita di informazione — un tipo non codificato non avrebbe comunque contribuito alla chiave
articolo — ma libera il foglio `df_xml_codici_articolo` e i conteggi da tutto ciò che non è
configurato.

Il numero di codici esclusi viene stampato **prima** del filtro, perché dopo non sarebbe più
calcolabile.

La conseguenza pratica è che un tipo di `CodiceArticolo` nuovo si abilita con una riga nell'Excel,
senza toccare il codice. Il notebook costruisce anche il tipo virtuale `RiferimentoAmministrazione`.

La **descrizione della linea non viene usata come codice articolo**, neppure se nel dizionario è
presente una regola `Descrizione`: non viene più creato il relativo codice virtuale. La descrizione
rimane disponibile per il report. Una riga che non ha altri codici non si abbina grazie al testo della
descrizione e resta identificata come riga descrittiva (o tramite la natura, se presente). Un eventuale
`CodiceArticolo` realmente presente nell'XML continua a seguire le normali regole del dizionario.

Una regola scritta male o una cella vuota **non bloccano** l'esecuzione: si applica `RIMUOVI_SEPARATORI` e
l'anomalia viene elencata nella diagnostica della sezione `[6-bis]` (regole non riconosciute, chiavi
duplicate). In caso di chiave duplicata vince la prima riga letta.

### Attenzione al default

Le regole sono **per lato**. Una riga assente non equivale a `NESSUNA_REGOLA`: in entrambi i casi
il valore viene ripulito (trim, maiuscolo), ma con `NESSUNA_REGOLA` restano i separatori, mentre
senza riga si applica `RIMUOVI_SEPARATORI` che li toglie.

```
XML   CODICE_FORNITORE  NESSUNA_REGOLA  →  ART/002
carichi  (riga assente)  RIMUOVI_SEPARATORI       →  ART002      ← nessun match
```

Se il codice articolo è scritto **identico** sui due lati ma il dizionario non ha una riga per quel
`CampoCanonico` in `RegoleCodiciCarico`, la riga resta `Solo XML` senza alcun errore. La sezione
`[10]` confronta le regole effettive dei due lati e, se differiscono, stampa
`ATTENZIONE - regole diverse fra i due lati` con la tabella `regole_non_allineate`
(`CFOR`, `Campo`, `RegolaXML`, `RegolaCarico`). Una regola non riconosciuta e una regola assente
producono lo stesso effetto e quindi non vengono segnalate come disallineamento.

---

## 5. Come avviene l'abbinamento

### 5.1 DDT (`map_ddt`, sezione 14)

L'abbinamento DDT ↔ carico avviene **dentro** ogni coppia `CFOR + numero fattura`, su tre livelli
in ordine di priorità:

1. **TESTO** — chiave normalizzata identica sui due lati;
2. **DATA_UNIVOCA** — sulla stessa data resta un solo DDT XML e un solo DDT carico fra quelli non
   ancora abbinati;
3. **UNICO_RESIDUO** — dopo i livelli precedenti resta un solo DDT per parte; se manca una delle
   due date l'abbinamento è accettato lo stesso (`UNICO_RESIDUO_DATA_MANCANTE`).

I DDT che non trovano corrispondenza ricevono una chiave "orfano" (`XML_ORFANO` / `CARICO_ORFANO`)
che per costruzione non può incontrare nulla sull'altro lato: non si producono abbinamenti
fantasma.

`DataDDT` è facoltativa nel tracciato: la colonna viene valorizzata solo quando la linea è
collegata a un solo DDT, oppure a più DDT che riportano la stessa data. Con date discordanti resta
vuota (e viene conteggiata nel riepilogo della sezione `[3]`), così nessun abbinamento si appoggia
su una data scelta a caso.

#### XML senza bolla, carico con una sola bolla

Capita che la fattura elettronica non riporti alcun `DatiDDT` mentre il carico la bolla ce l'ha.
Senza chiave, la riga XML resterebbe `Solo XML` pur avendo il documento in azienda.

La regola (sezione `[15]`, blocco *2-bis*) è stretta:

| DDT sul carico per `CFOR + fattura` | Comportamento | `OrigineChiaveDDT` |
|---|---|---|
| esattamente **uno** | la chiave viene presa da quel DDT e la riga si abbina | `DDT_UNICO_CARICO` |
| **più di uno** | nessuna derivazione, la riga resta non abbinata | `DDT_AMBIGUO` |
| nessuno | nessuna derivazione | `NESSUNA_CHIAVE` |

La chiave derivata è letta direttamente da `ChiaveDDT_ComuneCarico` (non ricostruita), così
coincide per costruzione con quella su cui lavorano le lookup. Il caso ambiguo ha uno stato
dedicato in `StatoDocumento` (`DDT ambiguo`): meglio non abbinare che abbinare alla bolla
sbagliata.

`OrigineChiaveDDT` distingue quindi `MAPPATO` (DDT presente nell'XML), `ORFANO` (DDT XML non
presente nei carichi), `DDT_UNICO_CARICO` e `DDT_AMBIGUO`, oltre a `NESSUNA_CHIAVE`.

### 5.2 Articolo (sezioni 10 e 15)

Il confronto avviene **su valori normalizzati da entrambi i lati**: l'XML passa dal dizionario
(`RegoleCodiciXML`), i carichi dal foglio `RegoleCodiciCarico`. Le colonne originali dei carichi
restano intatte; sul lato XML le colonne dei codici del report contengono il valore **normalizzato**
(quindi maiuscolo, senza separatori: l'XML con `art-002` arriva nel report come `ART-002`). Il valore
grezzo resta nel foglio diagnostico `df_xml_codici_articolo`. Il confronto usa `CEAN_Chiave`,
`CART_Chiave`, `CALA_Chiave` sul lato carichi e i valori normalizzati sul lato XML.

Per ogni riga XML si cercano le righe carico compatibili con una cascata di tre livelli:

```
EAN  →  CART (codice articolo cliente)  →  CALA/CARF (codice articolo fornitore)
```

Il primo livello che trova qualcosa vince, e fra più righe compatibili si prende quella con
`Indice` più basso. Il tipo di match finisce nella colonna `TipoMatch`.

Infine il **full outer** fra lato XML e lato carichi su `Indice`: le righe XML che non trovano
nulla restano `Solo XML`, le righe carico non raggiunte restano `Solo carico`.

---

## 6. Colonne di stato

| Colonna | Valori |
|---|---|
| `StatoAbbinamento` | `Abbinato`, `Solo XML`, `Solo carico`, `Da verificare` |
| `TipoMatch` | `EAN`, `CART`, `CALA`, `Nessun match`, `Solo carico` |
| `StatoDocumento` | `Documento trovato`, `DDT non corrispondente`, `CFOR non corrispondente`, `Fattura non trovata`, `DDT ambiguo`, `DDT XML nullo`, `Solo carico` |
| `MetodoMatchDDT` | `TESTO`, `DATA_UNIVOCA`, `UNICO_RESIDUO`, `UNICO_RESIDUO_DATA_MANCANTE` |
| `TipoAbbinamentoDDT` | `ESPLICITO`, `IMPLICITO`, `NON_ABBINATO`, `NESSUN_DDT` |

### `Tipologia documento` (colonna del report)

`60I` = fattura, `60C` = nota di credito (l'elenco è `CDOCIAA_FILTRO`, in cima al notebook: per
aggiungere una sigla basta scriverla lì).

È un attributo del **documento**, non della riga: si legge dal carico e viene riportata anche sulle
righe che esistono solo nell'XML, ricavandola dal carico della stessa fattura. Resta **vuota** quando
la fattura non esiste nei carichi: il tipo SDI dell'XML (`TD01`, `TD04`, …) è un codice diverso e non
esiste una mappatura su `CDOCIAA` — se serve, va decisa e aggiunta.

### `Stato DDT` (colonna del report)

Lo stato della **bolla**, non della riga: tutte le righe della stessa bolla riportano lo stesso
valore, anche quella che esiste solo nei carichi. Una riga `Solo carico` su una bolla riconciliata
resta un problema di articolo, non di documento, e il suo `Stato DDT` lo dice.

| Valore | Significato |
|---|---|
| `Bolla abbinata per numero` | numeri DDT identici dopo normalizzazione (metodo `TESTO`) |
| `Bolla abbinata per data` | numeri diversi, ma un solo DDT per lato su quella data |
| `Bolla abbinata per esclusione` | numeri diversi, resta un solo DDT per parte |
| `Bolla abbinata per esclusione, data mancante` | come sopra, ma mancava una delle due date |
| `Bolla dedotta dal carico` | l'XML non aveva DDT, la chiave viene dal DDT unico del carico |
| `Bolla ambigua: più bolle nel carico` | l'XML non ha DDT e il carico ne ha più di uno: non si sceglie |
| `Bolla XML senza riscontro nei carichi` | il DDT dell'XML non esiste fra i carichi |
| `Bolla carico senza riscontro nell'XML` | il DDT del carico non esiste nell'XML |
| `Nessuna bolla` | la riga non ha alcun DDT da nessuno dei due lati |

La lettura tipica: `Solo XML` + `Documento trovato` = la fattura c'è, manca la riga a carico;
`DDT non corrispondente` = il carico esiste ma il DDT è scritto diversamente (candidato a una
nuova regola nel dizionario); `CFOR non corrispondente` = il numero fattura esiste ma sotto un
altro fornitore; `DDT ambiguo` = l'XML non indica la bolla e il carico ne ha più di una, quindi la
riga va guardata a mano.

---

## 7. Output

### `export/riconciliazione.xlsx` — diagnostica

L’export è **disattivato per default**. Per attivarlo, impostare `ESPORTA_DIAGNOSTICA = True`
nella cella `[1]` e rieseguire il notebook. Quando è attivo esporta un solo foglio, `df_merge`.
Le altre tabelle sono disponibili ma vanno aggiunte a mano in `TABELLE_DA_ESPORTARE`.
Se disattivato non viene creato né aggiornato il file; un file precedente resta su OneLake.
Quando l'export è attivo, i fogli disponibili sono:

| Foglio | Contenuto |
|---|---|
| `df_merge` | il risultato del processo (full outer) — esportato quando attivo |
| `map_ddt` | abbinamento dei DDT fra i due lati |
| `df_xml_righe` | lato XML alla granularità dell'articolo |
| `df_fatture` | lato carichi nel perimetro |
| `df_xml_fatture` | lato XML, una riga per linea |
| `df_xml_codici_articolo` | lato XML, una riga per codice |

Il motivo è il tempo: `df_merge` ha 82 colonne e scrivere Excel costa circa 1 secondo ogni 1.000
righe **per foglio**. Misurato su 20.000 righe × 82 colonne: 6 fogli con `openpyxl` 124 s, un foglio
23 s, un foglio con `xlsxwriter` 14 s. Il notebook usa `xlsxwriter` quando è disponibile e ricade su
`openpyxl` altrimenti.

### Dataset Power BI e tabella Delta

La cella `[17]` crea `df_powerbi`; la `[18]` lo scrive come tabella Delta `quadratura_powerbi`.
L'Excel `export/riconciliazione_powerbi.xlsx` è **disattivato per default**; per attivarlo,
impostare `ESPORTA_EXCEL_POWERBI = True` nella cella `[1]`. Il file eventuale ha un solo foglio
`df_merge`. Se disattivato, un file precedente non viene aggiornato né eliminato.

Il dataset ha 28 colonne:

```
Fattura, Data fattura, Tipologia documento, CEAS, CFOR, Denominazione, Bolla,
Data bolla, Stato DDT, CPCO, CPCO descrizione, Descrizione, Numero riga fattura,
Unità di misura,
Codice articolo interno, Codice articolo fornitore, Codice EAN,
Quantità XML, Quantità carico, Differenza quantità (sui valori assoluti),
Prezzo unitario XML, Prezzo unitario carico,
Totale XML, Totale Mersy, Differenza totali,
Stato abbinamento, Tipo match articolo, Metodo match DDT
```

Le ultime due colonne descrivono il match già calcolato, senza modificarlo:

- `Tipo match articolo`: `EAN`, `CART`, `CALA`, `Nessun match` o `Solo carico`.
- `Metodo match DDT`: metodo della mappa DDT (`TESTO`, `DATA_UNIVOCA`, `UNICO_RESIDUO`,
  `UNICO_RESIDUO_DATA_MANCANTE`); vuoto quando non disponibile.

Il metodo DDT è vuoto sulle righe `Solo carico` e quando la chiave DDT è dedotta dal carico:
non significa necessariamente che la bolla non sia stata abbinata. Il campo `Stato DDT` resta la vista del risultato a livello di bolla.
Nella tabella Delta gli spazi nei nomi delle colonne diventano `_`. La tabella viene sovrascritta
insieme al suo schema: eventuali report Power BI esistenti devono considerare le nuove colonne.

Note sulle colonne di anagrafica:

- `CFOR` è il codice fornitore consolidato: quello dell'XML, altrimenti quello dei carichi.
- `Denominazione` è l'etichetta `(CFOR) Ragione Sociale`, per esempio `(12345) Granarolo`.
- `CEAS`, `CPCO` e `CPCO descrizione` arrivano **solo dal lato carichi**: sulle righe `Solo XML`
  restano vuote. È voluto — una bolla non ancora consegnata non ha punto di consegna, e nell'XML il
  `CEAS` non è un dato del documento (coincide con il nome del file).
- `Numero riga fattura` contiene il numero di linea XML e resta vuoto sulle righe senza lato XML.

Ogni colonna è un valore "consolidato" con una priorità dichiarata: prima il dato XML, poi
quello del gestionale (es. `Fattura` = numero XML, altrimenti `NDOGIAA`; `Data bolla` = `DataDDT`,
altrimenti `DataDDT_XML`, altrimenti `TDATIAB`). `Denominazione` viene propagata a tutte le righe
dello stesso fornitore, anche quelle `Solo carico`.

---

## 8. Tipi di dato nel file Excel

Excel non porta con sé uno schema: quello che conta è il tipo della singola cella, deciso da
pandas al momento della scrittura (`openpyxl`). In pratica:

| Colonne | Tipo nella cella |
|---|---|
| `Data fattura`, `Data bolla` | data reale (`datetime`), formato `DD/MM/YYYY` |
| `Quantità *`, `Prezzo *`, `Totale *`, `Differenza *` | numero |
| `Fattura`, `CEAS`, `CFOR`, `Denominazione`, `Bolla`, `CPCO descrizione`, `Codice articolo *`, `Codice EAN`, `Descrizione`, `Unità di misura`, `Numero riga fattura`, `Stato abbinamento` | testo |
| `CPCO` | numero intero |

Le celle senza valore restano **vuote** (non `0`, non `NA`). Attenzione a due punti quando il file
viene riletto da Power Query / Power BI: i codici numerici e gli EAN sono testo e vanno **forzati**
a testo nel caricamento, altrimenti vengono interpretati come numeri (perdita degli zeri iniziali,
notazione scientifica); le colonne data vanno tipizzate come data, non come testo.

Il file contiene valori, non formule: nessun ricalcolo lato Excel.

---

## 9. Requisiti ed esecuzione

### Log e debug

Ogni esecuzione avviata dalla cella `[1]` crea un file `.txt` distinto in
`Files/log/quadratura/`. Il percorso viene stampato nel notebook. All'inizio lo stato è
`IN_CORSO`; la cella `[18]` lo aggiorna con tempi, conteggi, anomalie e risultato della scrittura
Delta. Dei primi 100 XML non leggibili sono elencati nome ed errore; il conteggio totale è sempre
riportato e non viene salvato il contenuto dei file.

- `OK`: tabella aggiornata, nessuno degli avvisi rilevati nel riepilogo.
- `OK_CON_AVVISI`: ad esempio XML non leggibili, anomalie del dizionario, o tabella non scritta.
  Gli XML non leggibili **non bloccano** la pubblicazione, che può quindi essere parziale.
- `ERRORE`: errore intercettato durante la scrittura Delta, che viene comunque rilanciato.
  In questo caso la scrittura è indicata come `NON_CONFERMATA`, non come certamente annullata.
- `IN_CORSO`: la cella finale non ha aggiornato il log. Può indicare un'elaborazione ancora in corso,
  un'interruzione o un errore in una cella precedente: controllare l'esito e l'output del notebook
  o della pipeline. Non equivale a un successo né contiene necessariamente il dettaglio dell'errore.

Per mostrare anche anteprime e riepiloghi facoltativi, impostare `DEBUG = True` nella cella `[1]`.
Gli avvisi e i controlli restano attivi anche con `DEBUG = False`. Il log richiede permessi di
scrittura su OneLake e può contenere nomi di file e messaggi d'errore: limitarne l'accesso e definire
una politica di conservazione. Se la scrittura del log finale fallisce dopo la scrittura Delta,
la tabella può essere già aggiornata; verificare l'output dell'esecuzione.


- Runtime **Fabric / Synapse** con `notebookutils` (accesso a OneLake) e `openpyxl`.
- Per `[18]` occorrono una sessione Spark e un Lakehouse predefinito accessibile in scrittura:
  la tabella `quadratura_powerbi`, se già presente, viene sovrascritta insieme al suo schema.
- Le celle vanno eseguite **in ordine**: `[15]` presuppone tutte le precedenti (tranne `[6-bis]`,
  opzionale), `[16]` e `[17]` presuppongono `df_merge`, `[18]` presuppone `df_powerbi`.
- Il notebook è pensato per essere eseguito dall'alto verso il basso senza modifiche; i parametri
  da toccare stanno tutti nella sezione `[1]`.
- Il codice è difensivo per scelta: quasi tutti i merge usano `validate=`, i join sulle anagrafiche
  hanno assert sul numero di righe, le chiavi vuote vengono convertite in nulli (in pandas due
  chiavi nulle si incontrano, a differenza di SQL).

---

## 10. Test

Il notebook si può eseguire in locale senza Fabric, su dati sintetici:

```bash
pip install pandas openpyxl
python tests/verifica.py
```

Sostituisce solo `notebookutils`, le letture Excel e la scrittura su OneLake; il codice del notebook
viene eseguito così com'è. Esce con `0` se tutti i controlli passano, `1` se qualcuno fallisce.
Dettagli in [`tests/README.md`](tests/README.md).

---

## 11. Limiti noti

- `AliquotaIVA` e `CodiceFiscale` a livello di linea non vengono ancora estratti: la sezione `[13]`
  li aggregherebbe automaticamente se presenti.
- Una fattura fuori perimetro (senza `CFOR`) esce nel report come `Fornitore non disponibile`,
  anche quando il suo XML riporta la denominazione: il nome viene propagato tramite il codice
  fornitore, che in quel caso manca. Il caso è oggi considerato non significativo — si assume che
  ogni fattura abbia almeno un carico — ma è documentato nella cella del report insieme alle
  possibili strade, se in futuro non fosse più vero.
- `RiferimentoAmministrazione` è un tipo virtuale trattato come normale `CodiceArticolo` se
  codificato nel dizionario; il testo della descrizione non è più usato per ricavare codici.
- Se una fattura risulta associata a più `CFOR` il notebook lo segnala e tiene il primo in ordine
  alfabetico (sezione `[11]`).
- La numerazione `Indice` è progressiva **dopo** i filtri: non è stabile fra esecuzioni diverse se
  cambia il perimetro.
