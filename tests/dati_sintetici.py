"""
Dati sintetici per il test del notebook di riconciliazione.

Nessun file esterno: XML, carichi, anagrafiche e dizionario sono
costruiti qui in memoria, così il test gira anche senza OneLake.
"""

import pandas as pd


# ------------------------------------------------------------------
# XML
# ------------------------------------------------------------------

def xml_documento(numero, data, ddt_blocchi, linee):
    """
    Costruisce un XML FPR12 minimo ma valido per il notebook:
    intestazione con il fornitore, un body con una testata e le
    linee indicate.
    """

    return f"""<FatturaElettronica versione="FPR12">
<FatturaElettronicaHeader>
  <CedentePrestatore><DatiAnagrafici><Anagrafica>
    <Denominazione>FORNITORE {numero} SRL</Denominazione>
  </Anagrafica></DatiAnagrafici></CedentePrestatore>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
  <DatiGenerali>
    <DatiGeneraliDocumento>
      <TipoDocumento>TD24</TipoDocumento><Divisa>EUR</Divisa>
      <Data>{data}</Data><Numero>{numero}</Numero>
    </DatiGeneraliDocumento>
    {ddt_blocchi}
  </DatiGenerali>
  <DatiBeniServizi>{linee}</DatiBeniServizi>
</FatturaElettronicaBody>
</FatturaElettronica>"""


def linea(numero, descrizione, quantita, prezzo=None, totale=None,
          unita=None, natura=None, codici=()):
    """
    Un blocco DettaglioLinee. I codici sono coppie (tipo, valore).
    """

    campi = [
        f"<NumeroLinea>{numero}</NumeroLinea>",
        f"<Descrizione>{descrizione}</Descrizione>",
    ]

    if natura:
        campi.insert(
            0,
            f"<TipoCessionePrestazione>{natura}</TipoCessionePrestazione>",
        )

    if quantita is not None:
        campi.append(f"<Quantita>{quantita}</Quantita>")

    if unita:
        campi.append(f"<UnitaMisura>{unita}</UnitaMisura>")

    if prezzo is not None:
        campi.append(f"<PrezzoUnitario>{prezzo}</PrezzoUnitario>")

    if totale is not None:
        campi.append(f"<PrezzoTotale>{totale}</PrezzoTotale>")

    for tipo, valore in codici:
        campi.append(
            f"<CodiceArticolo><CodiceTipo>{tipo}</CodiceTipo>"
            f"<CodiceValore>{valore}</CodiceValore></CodiceArticolo>"
        )

    return "<DettaglioLinee>" + "".join(campi) + "</DettaglioLinee>"


def ddt(numero, data=None, righe=()):
    """
    Un blocco DatiDDT. DataDDT e RiferimentoNumeroLinea sono
    facoltativi nel tracciato: qui si possono omettere apposta.
    """

    campi = [f"<NumeroDDT>{numero}</NumeroDDT>"]

    if data:
        campi.append(f"<DataDDT>{data}</DataDDT>")

    campi += [
        f"<RiferimentoNumeroLinea>{riga}</RiferimentoNumeroLinea>"
        for riga in righe
    ]

    return "<DatiDDT>" + "".join(campi) + "</DatiDDT>"


