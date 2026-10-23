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
| `dati_sintetici.py` | XML, carichi, anagrafiche e dizionario |
| `harness.py` | esecuzione del notebook con i sostituti sopra |
| `verifica.py` | i controlli veri e propri, con il riepilogo |

## Cosa copre

1. **Date DDT** — estrazione di `DataDDT`, casi con data assente e con linea non citata dal DDT;
2. **Denominazione** — estrazione del fornitore e propagazione fino al report;
3. **Abbinamento DDT** — i tre livelli `TESTO`, `DATA_UNIVOCA`, `UNICO_RESIDUO_DATA_MANCANTE`;
4. **DDT derivato** — XML senza bolla agganciato al DDT unico del carico, e caso con più DDT
   lasciato non abbinato con lo stato dedicato `DDT_AMBIGUO`;
5. **Merge finale** — cascata EAN → CART → CALA, righe `Solo XML` / `Solo carico`, assenza di duplicati;
6. **Codici articolo** — normalizzazione per fornitore, righe senza codice, nature (`SC`, …);
7. **Normalizzazione sul lato carichi** — `CEAN` / `CART` / `CALA` da `RegoleCodiciCarico`, refuso nel
   `CampoCanonico` segnalato senza bloccare;
8. **Dizionario** — regola non riconosciuta e chiave duplicata segnalate senza bloccare;
9. **Perimetro e anagrafiche** — filtro `CDOCIAA`, precedenza `TDEC` su `CARF`, punti di consegna;
10. **Export** — file creati e tipo delle celle nell'xlsx (date, numeri, testo).

## Provare il test contro un'altra versione del notebook

```bash
QUAD_NOTEBOOK=/percorso/altro_notebook.ipynb python tests/verifica.py
```

## Limiti

- non verifica il comportamento su **Excel reale**: le letture sono simulate, quindi non copre
  celle numeriche nei codici, formati strani o colonne mancanti nei file veri;
- non verifica i **volumi** né le prestazioni;
- non sostituisce un'esecuzione su Fabric: serve a intercettare le regressioni logiche.
