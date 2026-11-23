"""
Controlli sul notebook di riconciliazione, eseguiti su dati sintetici.

Uso, dalla radice del repository:

    python tests/verifica.py

Esce con codice 0 se tutti i controlli passano, 1 altrimenti.
Non richiede Fabric, OneLake né i file Excel di origine: servono
solo pandas e openpyxl.
"""

import sys
import traceback
from pathlib import Path

import openpyxl
import pandas as pd

import harness

ESITI = []


def controlla(nome, condizione, dettaglio=""):
    ESITI.append((nome, bool(condizione), dettaglio))


def titolo(numero, testo):
    print()
    print("=" * 78)
    print(f"{numero}. {testo}")
    print("=" * 78)


def mostra(tabella):
    """to_string che accetta un segnaposto anche sulle colonne numeriche."""
    return (
        tabella
        .astype(object)
        .mask(tabella.isna(), "-")
        .to_string(index=False)
    )


def verifica_data_ddt(df_xml_fatture):
    titolo(1, "ESTRAZIONE DELLE DATE DDT (cella [3])")

    attese = {
        ("IT01111111111_00001.xml", 1): "2024-02-20",
        ("IT01111111111_00001.xml", 2): "2024-02-20",
        ("IT01111111111_00001.xml", 3): None,      # linea non citata
        ("IT01111111111_00002.xml", 1): "2024-04-01",
        ("IT02222222222_00007.xml", 1): None,      # DDT senza DataDDT
        ("IT03333333333_00009.xml", 1): "2024-04-28",
        ("IT01111111111_00003.xml", 1): "2024-06-01",
    }

    for (file_xml, numero_linea), atteso in attese.items():

        riga = df_xml_fatture.loc[
            (df_xml_fatture["FileXML"] == file_xml)
            & (df_xml_fatture["NumeroLinea"] == numero_linea)
        ]

        valore = riga["DataDDT"].iloc[0]
        ottenuto = None if pd.isna(valore) else valore.strftime("%Y-%m-%d")

        controlla(
            f"DataDDT {file_xml} linea {numero_linea}",
            ottenuto == atteso,
            f"atteso {atteso}, ottenuto {ottenuto}",
        )

    print(mostra(df_xml_fatture[[
        "FileXML", "NumeroLinea", "NumeroDDT", "DataDDT",
        "TipoAbbinamentoDDT",
    ]]))

    controlla(
        "DataDDT è di tipo data",
        pd.api.types.is_datetime64_any_dtype(df_xml_fatture["DataDDT"]),
        str(df_xml_fatture["DataDDT"].dtype),
    )
    controlla(
        "documento non FPR12 scartato in lettura",
        "IT04444444444_00011.xml" not in set(df_xml_fatture["FileXML"]),
        str(sorted(set(df_xml_fatture["FileXML"]))),
    )


def verifica_denominazione(df_xml_fatture, df_xml_righe, df_merge):
    titolo(2, "DENOMINAZIONE DEL FORNITORE (cella [3])")

    if "Denominazione" not in df_xml_fatture.columns:

        # Colonna sparita: si segnala e si evita di leggere colonne
        # che non esistono, così il riepilogo resta leggibile.
        controlla(
            "colonna Denominazione presente in df_xml_fatture",
            False,
            "colonna assente",
        )
        controlla(
            "Denominazione aggregata in df_xml_righe (cella [13])",
            "Denominazione" in df_xml_righe.columns,
            "colonna assente a monte",
        )
        controlla(
            "Denominazione presente in df_merge (cella [15])",
            "Denominazione" in df_merge.columns,
            "colonna assente a monte",
        )
        return

    print(mostra(df_xml_fatture[[
        "FileXML", "NumeroFattura", "Denominazione",
    ]]))

    controlla(
        "colonna Denominazione presente in df_xml_fatture",
        True,
    )
    controlla(
        "valorizzata su tutte le righe XML",
        df_xml_fatture["Denominazione"].notna().all(),
        f"{int(df_xml_fatture['Denominazione'].isna().sum())} righe vuote",
    )
    controlla(
        "valore corretto per F001",
        set(
            df_xml_fatture.loc[
                df_xml_fatture["FileXML"].str.startswith("IT01111111111_"),
                "Denominazione",
            ]
        ) == {"FORNITORE 00001 SRL", "FORNITORE 00002 SRL",
              "FORNITORE 00003 SRL", "FORNITORE 00013 SRL",
              "FORNITORE 00014 SRL", "FORNITORE 00020 SRL"},
        str(sorted(set(df_xml_fatture["Denominazione"]))),
    )
    controlla(
        "aggregata in df_xml_righe (cella [13])",
        "Denominazione" in df_xml_righe.columns
        and df_xml_righe["Denominazione"].notna().all(),
    )
    controlla(
        "presente in df_merge (cella [15])",
        "Denominazione" in df_merge.columns
        and df_merge["Denominazione"].notna().any(),
    )