XML_FILES = {
    # DDT esplicito su due linee, codici EAN e fornitore, una riga
    # sconto che nessun DDT cita.
    "IT01111111111_00001.xml": xml_documento(
        "00001", "2024-02-25",
        ddt("A/001", "2024-02-20", [1, 2]),
        "".join([
            linea(1, "PANE INTEGRALE", 10, 2.00, 20.00, "KG",
                  codici=[("EAN", "8001111111111")]),
            linea(2, "LATTE PS", 5, 3.00, 15.00, "LT",
                  codici=[("FORN", "art-002")]),
            linea(3, "SCONTO FEDELTA", 1, -2.00, -2.00, natura="SC"),
        ]),
    ),
    # DDT scritto diversamente sui due lati, stessa data: deve
    # scattare il livello DATA_UNIVOCA.
    "IT01111111111_00002.xml": xml_documento(
        "00002", "2024-04-05",
        ddt("X/1", "2024-04-01", [1]),
        linea(1, "BURRO", 4, 5.00, 20.00, "KG",
              codici=[("CLI", "C002")]),
    ),
    # DDT implicito e senza DataDDT: livello UNICO_RESIDUO.
    "IT02222222222_00007.xml": xml_documento(
        "7", "2024-03-10",
        ddt("B-2024/55"),
        linea(1, "YOGURT", 6, 1.50, 9.00, "PZ",
              codici=[("COD_F", "F22-1")]),
    ),
    # Fattura senza alcun carico: tutte le righe restano Solo XML.
    "IT03333333333_00009.xml": xml_documento(
        "9", "2024-05-01",
        ddt("Z/9", "2024-04-28", [1]),
        linea(1, "PRODOTTO IGNOTO", 1, 9.99, 9.99, "PZ"),
    ),
    # Carico con lo stesso EAN ma senza DDT: non deve abbinarsi.
    "IT01111111111_00003.xml": xml_documento(
        "00003", "2024-06-10",
        ddt("E/1", "2024-06-01", [1]),
        linea(1, "PANE INTEGRALE", 2, 2.00, 4.00, "KG",
              codici=[("EAN", "8001111111111")]),
    ),
    # F003: il codice fornitore e' scritto diversamente sui due lati
    # (ART002 nell'XML, ART/002 nel carico). Con la regola RIMUOVI_SEPARATORI
    # applicata a entrambi i lati i due valori coincidono.
    "IT05555555555_00012.xml": xml_documento(
        "00012", "2024-10-01",
        ddt("F/012", "2024-09-28", [1]),
        linea(1, "RICOTTA", 2, 4.00, 8.00, "KG",
              codici=[("FORN", "ART002")]),
    ),
    # F001/00013: l'XML NON riporta alcun DatiDDT, il carico ha un
    # solo DDT: la chiave va derivata e l'abbinamento deve avvenire.
    "IT01111111111_00013.xml": xml_documento(
        "00013", "2024-11-05", "",
        linea(1, "PANE INTEGRALE", 1, 2.00, 2.00, "KG",
              codici=[("EAN", "8001111111111")]),
    ),
    # F001/00014: XML senza DDT e carico con DUE DDT diversi:
    # il dato e' ambiguo, non si deriva nulla e resta non abbinato.
    "IT01111111111_00014.xml": xml_documento(
        "00014", "2024-11-06", "",
        linea(1, "PANE INTEGRALE", 1, 2.00, 2.00, "KG",
              codici=[("EAN", "8001111111111")]),
    ),
    # F001/00020: nota di credito (60C). Il 60C e' nel perimetro come
    # il 60I, quindi la riga merce si abbina normalmente; la riga di
    # sconto non ha codice articolo e resta Solo XML.
    "IT01111111111_00020.xml": xml_documento(
        "00020", "2024-12-01",
        ddt("R/20", "2024-11-25", [1]),
        "".join([
            linea(1, "RESO MERCE", 3, -2.00, -6.00, "KG",
                  codici=[("FORN", "ART-006")]),
            linea(2, "SCONTO RESO", 1, -1.00, -1.00, natura="SC"),
        ]),
    ),
    # Non FPR12: va scartato in lettura.
    "IT04444444444_00011.xml": xml_documento(
        "11", "2024-05-02", "",
        linea(1, "IGNORAMI", 1, 1, 1),
    ).replace('versione="FPR12"', 'versione="FPA11"'),
}


# ------------------------------------------------------------------
# CARICHI (una riga per articolo caricato)
# ------------------------------------------------------------------

def _carico(**kwargs):
    base = {
        "CAZI": "01", "CEDI": "1", "CPCO": 1, "CDOCIAA": "60I",
        "CUMF": "PZ", "CSTQ": "OK", "QTA ORDINE": 1, "QTA ACCETT": 1,
    }
    base.update(kwargs)
    return base


