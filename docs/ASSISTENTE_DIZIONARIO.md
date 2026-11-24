# Assistente per il dizionario codici — come funziona

Guida a [`Assistente_Dizionario_Codici.ipynb`](../Assistente_Dizionario_Codici.ipynb): il notebook
**ausiliario** che scopre quali `CodiceTipoXML` arrivano nelle fatture e propone le righe da
aggiungere a `Dizionario codici.xlsx`. Non fa quadratura, non legge `df_merge`, non scrive Delta.

---

## 1. Il problema

La quadratura (`Quadratura_Fatture.ipynb`, sezione `[12]`) conserva solo i codici il cui
`CodiceTipoXML` è configurato, **per quel `CFOR`**, nel foglio `RegoleCodiciXML`. Un tipo non
configurato viene scartato: non c'è un errore, semplicemente non contribuisce alla chiave articolo e
la riga resta `Solo XML`.

Il tracciato FPR12 lascia `CodiceTipo` come testo libero. Nella pratica si incontrano, per lo stesso
significato, `EAN`, `GTIN`, `BARCODE`, `FORN`, `COD_F`, `SUPPLIER`, `CLI`, `CUSTOMER`, `CART`, e
accanto a questi codici che **non** sono articoli (`MINSAN`, `SSCC`, `ISBN`, `LOTTO`…). Censirli a
mano significa aprire gli XML fornitore per fornitore.

L'assistente risponde a: *«che tipi di codice ci sono, e sono EAN, codice cliente o codice
fornitore?»*, producendo una **proposta verificabile**, non una modifica automatica.

---

## 2. Input e avvio

| File | Uso |
|---|---|
| `xml.zip` | XML FPR12 (anche in sottocartelle) |
| `TAB_CM_Fatture_BI.xlsx` | `CEAS`, `NDOGIAA`, `CFOR`, `CART`, `CALA` |
| `TAB_ANAGRAFICA_EAN.xlsx` | `CEAN` |
| `TAB_ANAGRAFICA_CARF.xlsx` | `CARF` |
| `Dizionario codici.xlsx` | letto in sola lettura, per il confronto |

Tutti nella stessa `cartella` OneLake del notebook principale. Eseguire le celle `[1]`–`[8]` in
ordine. Con `MODALITA_LOCALE = True` i file si leggono da `CARTELLA_LOCALE` senza `notebookutils`
(utile per provare il notebook fuori da Fabric). `ESPORTA_PROPOSTE = False` lascia le tabelle in
memoria senza scrivere l'Excel.

Nella cella `[1]` si possono anche impostare `MAPPA_PIVA_CFOR` e le soglie
`SOGLIA_RISCONTRO`, `MIN_RISCONTRI`, `SOGLIA_ALTA`, `SOGLIA_MEDIA`, `MARGINE_MINIMO`.

---

## 3. Flusso, cella per cella

| # | Cosa fa | Produce |
|---|---|---|
| 1 | configurazione, percorsi, funzioni di lettura | `leggi_excel()`, costanti |
| 2 | parsing ZIP, solo `FPR12`, via gli `<Allegati>`, una riga per `CodiceArticolo` | `df_codici`, `df_documenti`, `df_errori` |
| 3 | attribuzione del `CFOR` | `df_codici['CFOR']`, `df_fornitori_da_mappare` |
| 4 | forme normalizzate, set di riferimento, checksum GTIN | `RIFERIMENTI`, `df_valori` |
| 5 | alias dei nomi, forma del valore, scelta della regola | `classifica_nome()`, `classifica_forma()`, `suggerisci_regola()` |
| 6 | punteggio e classificazione | `df_tipi` |
| 7 | confronto con il dizionario, proposte simmetriche | `df_proposte_xml`, `df_proposte_carico`, `df_da_verificare`, `df_regole_inutilizzate`, `df_anomalie` |
| 8 | riepilogo, anteprime, Excel | `export/proposte_dizionario_codici.xlsx` |

`df_valori` ha una riga per **valore distinto** di ogni `(CFOR, CodiceTipoXML)`: `df_tipi` ha una riga
per **tipo**, con occorrenze, valori distinti, esempi, quote di forma, riscontri e punteggi.