def verifica_map_ddt(map_ddt):
    titolo(3, "ABBINAMENTO DDT (cella [14])")

    print(mostra(map_ddt[[
        "NumeroFattura", "NumeroDDT_XML", "NDOGIAB_Carico",
        "MetodoMatchDDT", "ChiaveDDT_Comune",
    ]]))

    metodi = set(map_ddt["MetodoMatchDDT"])

    for metodo in ("TESTO", "DATA_UNIVOCA", "UNICO_RESIDUO_DATA_MANCANTE"):
        controlla(f"metodo {metodo} usato", metodo in metodi, str(metodi))

    coppia = map_ddt.loc[map_ddt["NumeroFattura"] == "00002"]
    controlla(
        "00002: abbinato per data (X/1 <-> DIVERSO/77)",
        len(coppia) == 1 and coppia["MetodoMatchDDT"].iloc[0] == "DATA_UNIVOCA",
        str(coppia[["NumeroDDT_XML", "MetodoMatchDDT"]].to_dict("records")),
    )

    coppia = map_ddt.loc[map_ddt["NumeroFattura"] == "7"]
    controlla(
        "F002: DDT senza data abbinato come residuo unico",
        len(coppia) == 1
        and coppia["MetodoMatchDDT"].iloc[0] == "UNICO_RESIDUO_DATA_MANCANTE",
        str(coppia[["NumeroDDT_XML", "MetodoMatchDDT"]].to_dict("records")),
    )


def verifica_merge(df_merge):
    titolo(4, "MERGE FINALE (cella [15])")

    colonne = [
        "NumeroFattura", "ChiaveArticoloXML", "NumeriLineaXML",
        "NumeroDDT_Comune", "TipoMatch", "StatoAbbinamento",
        "StatoDocumento", "MetodoMatchDDT",
    ]
    print(mostra(df_merge[colonne]))

    attesi = [
        ("00001", "EAN|8001111111111", "EAN", "Abbinato", "TESTO"),
        ("00001", "FORN|ART-002", "CALA", "Abbinato", "TESTO"),
        ("00001", "SCONTO|3", "Nessun match", "Solo XML", None),
        ("00002", "CART|C002", "CART", "Abbinato", "DATA_UNIVOCA"),
        ("7", "FORN|F22-1", "CALA", "Abbinato", "UNICO_RESIDUO_DATA_MANCANTE"),
        ("9", "RIGA DESCRITTIVA|1", "Nessun match", "Solo XML", None),
        ("00013", "EAN|8001111111111", "EAN", "Abbinato", None),
        ("00014", "EAN|8001111111111", "Nessun match", "Solo XML", None),
    ]

    for fattura, chiave, tipo, stato, metodo in attesi:

        riga = df_merge.loc[
            (df_merge["NumeroFattura"] == fattura)
            & (df_merge["ChiaveArticoloXML"] == chiave)
        ]

        esito = (
            len(riga) == 1
            and riga["TipoMatch"].iloc[0] == tipo
            and riga["StatoAbbinamento"].iloc[0] == stato
        )

        if esito and metodo is not None:
            esito = riga["MetodoMatchDDT"].iloc[0] == metodo

        controlla(
            f"merge {fattura} / {chiave}",
            esito,
            str(riga[["TipoMatch", "StatoAbbinamento"]].to_dict("records")),
        )

    solo_carico = df_merge.loc[df_merge["StatoAbbinamento"] == "Solo carico"]

    controlla(
        "righe carico senza riscontro XML -> Solo carico",
        len(solo_carico) == 4
        and "ARTICOLO EXTRA"
        in set(solo_carico["mersy_descrizione_articolo(XART)"]),
        str(solo_carico[["mersy_descrizione_articolo(XART)"]].to_dict("records")),
    )
    controlla(
        "Solo carico: colonne XML vuote, valori Mersy presenti",
        solo_carico["NumeroFattura"].isna().all()
        and solo_carico["mersy_n_fattura(NDOGIAA)"].notna().all(),
    )
    controlla(
        "carico senza DDT: nessun abbinamento anche con EAN identico",
        "Senza DDT" in set(df_merge["NumeroDDT_Comune"]),
    )
    controlla(
        "merge senza duplicati (19 righe)",
        len(df_merge) == 19,
        str(len(df_merge)),
    )
    controlla(
        "ogni riga XML compare una volta sola",
        int(df_merge["ID_Riga_XML"].notna().sum()) == 15
        and df_merge["ID_Riga_XML"].dropna().is_unique,
        str(int(df_merge["ID_Riga_XML"].notna().sum())),
    )
    controlla(
        "ogni riga carico compare una volta sola",
        int(df_merge["Indice"].notna().sum()) == 13
        and df_merge["Indice"].dropna().is_unique,
        str(int(df_merge["Indice"].notna().sum())),
    )


