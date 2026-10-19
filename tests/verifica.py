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
              "FORNITORE 00003 SRL"},
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
        len(solo_carico) == 2
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
        "merge senza duplicati (9 righe)",
        len(df_merge) == 9,
        str(len(df_merge)),
    )
    controlla(
        "ogni riga XML compare una volta sola",
        int(df_merge["ID_Riga_XML"].notna().sum()) == 7
        and df_merge["ID_Riga_XML"].dropna().is_unique,
        str(int(df_merge["ID_Riga_XML"].notna().sum())),
    )
    controlla(
        "ogni riga carico compare una volta sola",
        int(df_merge["Indice"].notna().sum()) == 6
        and df_merge["Indice"].dropna().is_unique,
        str(int(df_merge["Indice"].notna().sum())),
    )


def verifica_codici(df_xml_righe):
    titolo(5, "CODICI ARTICOLO E NORMALIZZAZIONE (celle [12]-[13])")

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


def verifica_dizionario(dizionari):
    titolo(6, "DIAGNOSTICA DEL DIZIONARIO (cella [5])")

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


def verifica_perimetro(df_fatture):
    titolo(7, "PERIMETRO E ANAGRAFICHE (celle [8]-[9])")

    controlla(
        "filtro CDOCIAA = 60I applicato",
        len(df_fatture) == 6,
        f"righe nel perimetro: {len(df_fatture)}",
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


def verifica_export(cartella_output, df_powerbi):
    titolo(8, "EXPORT E TIPI DELLE CELLE (celle [16])")

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
        "Fattura", "Bolla", "Codice EAN", "Codice articolo interno",
        "Codice articolo fornitore", "Numero riga fattura",
        "Denominazione", "Stato abbinamento",
    ):
        controlla(
            f"xlsx: {colonna} = testo",
            tipi.get(colonna, set()) <= {"s"},
            str(tipi.get(colonna)),
        )

    controlla(
        "il report ha 20 colonne",
        len(intestazioni) == 20,
        f"trovate {len(intestazioni)}",
    )

    print()
    print("Dataset del report:")
    print(mostra(df_powerbi[[
        "Fattura", "Data fattura", "Bolla", "Data bolla", "Codice EAN",
        "Quantità XML", "Quantità carico", "Denominazione",
        "Stato abbinamento",
    ]]))


def stampa_riepilogo():
    titolo(9, "RIEPILOGO")

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

    verifica_data_ddt(namespace["df_xml_fatture"])
    verifica_denominazione(
        namespace["df_xml_fatture"],
        namespace["df_xml_righe"],
        namespace["df_merge"],
    )
    verifica_map_ddt(namespace["map_ddt"])
    verifica_merge(namespace["df_merge"])
    verifica_codici(namespace["df_xml_righe"])
    verifica_dizionario(namespace["dizionari"])
    verifica_perimetro(namespace["df_fatture"])
    verifica_export(namespace["_cartella_output"], namespace["df_powerbi"])

    return stampa_riepilogo()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