### Il tipo virtuale

Come nella sezione `[3]` della quadratura, `RiferimentoAmministrazione` viene ricreato come tipo
virtuale (`Origine = VIRTUALE`), altrimenti resterebbe invisibile a chi compila il dizionario. Viene
segnalato ma non classificato a priori: può essere un codice articolo oppure un riferimento
d'ordine, e la scelta dipende dal fornitore.

---

## 4. Il `CFOR`: il vincolo strutturale

**L'XML non contiene il `CFOR`**, ma `RegoleCodiciXML` è chiavato per `CFOR + CodiceTipoXML`.
L'assistente lo attribuisce con la stessa logica della sezione `[11]` della quadratura, in questo
ordine:

1. `MAPPA_PIVA_CFOR` (partita IVA o denominazione → `CFOR`): scelta manuale esplicita, prioritaria;
2. coppia `CEAS + NDOGIAA` dai carichi;
3. ripiego sul solo `CEAS`, se quel CEAS ha un unico fornitore;
4. altrimenti `CFOR` vuoto: la fattura finisce in `FornitoriDaMappare` con partita IVA (dall'intestazione
   o dal nome del file SDI), denominazione e un esempio di CEAS.

Una riga senza `CFOR` **non viene proposta**, nemmeno se il campo canonico è stato dedotto: finisce
in `DaVerificare` con `Azione = CFOR_MANCANTE`. Con più `CFOR` per la stessa fattura si tiene il
primo in ordine alfabetico e si stampa un avviso, come fa la quadratura.

---

## 5. I tre segnali

### 5.1 Nome del tipo

`ALIAS_GREZZI` (cella `[5]`) è una tabella di sinonimi: `EAN`, `EAN13`, `GTIN`, `BARCODE`,
`CODICE A BARRE` → `EAN`; `FORN`, `COD_F`, `SUPPLIER`, `CARF` → `CODICE_FORNITORE`; `CLI`,
`CUSTOMER`, `CART`, `CODICE INTERNO` → `CODICE_CLIENTE`. I nomi vengono normalizzati (accenti,
punteggiatura, maiuscole) prima del confronto.

Se il nome non è in tabella si cercano parole chiave (`EAN|GTIN|UPC|BARCODE`, `FORN|SUPPLIER|…`,
`CLI|CUSTOMER|CART|INTERN|…`): un nome che ne contiene per **due campi diversi** è ambiguo e non
assegna punti. `TIPI_NOTI` elenca i tipi che non sono codici articolo (`MINSAN`, `AIC`, `SSCC`,
`ISBN`, `LOTTO`, `Descrizione`, `RiferimentoAmministrazione`, `(senza tipo)`): vengono segnalati con
una motivazione, non classificati.

> Aggiungere un sinonimo nuovo significa aggiungere una stringa a `ALIAS_GREZZI`. È l'unico punto
> da mantenere quando arriva un fornitore con un nome inedito.

### 5.2 Forma del valore

- **GTIN valido**: 8, 12, 13 o 14 sole cifre con checksum GS1 (modulo 10) corretto → indizio
  forte di `EAN`;
- **solo cifre** di lunghezza 6–14 ma checksum non valido → indizio debole (molti codici interni
  sono numerici, e negli XML reali il checksum non sempre è rispettato);
- **alfanumerico** → la forma non distingue cliente da fornitore: non assegna punti.

`QuotaEANValida`, `QuotaSoloCifre`, `QuotaAlfanumerico` e `QuotaSeparatori` sono in `df_tipi`, così
la decisione si può rileggere.

### 5.3 Riscontro sui dati aziendali

Per ogni valore si calcolano fino a tre forme: pulito/maiuscolo, senza separatori e zeri iniziali,
sole cifre (quest'ultima **solo se il valore non contiene lettere**, per evitare che `ART002` diventi
`2` e combaci per caso con un codice numerico). Le stesse forme si costruiscono sui valori di
riferimento:

