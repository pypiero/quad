# Test dei notebook

Esegue `Quadratura_Fatture.ipynb` e `Assistente_Dizionario_Codici.ipynb` **senza Fabric**: i dati di
origine sono sintetici, costruiti in memoria. Serve a verificare che una modifica al codice non rompa
la riconciliazione o il banco di prove delle regole, prima di rieseguire tutto su OneLake.

## Requisiti

Solo due librerie:

```bash
pip install pandas openpyxl
```

Nessun accesso a rete, OneLake o file Excel di origine.

## Come si lancia

Dalla radice del repository:

```bash
python tests/verifica.py
python tests/test_delta.py
python tests/test_ottimizzazioni.py
python tests/test_export_diagnostico.py
python tests/test_report_match.py
python tests/test_priorita_report.py
python tests/test_log.py
python tests/test_assistente_dizionario.py
```

Il secondo comando verifica anche il caso di DataFrame vuoto e gli errori Spark; il terzo
controlla l'ordine dei codici XML e la riesecuzione del report senza modificare `df_merge`.
Il quarto verifica l'export diagnostico attivato e disattivato; il quinto verifica i campi match,
l'export Excel Power BI opzionale e la diagnostica delle regole. Il sesto verifica la scelta del
primo valore disponibile, compresi valori mancanti, numeri e date. Il settimo verifica il log
testuale, gli errori e il flag debug usando un filesystem finto. L'ottavo esegue il banco di prove
per il dizionario codici con gli stessi sostituti (più tre XML aggiuntivi) e ne controlla le griglie.
Le scritture Delta sono simulate: la compatibilità effettiva con Spark e il Lakehouse va verificata in Fabric.

Esce con:

| Codice | Significato |
|---|---|
| `0` | tutti i controlli superati |
| `1` | almeno un controllo fallito (il riepilogo elenca quali) |
| `2` | errore durante l'esecuzione (il notebook non gira) |

L'output è diviso in sezioni numerate, una per area funzionale, e termina con il riepilogo
`PASS/FAIL` e il conteggio finale.

## Cosa viene sostituito

Il codice del notebook **non viene modificato**: viene letto dall'`.ipynb` ed eseguito così com'è.
La suite `verifica.py` abilita il flag dell'Excel Power BI dopo la cella di configurazione per
testare anche il file opzionale; gli altri test verificano l'impostazione predefinita.
Vengono sostituite le dipendenze che in locale non esistono:

| Nel notebook | Nel test |
|---|---|
| `notebookutils.fs.*` | filesystem finto: copie no-op e log registrati in memoria |
| `pd.read_excel` | tabelle sintetiche, smistate per nome file |
| `pd.ExcelWriter` | cartella temporanea (`tempfile`), non OneLake |
| `display()` | funzione che non stampa |
| `spark` | oggetto finto che registra conversioni e scritture Delta, senza scrivere tabelle |

Lo ZIP degli XML non viene copiato: viene scritto direttamente nel percorso locale che il notebook
si aspetta (`zip_locale_python`), letto dal sorgente del notebook stesso. Se quel percorso cambia,
il test si adegua da solo.

## File

| File | Contenuto |
|---|---|
| `dati_sintetici.py` | XML, carichi, anagrafiche e dizionario (il fornitore `F005` ha il codice articolo scritto dentro la descrizione) |
| `harness.py` | esecuzione del notebook di quadratura con i sostituti sopra |
| `verifica.py` | i controlli veri e propri, con il riepilogo |
| `test_assistente_dizionario.py` | esecuzione e controlli dell'assistente per il dizionario codici |

## Cosa copre

1. **Date DDT** — estrazione di `DataDDT`, casi con data assente e con linea non citata dal DDT;
2. **Denominazione** — estrazione del fornitore e propagazione fino al report;
3. **Abbinamento DDT** — i tre livelli `TESTO`, `DATA_UNIVOCA`, `UNICO_RESIDUO_DATA_MANCANTE`;
4. **DDT derivato** — XML senza bolla agganciato al DDT unico del carico, e caso con più DDT
   lasciato non abbinato con lo stato dedicato `DDT_AMBIGUO`;
5. **Tipologia documento** — `60I` / `60C`, ricavata dal carico anche sulle righe Solo XML;
6. **Stato DDT** — etichetta di bolla (non di riga): una riga `Solo carico` su una bolla
   riconciliata riporta lo stato della bolla, e tutti i nove valori sono coperti;
7. **Merge finale** — cascata EAN → CART → CALA, righe `Solo XML` / `Solo carico`, assenza di duplicati;
8. **Codici articolo** — normalizzazione per fornitore, righe senza codice, nature (`SC`, …);
9. **Normalizzazione sul lato carichi** — `CEAN` / `CART` / `CALA` da `RegoleCodiciCarico`, refuso nel
   `CampoCanonico` segnalato senza bloccare, regole disallineate fra i due fogli segnalate;
10. **Dizionario** — regola non riconosciuta e chiave duplicata segnalate senza bloccare;
11. **Perimetro e anagrafiche** — filtro `CDOCIAA`, precedenza `TDEC` su `CARF`, punti di consegna;
12. **Descrizione e tipi codificati** — la descrizione non genera più un codice virtuale anche se
    il dizionario la codifica; i codici reali e la descrizione nel report restano disponibili e le
    righe che si abbinavano solo tramite descrizione restano non abbinate;
13. **Export** — file creati e tipo delle celle nell'xlsx (date, numeri, testo).

## Test dell'assistente dizionario

`test_assistente_dizionario.py` esegue le celle di `Assistente_Dizionario_Codici.ipynb` così come sono,
con un filesystem finto, le letture Excel sintetiche e l'Excel di output in una cartella temporanea.
Aggiunge tre XML ai `XML_FILES` sintetici: due tipi dal nome inedito ma con valori presenti in
`CEAN` / `CART` (`GTIN`, `CODICE_27`), un `RiferimentoAmministrazione`, un DDT che combacerebbe con
quello di **un'altra** fattura se il confronto non fosse per fattura, e un file non FPR12 da scartare.

Copre: l'identità delle 7 regole con il registro `REGOLE` della quadratura; i codici univoci senza
colonne di fattura; la griglia con tutte le 147 combinazioni per tipo; le proposte per `EAN` / `FORN`
/ `CLI` / `COD_F` / `GTIN` / `CODICE_27` e l'assenza di proposte per `MINSAN` / `XYZ`; il confronto
DDT per fattura (e la dimostrazione che un confronto globale troverebbe un match in più); le
proposte DDT per `TUTTI` e per `CFOR`; i 4 fogli dell'Excel e il fatto che **`Dizionario codici.xlsx`
non venga mai letto né scritto**.

## Provare il test contro un'altra versione del notebook

```bash
QUAD_NOTEBOOK=/percorso/altro_notebook.ipynb python tests/verifica.py
```

## Limiti

- non verifica il comportamento su **Excel reale**: le letture sono simulate, quindi non copre
  celle numeriche nei codici, formati strani o colonne mancanti nei file veri;
- non verifica i **volumi** né le prestazioni;
- non sostituisce un'esecuzione su Fabric: serve a intercettare le regressioni logiche.