def verifica_ddt_derivato(df_merge):
    titolo(5, "XML SENZA DDT: DDT UNICO DEL CARICO E CASO AMBIGUO")

    colonne = [
        "NumeroFattura", "ChiaveDDT_ComuneXML", "OrigineChiaveDDT",
        "DDTDistintiCarico", "StatoDocumento", "NumeroDDT_Comune",
        "TipoMatch", "StatoAbbinamento",
    ]
    print(mostra(df_merge.loc[
        df_merge["NumeroFattura"].isin(["00013", "00014"]), colonne
    ]))

    riga = df_merge.loc[df_merge["NumeroFattura"] == "00013"]
    controlla(
        "XML senza DDT: chiave derivata dal DDT unico del carico",
        len(riga) == 1
        and riga["OrigineChiaveDDT"].iloc[0] == "DDT_UNICO_CARICO",
        str(riga[["OrigineChiaveDDT", "ChiaveDDT_ComuneXML"]].to_dict("records")),
    )
    controlla(
        "XML senza DDT: la riga risulta abbinata",
        len(riga) == 1 and riga["StatoAbbinamento"].iloc[0] == "Abbinato",
        str(riga[["StatoAbbinamento", "TipoMatch"]].to_dict("records")),
    )
    controlla(
        "XML senza DDT: il documento risulta trovato",
        len(riga) == 1 and riga["StatoDocumento"].iloc[0] == "Documento trovato",
        str(riga["StatoDocumento"].tolist()),
    )
    controlla(
        "XML senza DDT: la bolla del carico compare nel report",
        len(riga) == 1 and riga["NumeroDDT_Comune"].iloc[0] == "G/013",
        str(riga["NumeroDDT_Comune"].tolist()),
    )

    riga = df_merge.loc[
        (df_merge["NumeroFattura"] == "00014")
        & df_merge["ID_Riga_XML"].notna()
    ]
    controlla(
        "due DDT sul carico: chiave non derivata",
        len(riga) == 1 and pd.isna(riga["ChiaveDDT_ComuneXML"].iloc[0]),
        str(riga["ChiaveDDT_ComuneXML"].tolist()),
    )
    controlla(
        "due DDT sul carico: stato dedicato DDT_AMBIGUO",
        len(riga) == 1 and riga["OrigineChiaveDDT"].iloc[0] == "DDT_AMBIGUO",
        str(riga["OrigineChiaveDDT"].tolist()),
    )
    controlla(
        "due DDT sul carico: stato documento 'DDT ambiguo'",
        len(riga) == 1 and riga["StatoDocumento"].iloc[0] == "DDT ambiguo",
        str(riga["StatoDocumento"].tolist()),
    )
    controlla(
        "due DDT sul carico: nessun abbinamento",
        len(riga) == 1 and riga["StatoAbbinamento"].iloc[0] == "Solo XML",
        str(riga["StatoAbbinamento"].tolist()),
    )
    controlla(
        "nessuna riga XML resta priva di chiave senza motivo",
        set(
            df_merge.loc[
                df_merge["ID_Riga_XML"].notna()
                & df_merge["ChiaveDDT_ComuneXML"].isna(),
                "OrigineChiaveDDT",
            ]
        ) <= {"NESSUNA_CHIAVE", "DDT_AMBIGUO", "ORFANO"},
        str(df_merge.loc[
            df_merge["ID_Riga_XML"].notna()
            & df_merge["ChiaveDDT_ComuneXML"].isna(),
            ["NumeroFattura", "OrigineChiaveDDT"],
        ].to_dict("records")),
    )


def verifica_tipologia(df_merge, df_powerbi):
    titolo(6, "TIPOLOGIA DEL DOCUMENTO (cella [15], 8-ter)")

    colonne = [
        "NumeroFattura", "TipologiaDocumento", "StatoAbbinamento",
    ]
    print(df_merge[colonne].to_string(index=False))

    def tipologie(fattura):
        return set(
            df_merge.loc[
                df_merge["NumeroFattura"] == fattura, "TipologiaDocumento"
            ]
        )

    controlla(
        "fattura 60I riconosciuta",
        tipologie("00001") == {"60I"},
        str(tipologie("00001")),
    )
    controlla(
        "nota di credito 60C riconosciuta",
        tipologie("00020") == {"60C"},
        str(tipologie("00020")),
    )
    controlla(
        "riga Solo XML: tipologia ricavata dal carico della fattura",
        set(
            df_merge.loc[
                (df_merge["NumeroFattura"] == "00001")
                & df_merge["ID_Riga_XML"].notna()
                & df_merge["StatoAbbinamento"].eq("Solo XML"),
                "TipologiaDocumento",
            ]
        ) == {"60I"},
        str(df_merge.loc[
            df_merge["NumeroFattura"] == "00001",
            ["StatoAbbinamento", "TipologiaDocumento"],
        ].to_dict("records")),
    )
    controlla(
        "riga Solo XML di una nota di credito: 60C dal carico",
        set(
            df_merge.loc[
                (df_merge["NumeroFattura"] == "00020")
                & df_merge["StatoAbbinamento"].eq("Solo XML"),
                "TipologiaDocumento",
            ]
        ) == {"60C"},
        str(df_merge.loc[
            df_merge["NumeroFattura"] == "00020",
            ["StatoAbbinamento", "TipologiaDocumento"],
        ].to_dict("records")),
    )
    controlla(
        "fattura assente dai carichi: tipologia vuota, non inventata",
        df_merge.loc[
            df_merge["NumeroFattura"] == "9", "TipologiaDocumento"
        ].isna().all(),
        str(df_merge.loc[
            df_merge["NumeroFattura"] == "9", "TipologiaDocumento"
        ].tolist()),
    )
    controlla(
        "solo 60I e 60C nel report",
        set(df_powerbi["Tipologia documento"].dropna()) <= {"60I", "60C"},
        str(sorted(set(df_powerbi["Tipologia documento"].dropna()))),
    )