| Campo canonico | Riferimento |
|---|---|
| `EAN` | `CEAN` (anagrafica EAN) |
| `CODICE_CLIENTE` | `CART` (carichi) |
| `CODICE_FORNITORE` | `CARF` + `CALA` |

I set sono **per `CFOR`** quando disponibili, altrimenti globali. Il riscontro è **indicativo**:
serve a pesare un'ipotesi, non è il join della quadratura (che resta governato dal dizionario). Per
questo conta la quota di valori distinti trovati, non il numero di occorrenze.

---

## 6. Punteggio e confidenza

| Segnale | Peso |
|---|---|
| alias esatto sul nome | +4,0 |
| parola chiave sul nome | +2,5 |
| forma GTIN con checksum valido | +4,0 |
| forma solo numerica compatibile (checksum non valido) | +1,5 |
| riscontro forte: ≥`MIN_RISCONTRI` valori **e** quota ≥`SOGLIA_RISCONTRO` | +5,0 (+1,5 se il riscontro è esclusivo) |
| riscontro debole: 1 valore | +2,0 (+0,5 per ogni valore in più, max +1,5) |
| nome e riscontro concordi | +1,5 |

Vince il punteggio più alto, ma servono almeno **2,5 punti** e un **margine di 1,5** sul secondo
classificato. Un nome che indica un campo mentre i dati (o un GTIN valido) ne indicano un altro è un
`CONFLITTO`: il campo resta vuoto. Se il nome è sconosciuto e la decisione poggia solo sul riscontro,
la confidenza massima è `MEDIA`.

| Confidenza | Effetto |
|---|---|
| `ALTA` | proposta `AGGIUNGI` (se il tipo è assente) |
| `MEDIA` | proposta `AGGIUNGI`, ma da rileggere |
| `BASSA` | riga presente in `ProposteXML` ma `Azione = DA_VERIFICARE` |
| `NESSUNA` | nessun campo proposto: va in `DaVerificare` |

### Regola di normalizzazione

`suggerisci_regola()` propone `RIMUOVI_SEPARATORI` quando i valori hanno separatori o zeri iniziali,
`ESTRAI_PRIMA_STRINGA` / `ESTRAI_ULTIMA_STRINGA` quando il codice utile è una **parte** del valore
(un valore di un solo pezzo non viene mai "estratto"), `SOLO_NUMERI` quando c'è testo davanti a un
riferimento numerico. Senza evidenze scrive comunque il default in modo esplicito.

La regola suggerita vale **solo per le righe nuove**: su una riga già presente l'assistente non
propone di cambiarla, perché le regole dei due lati possono essere state scelte apposta. Segnala
solo le regole non riconosciute, che finiscono comunque in `AnomalieDizionario`.

---

## 7. Output

`export/proposte_dizionario_codici.xlsx` (in `MODALITA_LOCALE` il file è scritto direttamente in
`CARTELLA_LOCALE`, sempre con lo stesso nome):

| Foglio | Contenuto |
|---|---|
| `ProposteXML` | prime 5 colonne = schema di `RegoleCodiciXML`, poi metadati (`Azione`, `Confidenza`, `Motivazione`, …) |
| `ProposteCarico` | prime 4 colonne = schema di `RegoleCodiciCarico`, una riga per `CFOR + CampoCanonico` |
| `DaVerificare` | tipi non classificati, conflitti, `CFOR_MANCANTE`, con tutte le evidenze |
| `DettaglioTipi` | audit completo: conteggi, quote, punteggi, motivazioni |
| `FornitoriDaMappare` | partita IVA / denominazione / CEAS di chi non ha `CFOR` |
| `RegoleInutilizzate` | regole configurate ma mai osservate negli XML analizzati |
| `AnomalieDizionario` | `CampoCanonico` non ammesso, regola sconosciuta, chiavi duplicate |
| `Riepilogo` | conteggi dell'esecuzione |

`Azione`: `AGGIUNGI`, `GIA_PRESENTE`, `VERIFICA_REGOLA`, `VERIFICA_CONFLITTO`, `DA_VERIFICARE`,
`CFOR_MANCANTE`. **Si copiano solo le righe `AGGIUNGI` dopo averle verificate**; le colonne dopo le
prime cinque (o quattro) sono metadati e non vanno nel dizionario.