CARICHI = pd.DataFrame([
    _carico(CFOR="F001", NDOGIAA="00001", TDATIAA="2024-02-25",
            NDOGIAB="A-001", TDATIAB="2024-02-20", CART="C001",
            XART="PANE INTEGRALE", CALA="ART-001",
            CEAS="IT01111111111_00001", CUMF="KG",
            **{"Qtà": 10, "Importo_ns_fattura": 20.00, "PF02IAL": 2.00,
               "QTA ORDINE": 10, "QTA ACCETT": 10}),
    _carico(CFOR="F001", NDOGIAA="00001", TDATIAA="2024-02-25",
            NDOGIAB="A-001", TDATIAB="2024-02-20", CART="C002",
            XART="LATTE PS", CALA="ART-002",
            CEAS="IT01111111111_00001", CUMF="LT",
            **{"Qtà": 5, "Importo_ns_fattura": 15.00, "PF02IAL": 3.00,
               "QTA ORDINE": 5, "QTA ACCETT": 5}),
    # riga senza riscontro XML
    _carico(CFOR="F001", NDOGIAA="00001", TDATIAA="2024-02-25",
            NDOGIAB="A-001", TDATIAB="2024-02-20", CART="C003",
            CPCO=2, XART="ARTICOLO EXTRA", CALA="ART-003",
            CEAS="IT01111111111_00001",
            **{"Qtà": 1, "Importo_ns_fattura": 7.50, "PF02IAL": 7.50}),
    _carico(CFOR="F001", NDOGIAA="00002", TDATIAA="2024-04-05",
            NDOGIAB="DIVERSO/77", TDATIAB="2024-04-01", CART="C002",
            XART="BURRO", CALA="ART-002", CUMF="KG",
            CEAS="IT01111111111_00002",
            **{"Qtà": 4, "Importo_ns_fattura": 20.00, "PF02IAL": 5.00,
               "QTA ORDINE": 4, "QTA ACCETT": 4}),
    _carico(CFOR="F002", NDOGIAA="7", TDATIAA="2024-03-10",
            NDOGIAB="ALTRO", TDATIAB="2024-03-05", CART="C004",
            CPCO=2, XART="YOGURT", CALA="F22-1",
            CEAS="IT02222222222_00007",
            **{"Qtà": 6, "Importo_ns_fattura": 9.00, "PF02IAL": 1.50,
               "QTA ORDINE": 6, "QTA ACCETT": 6}),
    # carico senza DDT: stessa anagrafica ma nessun abbinamento
    _carico(CFOR="F001", NDOGIAA="00003", TDATIAA="2024-06-10",
            NDOGIAB=None, TDATIAB=None, CART="C001",
            XART="PANE INTEGRALE", CALA="ART-001", CUMF="KG",
            CEAS="IT01111111111_00003",
            **{"Qtà": 2, "Importo_ns_fattura": 4.00, "PF02IAL": 2.00,
               "QTA ORDINE": 2, "QTA ACCETT": 2}),
    # carico F003: stesso articolo, ma il codice porta un separatore
    _carico(CFOR="F003", NDOGIAA="00012", TDATIAA="2024-10-01",
            NDOGIAB="F-012", TDATIAB="2024-09-28", CART="C005",
            XART="RICOTTA", CALA="ART/002", CUMF="KG",
            CEAS="IT05555555555_00012",
            **{"Qtà": 2, "Importo_ns_fattura": 8.00, "PF02IAL": 4.00,
               "QTA ORDINE": 2, "QTA ACCETT": 2}),
    # carico 00013: un solo DDT, quindi derivabile
    _carico(CFOR="F001", NDOGIAA="00013", TDATIAA="2024-11-05",
            NDOGIAB="G/013", TDATIAB="2024-11-02", CART="C001",
            XART="PANE INTEGRALE", CALA="ART-001", CUMF="KG",
            CEAS="IT01111111111_00013",
            **{"Qtà": 1, "Importo_ns_fattura": 2.00, "PF02IAL": 2.00,
               "QTA ORDINE": 1, "QTA ACCETT": 1}),
    # carico 00014, primo DDT
    _carico(CFOR="F001", NDOGIAA="00014", TDATIAA="2024-11-06",
            NDOGIAB="H/1", TDATIAB="2024-11-02", CART="C001",
            XART="PANE INTEGRALE", CALA="ART-001", CUMF="KG",
            CEAS="IT01111111111_00014",
            **{"Qtà": 1, "Importo_ns_fattura": 2.00, "PF02IAL": 2.00,
               "QTA ORDINE": 1, "QTA ACCETT": 1}),
    # carico 00014, secondo DDT: rende ambigua la derivazione
    _carico(CFOR="F001", NDOGIAA="00014", TDATIAA="2024-11-06",
            NDOGIAB="H/2", TDATIAB="2024-11-03", CART="C001",
            XART="PANE INTEGRALE", CALA="ART-001", CUMF="KG",
            CEAS="IT01111111111_00014",
            **{"Qtà": 1, "Importo_ns_fattura": 2.00, "PF02IAL": 2.00,
               "QTA ORDINE": 1, "QTA ACCETT": 1}),
    # carico della nota di credito: tipo documento 60C.
    # La quantita' e' NEGATIVA mentre nell'XML e' positiva: e' il caso
    # in cui la differenza deve valere 0 e non 6.
    _carico(CFOR="F001", NDOGIAA="00020", TDATIAA="2024-12-01",
            NDOGIAB="R/20", TDATIAB="2024-11-25", CART="C006",
            XART="RESO MERCE", CALA="ART-006", CUMF="KG",
            CEAS="IT01111111111_00020", CDOCIAA="60C",
            **{"Qtà": -3, "Importo_ns_fattura": -6.00, "PF02IAL": -2.00,
               "QTA ORDINE": 3, "QTA ACCETT": 3}),
    # fuori perimetro: tipo documento diverso da 60I
    _carico(CFOR="F009", NDOGIAA="999", TDATIAA="2024-01-01",
            NDOGIAB="Q/1", TDATIAB="2024-01-01", CART="C009",
            XART="FUORI PERIMETRO", CALA="ART-009", CDOCIAA="99X",
            CEAS="IT09999999999_00099",
            **{"Qtà": 1, "Importo_ns_fattura": 1.00, "PF02IAL": 1.00}),
])