def verifica_stato_ddt(df_merge):
    titolo(7, "STATO DEL DDT, A LIVELLO DI BOLLA (cella [15], 8-bis)")

    colonne = [
        "NumeroFattura", "NumeroDDT_Comune", "StatoAbbinamento", "StatoDDT",
    ]
    print(mostra(df_merge[colonne]))

    etichette = {
        "Bolla abbinata per numero",
        "Bolla abbinata per data",
        "Bolla abbinata per esclusione",
        "Bolla abbinata per esclusione, data mancante",
        "Bolla dedotta dal carico",
        "Bolla ambigua: più bolle nel carico",
        "Bolla XML senza riscontro nei carichi",
        "Bolla carico senza riscontro nell'XML",
        "Nessuna bolla",
    }

    controlla(
        "tutte le righe hanno uno stato riconosciuto",
        set(df_merge["StatoDDT"]) <= etichette,
        str(sorted(set(df_merge["StatoDDT"]) - etichette)),
    )
    controlla(
        "nessuno stato mancante",
        df_merge["StatoDDT"].notna().all(),
        str(int(df_merge["StatoDDT"].isna().sum())),
    )

    # il punto centrale: lo stato e' della bolla, non della riga.
    # La bolla A/001 di 00001 ha due righe abbinate e una che
    # esiste solo nei carichi: devono dire tutte la stessa cosa.
    stato_a001 = set(
        df_merge.loc[
            df_merge["NumeroDDT_Comune"] == "A/001", "StatoDDT"
        ]
    )
    controlla(
        "righe Solo carico e Abbinato della stessa bolla: stesso stato",
        stato_a001 == {"Bolla abbinata per numero"},
        str(sorted(stato_a001)),
    )
    solo_carico_a001 = df_merge.loc[
        df_merge["NumeroDDT_Comune"].isin(["A/001", "A-001"])
        & df_merge["StatoAbbinamento"].eq("Solo carico")
    ]
    controlla(
        "la riga articolo non trovato non cambia lo stato della bolla",
        len(solo_carico_a001) == 1
        and solo_carico_a001["StatoDDT"].eq("Bolla abbinata per numero").all(),
        str(solo_carico_a001[["StatoAbbinamento", "StatoDDT"]].to_dict("records")),
    )

    def stato(fattura, colonna="NumeroFattura", valore=None):
        return set(
            df_merge.loc[
                df_merge[colonna] == (fattura if valore is None else valore),
                "StatoDDT",
            ]
        )

    controlla(
        "abbinamento per numero (00012)",
        stato("00012") == {"Bolla abbinata per numero"},
        str(stato("00012")),
    )
    controlla(
        "abbinamento per data (00002)",
        stato("00002") == {"Bolla abbinata per data"},
        str(stato("00002")),
    )
    controlla(
        "abbinamento per esclusione con data mancante (7)",
        stato("7") == {"Bolla abbinata per esclusione, data mancante"},
        str(stato("7")),
    )
    controlla(
        "bolla dedotta dal carico (00013)",
        stato("00013") == {"Bolla dedotta dal carico"},
        str(stato("00013")),
    )
    controlla(
        "bolla ambigua (00014, riga XML senza DDT)",
        set(
            df_merge.loc[
                (df_merge["NumeroFattura"] == "00014")
                & df_merge["ID_Riga_XML"].notna(),
                "StatoDDT",
            ]
        ) == {"Bolla ambigua: più bolle nel carico"},
        str(stato("00014")),
    )
    controlla(
        "bolla dei carichi non abbinata (00014, H/1 e H/2)",
        set(
            df_merge.loc[
                df_merge["NumeroDDT_Comune"].isin(["H/1", "H/2"]), "StatoDDT"
            ]
        ) == {"Bolla carico senza riscontro nell'XML"},
        str(df_merge.loc[
            df_merge["NumeroDDT_Comune"].isin(["H/1", "H/2"]),
            ["NumeroDDT_Comune", "StatoDDT"],
        ].to_dict("records")),
    )
    controlla(
        "bolla XML non abbinata (00003 / E/1)",
        set(
            df_merge.loc[df_merge["NumeroDDT_Comune"] == "E/1", "StatoDDT"]
        ) == {"Bolla XML senza riscontro nei carichi"},
        str(stato("00003")),
    )
    controlla(
        "carico senza alcun DDT: nessuna bolla",
        set(
            df_merge.loc[
                df_merge["NumeroDDT_Comune"] == "Senza DDT", "StatoDDT"
            ]
        ) <= {"Nessuna bolla", "Bolla ambigua: più bolle nel carico"},
        str(df_merge.loc[
            df_merge["NumeroDDT_Comune"] == "Senza DDT",
            ["NumeroFattura", "StatoDDT"],
        ].to_dict("records")),
    )


def verifica_codici(df_xml_righe):
    titolo(8, "CODICI ARTICOLO E NORMALIZZAZIONE (celle [12]-[13])")

    print(mostra(df_xml_righe[[
        "CFOR", "NumeroFattura", "ChiaveArticoloXML", "EAN",
        "Codice Art. Fornitore", "Quantita",
    ]]))

    def chiavi(fattura):
        return set(
            df_xml_righe.loc[
                df_xml_righe["NumeroFattura"] == fattura,
                "ChiaveArticoloXML",
            ]
        )

    controlla(
        "F001/00001: chiavi EAN, codice fornitore e sconto",
        chiavi("00001") == {"EAN|8001111111111", "FORN|ART-002", "SCONTO|3"},
        str(chiavi("00001")),
    )
    controlla(
        "codice fornitore normalizzato in maiuscolo",
        "FORN|ART-002" in chiavi("00001"),
        str(chiavi("00001")),
    )
    controlla(
        "NESSUNA_REGOLA conserva i separatori",
        "FORN|F22-1" in chiavi("7"),
        str(chiavi("7")),
    )
    controlla(
        "riga senza codice sopravvive al pivot (natura SC)",
        "SCONTO|3" in chiavi("00001"),
        str(chiavi("00001")),
    )


