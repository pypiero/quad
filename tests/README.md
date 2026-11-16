# Test del notebook

Esegue il notebook `Notebook_2 (1).ipynb` **senza Fabric**: i dati di origine sono sintetici, costruiti
in memoria. Serve a verificare che una modifica al codice non rompa la riconciliazione, prima di
rieseguire tutto su OneLake.

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
```

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
Vengono sostituite solo le tre cose che in locale non esistono:

| Nel notebook | Nel test |
|---|---|
| `notebookutils.fs.*` | filesystem finto: le copie sono no-op |
| `pd.read_excel` | tabelle sintetiche, smistate per nome file |
| `pd.ExcelWriter` | cartella temporanea (`tempfile`), non OneLake |
| `display()` | funzione che non stampa |

Lo ZIP degli XML non viene copiato: viene scritto direttamente nel percorso locale che il notebook
si aspetta (`zip_locale_python`), letto dal sorgente del notebook stesso. Se quel percorso cambia,
il test si adegua da solo.

## File

| File | Contenuto |
|---|---|
| `dati_sintetici.py` | XML, carichi, anagrafiche e dizionario (il fornitore `F005` ha il codice articolo scritto dentro la descrizione; il fornitore `F011` usa `PrioritaMatch` per far vincere il codice fornitore su EAN e descrizione) |
| `harness.py` | esecuzione del notebook con i sostituti sopra |
| `verifica.py` | i controlli veri e propri, con il riepilogo |

## Cosa copre

1. **Date DDT** — estrazione di `DataDDT`, casi con data assente e con linea non citata dal DDT;
2. **Denominazione** — estrazione del fornitore e propagazione fino al report;
3. **Abbinamento DDT** — i tre livelli `TESTO`, `DATA_UNIVOCA`, `UNICO_RESIDUO_DATA_MANCANTE`;
4. **DDT derivato** — XML senza bolla agganciato al DDT unico del carico, e caso con più DDT
   lasciato non abbinato con lo stato dedicato `DDT_AMBIGUO`;
5. **Tipologia documento** — `60I` / `60C`, ricavata dal carico anche sulle righe Solo XML;
6. **Stato DDT** — etichetta di bolla (non di riga): una riga `Solo carico` su una bolla
   riconciliata riporta lo stato della bolla, e tutti i nove valori sono coperti;
7. **Merge finale** — ordine EAN → CART → CALA, righe `Solo XML` / `Solo carico`, assenza di duplicati;
8. **Codici articolo** — normalizzazione per fornitore, righe senza codice, nature (`SC`, …);
9. **Normalizzazione sul lato carichi** — `CEAN` / `CART` / `CALA` da `RegoleCodiciCarico`, refuso nel
   `CampoCanonico` segnalato senza bloccare, regole disallineate fra i due fogli segnalate;
10. **Dizionario** — regola non riconosciuta e chiave duplicata segnalate senza bloccare;
11. **Perimetro e anagrafiche** — filtro `CDOCIAA`, precedenza `TDEC` su `CARF`, punti di consegna;
12. **Descrizione come codice e tipi codificati** — un fornitore che scrive il codice in coda alla
    descrizione viene abbinato lo stesso; un altro che lo scrive in testa (`ESTRAI_PRIMA_STRINGA`)
    si abbina anche quando la linea porta un `MINSAN` non codificato; la descrizione viene aggiunta
    a ogni linea e un codice vero prevale su di essa nello stesso campo; un `CodiceTipoXML` assente
    dal dizionario non entra nella tabella dei codici;
13. **Priorità dei codici** — `PrioritaMatch` cambia il livello vincente (il fornitore `F011` passa
    a `CALA` e trova l'articolo giusto anche quando l'EAN, lasciato al default, punterebbe altrove);
    senza colonna resta l'ordine storico; le anomalie (valore non valido, priorità duplicata, due
    tipi sullo stesso campo con priorità diverse) vengono segnalate senza bloccare, mentre una
    cella vuota è un campo non configurato e non produce avvisi. Verifica anche che
    `Codice articolo interno` prenda il valore dal carico e usi l'XML solo come ripiego, che
    `ChiaveArticoloXML` resti una chiave di raggruppamento e non segua la priorità, e che il
    dettaglio attivato da `CFOR_VERIFICA_MATCH` produca i tre livelli con l'articolo abbinato;
14. **Export** — file creati e tipo delle celle nell'xlsx (date, numeri, testo).

## Provare il test contro un'altra versione del notebook

```bash
QUAD_NOTEBOOK=/percorso/altro_notebook.ipynb python tests/verifica.py
```

## Limiti

- non verifica il comportamento su **Excel reale**: le letture sono simulate, quindi non copre
  celle numeriche nei codici, formati strani o colonne mancanti nei file veri;
- non verifica i **volumi** né le prestazioni;
- non sostituisce un'esecuzione su Fabric: serve a intercettare le regressioni logiche.