Le `ProposteCarico` esistono perché una riga assente sul lato carichi ricade su `RIMUOVI_SEPARATORI`,
mentre `NESSUNA_REGOLA` mantiene i separatori: il notebook principale segnala
«regole diverse fra i due lati» (sezione `[10]`). Proporre regole simmetriche evita il disallineamento.

> **`Dizionario codici.xlsx` non viene mai scritto.** L'assistente apre il file in lettura e produce
> un file separato. La scelta finale resta a chi conosce gli articoli del fornitore.

---

## 8. Limiti: quando l'automatismo non basta

1. **Cliente vs fornitore non si distingue dalla forma del valore**: entrambi sono spesso stringhe
   alfanumeriche. Servono il nome del tipo o il riscontro in `CART` / `CARF`. Senza entrambi il tipo
   resta `DA_VERIFICARE`, ed è voluto.
2. **L'EAN non è garantito dal checksum**: il controllo GS1 è un indizio, non un filtro. Un codice
   interno di 13 cifre può sembrare un GTIN; per questo la forma numerica da sola pesa 1,5 e non
   produce mai `ALTA`.
3. **Il riscontro può avere falsi positivi**: le tre forme normalizzate sono più permissive del join
   reale. Un solo valore che combacia pesa 2,0 e non basta da solo a classificare.
4. **Fatture senza carichi**: senza `CEAS + NDOGIAA` e senza `MAPPA_PIVA_CFOR` non c'è `CFOR`, quindi
   nessuna proposta. È il caso dei fornitori nuovi: va compilata la mappa nella cella `[1]`.
5. **Tipi non articolo**: mappare `MINSAN`, `SSCC` o un lotto come `EAN`/`CODICE_*` creerebbe
   abbinamenti falsi. Meglio lasciarli fuori finché una persona non decide.
6. **Perimetro**: solo documenti `versione="FPR12"` presenti in `xml.zip`. Altri tracciati e XML non
   letti (`df_errori`) non entrano nelle statistiche.
7. **Sinonimi**: un nome mai visto e con valori assenti dalle anagrafiche resta non classificato;
   si aggiunge l'alias in `ALIAS_GREZZI` e si riesegue.
8. **Regole esistenti**: non vengono mai riscritte, quindi l'assistente non corregge da sé un
   dizionario sbagliato; lo segnala (`VERIFICA_CONFLITTO`, `AnomalieDizionario`).
9. **Nessuna verifica a valle**: la bontà di una proposta si vede solo rieseguendo la quadratura.

---

## 9. Flusso consigliato e verifica

1. Eseguire l'assistente sullo ZIP corrente.
2. Verificare `ProposteXML` (soprattutto `MEDIA`), `DaVerificare` e `FornitoriDaMappare`; eventualmente
   mappare i `CFOR` mancanti e rieseguire.
3. Copiare le righe `AGGIUNGI` in `RegoleCodiciXML` e le relative `AGGIUNGI` in
   `RegoleCodiciCarico`.
4. Rieseguire `Quadratura_Fatture.ipynb` e controllare:
   - sezione `[12]`: deve calare «Codici esclusi perché il tipo non è nel dizionario»;
   - sezione `[10]`: `regole_non_allineate` deve restare vuota;
   - sezione `[6-bis]`: nessuna regola non riconosciuta o chiave duplicata;
   - report: meno righe `Solo XML` con `Documento trovato`.

---

## 10. Test

```bash
python tests/test_assistente_dizionario.py
```

Esegue le celle del notebook sui dati sintetici (`tests/dati_sintetici.py`) più cinque XML
aggiuntivi: un tipo dal nome sconosciuto ma riscontrabile in `CART`, GTIN con checksum valido, il
tipo virtuale, due fornitori senza carichi (uno mappato a mano). Controlla la classificazione di
`EAN`/`FORN`/`CLI`/`COD_F`, il rifiuto di `MINSAN`/`XYZ`, lo schema delle proposte, le anomalie del
dizionario, i fogli dell'Excel e che **`Dizionario codici.xlsx` non venga mai sovrascritto**.