def verifica_normalizzazione_carichi(df_fatture, df_merge, namespace):
    titolo(9, "NORMALIZZAZIONE DEI CODICI SUL LATO CARICHI (cella [10])")

    colonne = [
        "mersy_fornitore(CFOR)",
        "mersy_articolo_fornitore(CALA)",
        "CALA_Chiave",
        "mersy_articolo(CART)",
        "CART_Chiave",
        "mersy_ean(CEAN)",
        "CEAN_Chiave",
    ]
    print(mostra(df_fatture[colonne]))

    riga = df_fatture.loc[
        df_fatture["mersy_fornitore(CFOR)"] == "F003"
    ]

    controlla(
        "il carico conserva il codice originale",
        riga["mersy_articolo_fornitore(CALA)"].eq("ART/002").all(),
        str(riga["mersy_articolo_fornitore(CALA)"].tolist()),
    )
    controlla(
        "il carico porta la chiave normalizzata (ART/002 -> ART002)",
        riga["CALA_Chiave"].eq("ART002").all(),
        str(riga["CALA_Chiave"].tolist()),
    )
    controlla(
        "le chiavi dei codici esistono per tutti i livelli",
        all(
            colonna in df_fatture.columns
            for colonna in ("CEAN_Chiave", "CART_Chiave", "CALA_Chiave")
        ),
    )
    controlla(
        "il carico si abbina grazie alla normalizzazione",
        (df_merge.loc[df_merge["NumeroFattura"] == "00012", "StatoAbbinamento"]
         == "Abbinato").all(),
        str(df_merge.loc[df_merge["NumeroFattura"] == "00012",
                         ["TipoMatch", "StatoAbbinamento"]].to_dict("records")),
    )
    controlla(
        "l'abbinamento F003 avviene sul codice fornitore",
        (df_merge.loc[df_merge["NumeroFattura"] == "00012", "TipoMatch"]
         == "CALA").all(),
        str(df_merge.loc[df_merge["NumeroFattura"] == "00012",
                         "TipoMatch"].tolist()),
    )

    # refuso nel dizionario: non applicato ma segnalato
    non_riconosciuti = namespace.get("campi_non_riconosciuti", [])
    controlla(
        "CampoCanonico sconosciuto segnalato (CODICE_FORNTORE)",
        "CODICE_FORNTORE" in non_riconosciuti,
        str(non_riconosciuti),
    )
    controlla(
        "CampoCanonico sconosciuto non genera una regola applicata",
        df_fatture.loc[
            df_fatture["mersy_fornitore(CFOR)"] == "F003", "CALA_Chiave"
        ].eq("ART002").all(),
        "la regola SOLO_NUMERI sul refuso non deve toccare il codice",
    )


def verifica_dizionario(dizionari):
    titolo(10, "DIAGNOSTICA DEL DIZIONARIO (cella [5])")

    print("Anomalie:")
    print(dizionari["Anomalie"].to_string(index=False))
    print()
    print("Chiavi duplicate:")
    print(dizionari["ChiaviDuplicate"].to_string(index=False))

    controlla(
        "regola non riconosciuta segnalata senza bloccare",
        len(dizionari["Anomalie"]) == 1
        and "REGOLA_INVENTATA" in dizionari["Anomalie"]["Stato"].iloc[0],
        str(dizionari["Anomalie"].to_dict("records")),
    )
    controlla(
        "chiave duplicata segnalata",
        len(dizionari["ChiaviDuplicate"]) == 1,
        str(dizionari["ChiaviDuplicate"].to_dict("records")),
    )


def verifica_regole_allineate(namespace):
    titolo(11, "COERENZA DELLE REGOLE FRA I DUE LATI (cella [10])")

    tabella = namespace["regole_non_allineate"]

    print(tabella.to_string(index=False))

    coppie = set(zip(tabella["CFOR"], tabella["Campo"]))

    controlla(
        "regola presente solo sul lato XML segnalata (F009)",
        ("F009", "CODICE_FORNITORE") in coppie,
        str(tabella.to_dict("records")),
    )
    controlla(
        "il disallineamento mostra le due regole applicate",
        tabella.loc[
            (tabella["CFOR"] == "F009")
            & (tabella["Campo"] == "CODICE_FORNITORE"),
            ["RegolaXML", "RegolaCarico"],
        ].to_dict("records") == [{
            "RegolaXML": "NESSUNA_REGOLA",
            "RegolaCarico": "RIMUOVI_SEPARATORI (default)",
        }],
        str(tabella.to_dict("records")),
    )
    controlla(
        "regole allineate non segnalate",
        not {
            ("F001", "EAN"),
            ("F001", "CODICE_FORNITORE"),
            ("F001", "CODICE_CLIENTE"),
            ("F002", "CODICE_FORNITORE"),
            ("F003", "CODICE_FORNITORE"),
        } & coppie,
        str(sorted(coppie)),
    )
    controlla(
        "regola solo non riconosciuta: non e' un disallineamento",
        ("F002", "EAN") not in coppie,
        "REGOLA_INVENTATA ricade sul default, come l'assenza di regola",
    )
    controlla(
        "CampoCanonico sconosciuto escluso dal confronto",
        all(campo in {"EAN", "CODICE_CLIENTE", "CODICE_FORNITORE", "DDT"}
            for campo in tabella["Campo"]),
        str(sorted(set(tabella["Campo"]))),
    )