# ------------------------------------------------------------------
# ANAGRAFICHE
# ------------------------------------------------------------------

CPCO = pd.DataFrame([
    {"CPCO": 1, "XPCO": "PUNTO MILANO"},
    {"CPCO": 2, "XPCO": "PUNTO ROMA"},
])

EAN = pd.DataFrame([
    {"CART": "C001", "SBAR": "EAN", "CEAN": "8001111111111"},
    {"CART": "C002", "SBAR": "EAN", "CEAN": "8002222222222"},
    {"CART": "C003", "SBAR": "EAN", "CEAN": "8003333333333"},
    {"CART": "C004", "SBAR": "EAN", "CEAN": "8004444444444"},
    {"CART": "C005", "SBAR": "EAN", "CEAN": "8005555555555"},
    {"CART": "C006", "SBAR": "EAN", "CEAN": "8006666666666"},
])

CARF = pd.DataFrame([
    {"CART": "C001", "CFOR": "F001", "TDEC": "2024-01-01",
     "CARF": "ART-001", "XARF": "PANE"},
    {"CART": "C002", "CFOR": "F001", "TDEC": "2024-01-01",
     "CARF": "ART-002", "XARF": "LATTE"},
    # riga superata: deve perdere contro quella con TDEC piu' recente
    {"CART": "C002", "CFOR": "F001", "TDEC": "2019-01-01",
     "CARF": "ART-OLD", "XARF": "LATTE"},
    {"CART": "C003", "CFOR": "F001", "TDEC": "2024-01-01",
     "CARF": "ART-003", "XARF": "EXTRA"},
    {"CART": "C004", "CFOR": "F002", "TDEC": "2024-01-01",
     "CARF": "F22-1", "XARF": "YOGURT"},
    {"CART": "C005", "CFOR": "F003", "TDEC": "2024-01-01",
     "CARF": "ART/002", "XARF": "RICOTTA"},
    {"CART": "C006", "CFOR": "F001", "TDEC": "2024-01-01",
     "CARF": "ART-006", "XARF": "RESO"},
])


# ------------------------------------------------------------------
# DIZIONARIO DELLE REGOLE
# ------------------------------------------------------------------

