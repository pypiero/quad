# Assistente dizionario codici — banco di prova

[`Assistente_Dizionario_Codici.ipynb`](../Assistente_Dizionario_Codici.ipynb) è un notebook
**autonomo e volutamente semplice**: non classifica, non ha alias, punteggi o confidenze. Prova
**tutte le combinazioni di regole** sui dati veri e conta quanti codici combaciano. Serve a decidere
cosa scrivere nei tre fogli di `Dizionario codici.xlsx`.

---

## 1. Perché

La quadratura (`Quadratura_Fatture.ipynb`, sezione `[12]`) scarta in silenzio ogni `CodiceTipoXML`
non configurato per quel `CFOR`, e le regole DDT sbagliate fanno fallire l'abbinamento in `[14]`.
Invece di indovinare nomi e regole, si misurano: si normalizzano i codici con ciascuna regola e si
conta quanti si ritrovano nelle anagrafiche.

## 2. Input e avvio

| File | Uso |
|---|---|
| `xml.zip` | XML `FPR12` (anche in sottocartelle) |
| `TAB_CM_Fatture_BI.xlsx` | `CART`, `CALA`, `NDOGIAB`, `CEAS`, `NDOGIAA`, `CFOR` |
| `TAB_ANAGRAFICA_EAN.xlsx` | `CEAN` |
| `TAB_ANAGRAFICA_CARF.xlsx` | `CARF` |

Stessa `cartella` OneLake della quadratura. Eseguire le celle `[1]`–`[5]` in ordine. Con
`MODALITA_LOCALE = True` si leggono i file da `CARTELLA_LOCALE` senza `notebookutils`;
`ESPORTA_PROPOSTE = False` lascia le tabelle in memoria.

**`Dizionario codici.xlsx` non viene letto**: il confronto con le regole esistenti si fa a occhio,
e il file non viene mai scritto.

## 3. Le regole provate

Le 7 regole sono copiate dal registro `REGOLE` della cella `[4]` della quadratura, pulizia di base
compresa: `RIMUOVI_SEPARATORI`, `RIMUOVI_ZERI`, `NESSUNA_REGOLA`, `TESTO_MAIUSCOLO`,
`SOLO_NUMERI`, `ESTRAI_PRIMA_STRINGA`, `ESTRAI_ULTIMA_STRINGA`. `normalizza(valore, regola)` è
l'unica funzione usata: la prova adotta quindi **la stessa normalizzazione** del processo.

A parità di match si preferisce la regola meno distruttiva, in quest'ordine:
`RIMUOVI_SEPARATORI` (il default), `RIMUOVI_ZERI`, `NESSUNA_REGOLA`, `TESTO_MAIUSCOLO`,
`SOLO_NUMERI`, `ESTRAI_PRIMA_STRINGA`, `ESTRAI_ULTIMA_STRINGA`.

## 4. Codici articolo: tutte le combinazioni, senza fatture

Si estraggono i **codici univoci** di tutti gli XML (più il tipo virtuale
`RiferimentoAmministrazione`), resi univoci su `CodiceTipoXML + valore pulito`. Non esistono colonne
di fattura né di `CFOR` in questa tabella: lo stesso EAN ripetuto in dieci fatture è **una** riga.

Per ogni `CodiceTipoXML` si provano:

```
3 campi canonici × 7 regole lato XML × 7 regole lato carico = 147 combinazioni
```

| Campo canonico | Valori di riferimento |
|---|---|
| `EAN` | `CEAN` |
| `CODICE_CLIENTE` | `CART` |
| `CODICE_FORNITORE` | `CARF` + `CALA` |

I codici XML si normalizzano con `RegolaXML`, i valori di riferimento con `RegolaCarico`; si conta
quanti codici univoci combaciano. Non servono alias: un tipo chiamato `GTIN` o `CODICE_27` viene
riconosciuto perché i suoi valori, normalizzati, stanno in `CEAN` o in `CART`.

Le chiavi normalizzate di 1–2 caratteri non vengono contate come match (`MIN_LUNGHEZZA_CHIAVE = 3`):
con `SOLO_NUMERI`, `ART-002` diventa `2` e combacerebbe per caso con `C002`. Le regole si provano
comunque tutte; si scarta solo l'accoppiamento evidentemente accidentale. Per i DDT questo filtro
non si applica, perché numeri di bolla corti come `H/1` sono normali.

## 5. DDT: tutte le combinazioni, dentro ogni fattura