def verifica_perimetro(df_fatture):
    titolo(12, "PERIMETRO E ANAGRAFICHE (celle [8]-[9])")

    controlla(
        "filtro CDOCIAA: 60I e 60C nel perimetro",
        len(df_fatture) == 13,
        f"righe nel perimetro: {len(df_fatture)}",
    )
    controlla(
        "la nota di credito 60C entra nel perimetro",
        set(
            df_fatture.loc[
                df_fatture["mersy_tipo_documento(CDOCIAA)"] == "60C",
                "mersy_n_fattura(NDOGIAA)",
            ]
        ) == {"00020"},
        str(df_fatture.loc[
            df_fatture["mersy_tipo_documento(CDOCIAA)"] == "60C",
            "mersy_n_fattura(NDOGIAA)",
        ].tolist()),
    )
    controlla(
        "un tipo documento fuori elenco resta escluso",
        "99X" not in set(df_fatture["mersy_tipo_documento(CDOCIAA)"]),
        str(sorted(set(df_fatture["mersy_tipo_documento(CDOCIAA)"]))),
    )
    controlla(
        "CARF sostituisce CALA usando il TDEC più recente",
        set(
            df_fatture.loc[
                df_fatture["mersy_articolo(CART)"] == "C002",
                "mersy_articolo_fornitore(CALA)",
            ]
        ) == {"ART-002"},
        str(sorted(set(df_fatture["mersy_articolo_fornitore(CALA)"].dropna()))),
    )
    controlla(
        "punto di consegna agganciato",
        df_fatture["mersy_descrizione_punto_consegna(XPCO)"].notna().all(),
    )
    controlla(
        "riga fuori perimetro assente dal lato carichi",
        "FUORI PERIMETRO"
        not in set(df_fatture["mersy_descrizione_articolo(XART)"]),
    )


def verifica_descrizione_codice(df_xml_fatture, df_xml_codici_articolo,
                                df_xml_righe):
    titolo(13, "DESCRIZIONE COME CODICE E TIPI CODIFICATI (celle [3] e [12])")

    print(mostra(df_xml_codici_articolo[
        ["CFOR_XML", "CodiceTipoXML", "CodiceValoreXML",
         "CampoCanonico", "CodiceValoreNormalizzato"]
    ]))

    descrizioni = df_xml_codici_articolo.loc[
        df_xml_codici_articolo["CodiceTipoXML"] == "Descrizione"
    ]

    # dropna: sui dati rotti il CFOR può mancare e sorted() non
    # accetta i valori NA
    fornitori_descrizione = sorted(set(descrizioni["CFOR_XML"].dropna()))

    tipi_presenti = set(df_xml_codici_articolo["CodiceTipoXML"].dropna())

    valori_presenti = set(
        df_xml_codici_articolo["CodiceValoreNormalizzato"].dropna()
    )

    def tipi_della_linea(file_xml, numero_linea):
        """Tipi di codice rimasti sulle linee di quell'XML."""

        chiavi = set(
            df_xml_fatture.loc[
                (df_xml_fatture["FileXML"] == file_xml)
                & (df_xml_fatture["NumeroLinea"] == numero_linea),
                "ChiaveRigaXML",
            ]
        )

        return df_xml_codici_articolo.loc[
            df_xml_codici_articolo["ChiaveRigaXML"].isin(chiavi),
            "CodiceTipoXML",
        ].tolist()

    controlla(
        "la descrizione di F005 diventa un codice articolo",
        "ART222" in descrizioni.loc[
            descrizioni["CFOR_XML"] == "F005",
            "CodiceValoreNormalizzato",
        ].tolist(),
        mostra(descrizioni),
    )

    controlla(
        "la descrizione viene aggiunta a ogni linea, anche quando "
        "c'e' gia' un codice",
        tipi_della_linea("IT06666666666_00030.xml", 2)
        == ["FORN", "Descrizione"],
        str(tipi_della_linea("IT06666666666_00030.xml", 2)),
    )

    controlla(
        "la descrizione di F006 usa ESTRAI_PRIMA_STRINGA",
        descrizioni.loc[
            descrizioni["CFOR_XML"] == "F006",
            "CodiceValoreNormalizzato",
        ].tolist() == ["1234"],
        mostra(descrizioni),
    )

    controlla(
        "la descrizione vale solo per i fornitori che la codificano",
        fornitori_descrizione == ["F005", "F006"],
        str(fornitori_descrizione),
    )

    controlla(
        "la descrizione si usa anche con un codice non codificato "
        "sulla linea (MINSAN)",
        tipi_della_linea("IT07777777777_00040.xml", 1) == ["Descrizione"],
        str(tipi_della_linea("IT07777777777_00040.xml", 1)),
    )

    controllo_linea_con_codice = df_xml_righe.loc[
        df_xml_righe["NumeroFattura"] == "00030",
        "Codice Art. Fornitore",
    ].dropna().tolist()

    controlla(
        "un codice vero prevale sulla descrizione nello stesso campo",
        controllo_linea_con_codice[0] == "ART001",
        str(controllo_linea_con_codice),
    )

    controlla(
        "il progressivo della descrizione e' sempre l'ultimo",
        int(
            descrizioni["ProgressivoCodiceXML"].max()
        ) > int(
            df_xml_codici_articolo.loc[
                df_xml_codici_articolo["CodiceTipoXML"] != "Descrizione",
                "ProgressivoCodiceXML",
            ].max()
        ),
        str(sorted(descrizioni["ProgressivoCodiceXML"].tolist())),
    )

    chiave_f006 = df_xml_righe.loc[
        df_xml_righe["NumeroFattura"] == "00040", "ChiaveArticoloXML"
    ].tolist()

    controlla(
        "F006 si abbina al carico tramite il codice preso dalla "
        "descrizione",
        chiave_f006 == ["CART|1234"],
        str(chiave_f006),
    )

    controlla(
        "tipo non codificato escluso dalla tabella dei codici",
        "XYZ" not in tipi_presenti and "MINSAN" not in tipi_presenti,
        str(sorted(tipi_presenti)),
    )

    controlla(
        "ogni codice rimasto ha un campo canonico",
        df_xml_codici_articolo["CampoCanonico"].notna().all(),
        str(int(df_xml_codici_articolo["CampoCanonico"].isna().sum())),
    )

    controlla(
        "il valore del tipo escluso non compare nei codici",
        "SCONTO-9" not in valori_presenti,
    )