DIZIONARIO = {
    "RegoleCodiciXML": pd.DataFrame([
        {"CFOR": "F001", "Denominazione": "uno", "CodiceTipoXML": "EAN",
         "CampoCanonico": "EAN", "RegolaNormalizzazione": "TESTO_MAIUSCOLO"},
        {"CFOR": "F001", "Denominazione": "uno", "CodiceTipoXML": "FORN",
         "CampoCanonico": "CODICE_FORNITORE",
         "RegolaNormalizzazione": "TESTO_MAIUSCOLO"},
        {"CFOR": "F001", "Denominazione": "uno", "CodiceTipoXML": "CLI",
         "CampoCanonico": "CODICE_CLIENTE",
         "RegolaNormalizzazione": "TESTO_MAIUSCOLO"},
        {"CFOR": "F002", "Denominazione": "due", "CodiceTipoXML": "COD_F",
         "CampoCanonico": "CODICE_FORNITORE",
         "RegolaNormalizzazione": "NESSUNA_REGOLA"},
        # regola scritta male: deve essere segnalata, non bloccare
        {"CFOR": "F002", "Denominazione": "due", "CodiceTipoXML": "X",
         "CampoCanonico": "EAN",
         "RegolaNormalizzazione": "REGOLA_INVENTATA"},
        {"CFOR": "F003", "Denominazione": "tre", "CodiceTipoXML": "FORN",
         "CampoCanonico": "CODICE_FORNITORE",
         "RegolaNormalizzazione": "RIMUOVI_SEPARATORI"},
        # F009: regola presente solo sul lato XML. Il lato carichi non
        # ha la riga e ricade sul default, quindi le due chiavi non
        # coincidono: la diagnostica deve segnalarlo.
        {"CFOR": "F009", "Denominazione": "nove", "CodiceTipoXML": "FORN",
         "CampoCanonico": "CODICE_FORNITORE",
         "RegolaNormalizzazione": "NESSUNA_REGOLA"},
    ]),
    "RegoleCodiciCarico": pd.DataFrame([
        {"CFOR": "F001", "Denominazione": "uno", "CampoCanonico": "EAN",
         "RegolaNormalizzazione": "TESTO_MAIUSCOLO"},
        {"CFOR": "F001", "Denominazione": "uno",
         "CampoCanonico": "CODICE_FORNITORE",
         "RegolaNormalizzazione": "TESTO_MAIUSCOLO"},
        {"CFOR": "F001", "Denominazione": "uno",
         "CampoCanonico": "CODICE_CLIENTE",
         "RegolaNormalizzazione": "TESTO_MAIUSCOLO"},
        {"CFOR": "F002", "Denominazione": "due",
         "CampoCanonico": "CODICE_FORNITORE",
         "RegolaNormalizzazione": "NESSUNA_REGOLA"},
        # duplicato: deve essere segnalato
        {"CFOR": "F001", "Denominazione": "uno", "CampoCanonico": "EAN",
         "RegolaNormalizzazione": "RIMUOVI_SEPARATORI"},
        {"CFOR": "F003", "Denominazione": "tre",
         "CampoCanonico": "CODICE_FORNITORE",
         "RegolaNormalizzazione": "RIMUOVI_SEPARATORI"},
        # refuso voluto: CODICE_FORNTORE invece di CODICE_FORNITORE.
        # La regola non deve essere applicata, ma il campo va segnalato.
        {"CFOR": "F003", "Denominazione": "tre",
         "CampoCanonico": "CODICE_FORNTORE",
         "RegolaNormalizzazione": "SOLO_NUMERI"},
    ]),
    "RegoleDDT": pd.DataFrame([
        {"CFOR": "F001", "Denominazione": "uno",
         "RegolaDDTXML": "RIMUOVI_SEPARATORI", "RegolaDDTCarico": "RIMUOVI_SEPARATORI"},
        {"CFOR": "F002", "Denominazione": "due",
         "RegolaDDTXML": "NESSUNA_REGOLA",
         "RegolaDDTCarico": "NESSUNA_REGOLA"},
    ]),
}