Qui il confronto resta **dentro la singola fattura** (`CEAS + numero fattura`): si prendono i
`NumeroDDT` dell'XML e gli `NDOGIAB` dei carichi **di quella fattura**, e si provano le 7 × 7
regole. Un DDT della fattura A non può mai incrociare la bolla della fattura B: senza questo
vincolo `A/001` di una fattura combacerebbe con `A-001` di un'altra.

I match si sommano su tutte le fatture, complessivamente (`CFOR = TUTTI`) e per fornitore. Le
fatture senza DDT su uno dei due lati non entrano nel conteggio.

## 6. Output

`export/proposte_dizionario_codici.xlsx` (in `MODALITA_LOCALE` viene scritto in `CARTELLA_LOCALE`):

| Foglio | Contenuto |
|---|---|
| `ProposteCodici` | una riga per `CodiceTipoXML`: miglior `CampoCanonico`, `RegolaXML`, `RegolaCarico`, `Match`, `CodiciUnivoci`, `Quota`, `CFOR osservati`, `Stato`, `EsempiMatch` |
| `ProposteDDT` | una riga per `CFOR` (+ `TUTTI`): miglior `RegolaDDTXML`, `RegolaDDTCarico`, `Match`, `DDTXML`, `Quota`, `Fatture` |
| `GrigliaCodici` | tutte le 147 combinazioni per tipo, con i relativi match |
| `GrigliaDDT` | le 49 combinazioni complessive |

`Stato = NESSUN MATCH` significa che nessuna combinazione ha trovato riscontro: campo e regole
restano vuoti e quel tipo va guardato a mano (per esempio `MINSAN`, `SSCC`, lotti).

Come si copiano le righe:

- `ProposteCodici` → `RegoleCodiciXML` (`CFOR` × `CodiceTipoXML` → `CampoCanonico`,
  `RegolaNormalizzazione` = `RegolaXML`) e `RegoleCodiciCarico` (per ogni `CFOR osservati` +
  `CampoCanonico`, `RegolaNormalizzazione` = `RegolaCarico`);
- `ProposteDDT` → `RegoleDDT` (`CFOR` → `RegolaDDTXML`, `RegolaDDTCarico`). La riga `TUTTI` è un
  riassunto: se i fornitori si comportano diversamente, usare le righe per `CFOR`.

## 7. Limiti

1. **È una misura, non una verità**: un match dice che una certa regola fa coincidere due stringhe,
   non che il campo canonico sia semanticamente corretto. In caso di parità guardare `GrigliaCodici`
   ed `EsempiMatch`.
2. **Le anagrafiche devono contenere i codici**: un tipo i cui valori non compaiono in `CEAN`,
   `CART` o `CARF`/`CALA` dà zero match anche se è un codice articolo valido.
3. **`SOLO_NUMERI` e le regole di estrazione** possono accorciare i valori: il filtro sulle chiavi
   corte limita i falsi positivi sui codici articolo, ma le combinazioni restano visibili in griglia.
4. **I DDT si confrontano solo per testo**: la quadratura ha anche i livelli `DATA_UNIVOCA` e
   `UNICO_RESIDUO`, che qui non vengono simulati. Le regole migliori sono quindi quelle che
   massimizzano il match di livello `TESTO`.
5. **`CFOR`**: per i codici articolo è solo un'etichetta ricavata dai carichi (`CEAS + NDOGIAA`);
   per i DDT viene dai carichi della fattura. Le fatture senza carichi non producono DDT confrontabili.
6. **Perimetro**: solo `FPR12` presenti nello ZIP; gli XML non letti sono in `df_errori`.
7. **Nessuna scrittura automatica**: si copia a mano, poi si riesegue la quadratura e si controllano
   in `[12]` i «Codici esclusi perché il tipo non è nel dizionario» e in `[10]` le
   `regole_non_allineate`.

---

## 8. Test

```bash
python tests/test_assistente_dizionario.py
```

Esegue le celle su dati sintetici più tre XML aggiuntivi. Controlla che le 7 regole normalizzino
**esattamente** come la quadratura, che i codici siano univoci e senza colonne di fattura, che la
griglia contenga tutte le 147 combinazioni per tipo, che tipi dal nome inedito (`GTIN`,
`CODICE_27`) vengano individuati dal solo riscontro, che `MINSAN`/`XYZ` non producano proposte, che
i DDT siano confrontati per fattura, che le proposte DDT esistano per `TUTTI` e per `F001`, e che
l'Excel abbia 4 fogli senza mai leggere né scrivere il dizionario.