def verifica_export(cartella_output, df_powerbi, namespace):
    titolo(14, "EXPORT E TIPI DELLE CELLE (celle [16]-[17])")

    for nome in ("riconciliazione.xlsx", "riconciliazione_powerbi.xlsx"):
        controlla(
            f"{nome} creato",
            (Path(cartella_output) / nome).exists(),
            str(Path(cartella_output) / nome),
        )

    percorso = Path(cartella_output) / "riconciliazione_powerbi.xlsx"

    if not percorso.exists():
        return

    foglio = openpyxl.load_workbook(percorso)["df_merge"]
    intestazioni = [cella.value for cella in foglio[1]]

    tipi = {}
    for riga in foglio.iter_rows(min_row=2, max_row=foglio.max_row):
        for nome_colonna, cella in zip(intestazioni, riga):
            if cella.value is not None:
                tipi.setdefault(nome_colonna, set()).add(cella.data_type)

    for colonna in ("Data fattura", "Data bolla"):
        controlla(
            f"xlsx: {colonna} = data",
            tipi.get(colonna, set()) <= {"d"},
            str(tipi.get(colonna)),
        )

    for colonna in intestazioni:
        if colonna.startswith(("Quantità", "Prezzo", "Totale", "Differenza")):
            controlla(
                f"xlsx: {colonna} = numero",
                tipi.get(colonna, set()) <= {"n"},
                str(tipi.get(colonna)),
            )

    for colonna in (
        "Fattura", "CEAS", "CFOR", "Denominazione", "Bolla",
        "CPCO descrizione", "Codice EAN", "Codice articolo interno",
        "Codice articolo fornitore", "Numero riga fattura",
        "Stato abbinamento", "Stato DDT", "Tipologia documento",
    ):
        controlla(
            f"xlsx: {colonna} = testo",
            tipi.get(colonna, set()) <= {"s"},
            str(tipi.get(colonna)),
        )

    controlla(
        "il report ha 26 colonne",
        len(intestazioni) == 26,
        f"trovate {len(intestazioni)}",
    )

    controlla(
        "CPCO e' numerico",
        tipi.get("CPCO", set()) <= {"n"},
        str(tipi.get("CPCO")),
    )

    controlla(
        "ordine delle colonne come da specifica",
        intestazioni[:7] == [
            "Fattura", "Data fattura", "Tipologia documento", "CEAS", "CFOR",
            "Denominazione", "Bolla",
        ],
        str(intestazioni[:7]),
    )

    controlla(
        "Stato DDT subito dopo Data bolla",
        intestazioni[7:10] == ["Data bolla", "Stato DDT", "CPCO"],
        str(intestazioni[7:10]),
    )

    # la colonna CFOR deve coincidere con il codice fornitore usato
    # nel resto del processo, non essere un doppione vuoto
    if "CFOR" in intestazioni:
        posizione = intestazioni.index("CFOR")
        valori_cfor = [
            riga[posizione].value
            for riga in foglio.iter_rows(min_row=2, max_row=foglio.max_row)
        ]
        controlla(
            "CFOR valorizzato sulle righe con fornitore noto",
            sum(1 for v in valori_cfor if v not in (None, "")) >= 8,
            str(valori_cfor),
        )

    dataset = df_powerbi

    controlla(
        "etichetta fornitore nella forma '(CFOR) Nome'",
        dataset.loc[dataset["CFOR"].eq("F001"), "Denominazione"]
        .eq("(F001) FORNITORE 00001 SRL").any(),
        str(sorted(set(dataset["Denominazione"].dropna()))),
    )
    controlla(
        "Numero riga fattura vuoto sulle righe Solo carico",
        dataset.loc[
            dataset["Stato abbinamento"].eq("Solo carico"), "Numero riga fattura"
        ].isna().all(),
        str(dataset.loc[dataset["Stato abbinamento"].eq("Solo carico"),
                        "Numero riga fattura"].tolist()),
    )
    controlla(
        "CEAS popolato solo sulle righe con carico",
        dataset.loc[dataset["Stato abbinamento"].ne("Solo XML"), "CEAS"]
        .notna().all()
        and dataset.loc[dataset["Stato abbinamento"].eq("Solo XML"), "CEAS"]
        .isna().all(),
        str(dataset[["Stato abbinamento", "CEAS"]].to_dict("records")),
    )
    # differenza quantità sui valori assoluti: una nota di credito ha
    # quantità negative e sottrarre i valori con segno darebbe 12
    # invece di 0 (caso 00020: XML +3, carico -3)
    nota = dataset.loc[dataset["Fattura"].eq("00020")]
    riga_merce = nota.loc[nota["Stato abbinamento"].eq("Abbinato")]

    controlla(
        "Differenza quantità sui valori assoluti (3 contro -3 = 0)",
        len(riga_merce) == 1
        and riga_merce["Differenza quantità"].iloc[0] == 0,
        str(riga_merce[[
            "Quantità XML", "Quantità carico", "Differenza quantità",
        ]].to_dict("records")),
    )
    controlla(
        "le quantità mantengono il segno originale",
        len(riga_merce) == 1
        and riga_merce["Quantità XML"].iloc[0] == 3
        and riga_merce["Quantità carico"].iloc[0] == -3,
        str(riga_merce[["Quantità XML", "Quantità carico"]].to_dict("records")),
    )

    def differenza_attesa(colonna_xml, colonna_carico, assoluta):
        sinistra = dataset[colonna_xml]
        destra = dataset[colonna_carico]
        if assoluta:
            sinistra = sinistra.abs()
            destra = destra.abs()
        return sinistra - destra

    controlla(
        "Differenza quantità = |XML| - |carico| su tutte le righe",
        dataset["Differenza quantità"].equals(
            differenza_attesa("Quantità XML", "Quantità carico", True)
        ),
        str(dataset[["Quantità XML", "Quantità carico",
                     "Differenza quantità"]].to_dict("records")),
    )
    controlla(
        "Differenza totali resta con il segno (sottrazione semplice)",
        dataset["Differenza totali"].equals(
            differenza_attesa("Totale XML", "Totale Mersy", False)
        ),
        str(dataset[["Totale XML", "Totale Mersy",
                     "Differenza totali"]].to_dict("records")),
    )

    controlla(
        "CPCO valorizzato solo sulle righe con carico",
        dataset.loc[dataset["Stato abbinamento"].ne("Solo XML"), "CPCO"]
        .notna().all()
        and dataset.loc[dataset["Stato abbinamento"].eq("Solo XML"), "CPCO"]
        .isna().all(),
        str(dataset[["Stato abbinamento", "CPCO"]].to_dict("records")),
    )

    # cella [18]: scrittura della tabella Delta quadratura_powerbi
    spark_finto = namespace["spark"]
    controlla(
        "tabella Delta quadratura_powerbi scritta",
        spark_finto.tabelle_scritte == ["quadratura_powerbi"],
        str(spark_finto.tabelle_scritte),
    )
    controlla(
        "colonne Delta normalizzate rispetto al report",
        len(spark_finto.dataframe_creati) == 1
        and list(spark_finto.dataframe_creati[0].columns) == [
            str(c).strip().replace(" ", "_") for c in dataset.columns
        ],
        str(list(spark_finto.dataframe_creati[0].columns)) if spark_finto.dataframe_creati else "nessun DataFrame",
    )
    controlla(
        "scrittura Delta in overwrite con aggiornamento schema",
        len(spark_finto.scritture) == 1
        and spark_finto.scritture[0]["formato"] == "delta"
        and spark_finto.scritture[0]["modalita"] == "overwrite"
        and spark_finto.scritture[0]["opzioni"].get("overwriteSchema") == "true",
        str(spark_finto.scritture),
    )
    controlla(
        "scrittura Delta conserva righe e valori del report",
        len(spark_finto.dataframe_creati) == 1
        and spark_finto.dataframe_creati[0].set_axis(dataset.columns, axis=1).equals(dataset),
    )

    print()
    print("Dataset del report:")
    print(mostra(df_powerbi[[
        "Fattura", "CEAS", "CFOR", "Denominazione", "Bolla",
        "CPCO", "CPCO descrizione", "Codice EAN",
        "Quantità XML", "Quantità carico", "Numero riga fattura",
        "Stato abbinamento",
    ]]))


def stampa_riepilogo():
    titolo(15, "RIEPILOGO")

    for nome, esito, dettaglio in ESITI:
        riga = ("PASS  " if esito else "FAIL  ") + nome
        if not esito and dettaglio:
            riga += f"   [{dettaglio}]"
        print(riga)

    falliti = [esito for esito in ESITI if not esito[1]]

    print()
    print(f"{len(ESITI) - len(falliti)}/{len(ESITI)} controlli superati")

    return 0 if not falliti else 1


def main():
    namespace = harness.esegui_notebook()
    # La cella [18] normalizza i nomi in df_powerbi dopo l'export Excel.
    # Ripristiniamo le intestazioni del report solo per i controlli esistenti.
    df_report = namespace["df_powerbi"].rename(
        columns=lambda colonna: colonna.replace("_", " ")
    )

    verifica_data_ddt(namespace["df_xml_fatture"])
    verifica_denominazione(
        namespace["df_xml_fatture"],
        namespace["df_xml_righe"],
        namespace["df_merge"],
    )
    verifica_map_ddt(namespace["map_ddt"])
    verifica_merge(namespace["df_merge"])
    verifica_ddt_derivato(namespace["df_merge"])
    verifica_tipologia(namespace["df_merge"], df_report)
    verifica_stato_ddt(namespace["df_merge"])
    verifica_codici(namespace["df_xml_righe"])
    verifica_normalizzazione_carichi(
        namespace["df_fatture"],
        namespace["df_merge"],
        namespace,
    )
    verifica_dizionario(namespace["dizionari"])
    verifica_regole_allineate(namespace)
    verifica_perimetro(namespace["df_fatture"])
    verifica_descrizione_codice(
        namespace["df_xml_fatture"],
        namespace["df_xml_codici_articolo"],
        namespace["df_xml_righe"],
    )
    verifica_export(
        namespace["_cartella_output"],
        df_report,
        namespace,
    )

    return stampa_riepilogo()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
