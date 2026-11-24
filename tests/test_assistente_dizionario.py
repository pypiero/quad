"""
Test di Assistente_Dizionario_Codici.ipynb su dati sintetici.

Esegue le celle del notebook così come sono, sostituendo solo
notebookutils.fs, pd.read_excel e pd.ExcelWriter (come tests/harness.py).
Non richiede OneLake né Fabric.

Uso, dalla radice del repository:

    python tests/test_assistente_dizionario.py
"""

import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

import openpyxl
import pandas as pd

import dati_sintetici

RADICE = Path(__file__).resolve().parents[1]
NOTEBOOK = RADICE / "Assistente_Dizionario_Codici.ipynb"


class _FsFinto:
    def exists(self, percorso):
        return True

    def rm(self, percorso):
        return True

    def cp(self, sorgente, destinazione):
        return True

    def mkdirs(self, percorso):
        return True


class _NotebookutilsFinto:
    def __init__(self):
        self.fs = _FsFinto()


def _gtin_valido(prime_12_cifre):
    """Aggiunge la cifra di controllo GS1 (EAN13)."""
    cifre = [int(c) for c in prime_12_cifre]
    totale = sum(
        c * (3 if i % 2 == 0 else 1)
        for i, c in enumerate(reversed(cifre))
    )
    return prime_12_cifre + str((10 - totale % 10) % 10)


def _xml_aggiuntivi():
    """
    XML extra (in una sottocartella dello ZIP, così il nome file
    senza estensione resta il CEAS atteso dai carichi).

    - un tipo dal nome sconosciuto ma riscontrabile in CART (F001);
    - un tipo BARCODE con GTIN validi (F002);
    - il tipo virtuale RiferimentoAmministrazione;
    - due fornitori senza carichi: uno non mappato, uno mappato
      a mano con MAPPA_PIVA_CFOR.
    """
    gtin_a = _gtin_valido("800150030280")
    gtin_b = _gtin_valido("800150030281")

    return {
        "nuovi/IT01111111111_00001.xml": dati_sintetici.xml_documento(
            "00001", "2025-01-10", "",
            "".join([
                dati_sintetici.linea(
                    1, "ARTICOLO NUOVO", 1, 1, 1,
                    codici=[("CODICE_27", "C001")],
                ),
                dati_sintetici.linea(
                    2, "ARTICOLO NUOVO 2", 1, 1, 1,
                    codici=[("CODICE_27", "C002")],
                ),
            ]),
        ),
        "nuovi/IT02222222222_00007.xml": dati_sintetici.xml_documento(
            "7", "2025-02-10", "",
            "".join([
                dati_sintetici.linea(
                    1, "BARCODE A", 1, 1, 1,
                    codici=[("BARCODE", gtin_a)],
                ),
                dati_sintetici.linea(
                    2, "BARCODE B", 1, 1, 1,
                    codici=[("BARCODE", gtin_b)],
                ),
            ]),
        ),
        "nuovi/IT01111111111_00002.xml": dati_sintetici.xml_documento(
            "00002", "2025-03-10", "",
            (
                "<DettaglioLinee><NumeroLinea>1</NumeroLinea>"
                "<Descrizione>VOCE</Descrizione>"
                "<RiferimentoAmministrazione>C001"
                "</RiferimentoAmministrazione></DettaglioLinee>"
            ),
        ),
        "nuovi/IT09999999999_00050.xml": dati_sintetici.xml_documento(
            "50", "2025-04-10", "",
            dati_sintetici.linea(
                1, "PRODOTTO", 1, 1, 1,
                codici=[("FORN", "ART-999")],
            ),
        ),
        "nuovi/IT08888888888_00060.xml": dati_sintetici.xml_documento(
            "60", "2025-05-10", "",
            dati_sintetici.linea(
                1, "PRODOTTO MAPPATO", 1, 1, 1,
                codici=[("FORN", "ART-777")],
            ),
        ),
    }


def _leggi_excel_finta(percorso, sheet_name=None, **kwargs):
    nome = Path(str(percorso)).name

    if "Dizionario" in nome:
        return {
            foglio: tabella.copy()
            for foglio, tabella in dati_sintetici.DIZIONARIO.items()
        }
    if "TAB_CM_Fatture_BI" in nome:
        return dati_sintetici.CARICHI.copy()
    if "ANAGRAFICA_EAN" in nome:
        return dati_sintetici.EAN.copy()
    if "ANAGRAFICA_CARF" in nome:
        return dati_sintetici.CARF.copy()

    raise AssertionError(
        f"Lettura Excel non prevista dal test: {percorso}"
    )


def _esegui_notebook():
    with open(NOTEBOOK, encoding="utf-8") as file:
        notebook = json.load(file)

    celle = [
        "".join(cella["source"])
        for cella in notebook["cells"]
        if cella.get("cell_type") == "code"
        and "".join(cella["source"]).strip()
    ]

    trovato = re.search(
        r'zip_locale_python\s*=\s*"([^"]+)"',
        "\n".join(celle),
    )
    if trovato is None:
        raise RuntimeError("zip_locale_python non trovato nel notebook")

    percorso_zip = Path(trovato.group(1))
    percorso_zip.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(percorso_zip, "w") as archivio:
        for nome, contenuto in {
            **dati_sintetici.XML_FILES,
            **_xml_aggiuntivi(),
        }.items():
            archivio.writestr(nome, contenuto)

    cartella_output = Path(tempfile.mkdtemp(prefix="quad_assistente_"))
    scritture = []

    lettura_originale = pd.read_excel
    scrittore_originale = pd.ExcelWriter

    def scrittore_redirect(percorso, **kwargs):
        scritture.append(str(percorso))
        destinazione = cartella_output / Path(str(percorso)).name
        return scrittore_originale(destinazione, **kwargs)

    pd.read_excel = _leggi_excel_finta
    pd.ExcelWriter = scrittore_redirect

    namespace = {
        "pd": pd,
        "notebookutils": _NotebookutilsFinto(),
        "display": lambda *argomenti, **kwargs: None,
        "__name__": "__main__",
    }

    try:
        for indice, codice in enumerate(celle, start=1):
            exec(
                compile(codice, f"cella_{indice}", "exec"),
                namespace,
            )
            # Come per i flag del notebook principale, si inietta
            # una configurazione subito dopo la cella [1].
            if indice == 1:
                namespace["MAPPA_PIVA_CFOR"] = {
                    "IT08888888888": "F088",
                }
    finally:
        pd.read_excel = lettura_originale
        pd.ExcelWriter = scrittore_originale

    return namespace, cartella_output, scritture


class TestAssistenteDizionario(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ns, cls.cartella, cls.scritture = _esegui_notebook()

    def _riga_tipo(self, cfor, tipo_chiave):
        df = self.ns["df_tipi"]
        righe = df.loc[
            (df["CFOR"] == cfor)
            & (df["TipoChiave"] == tipo_chiave)
        ]
        self.assertEqual(
            len(righe), 1,
            f"attesa una riga per ({cfor}, {tipo_chiave}), "
            f"trovate {len(righe)}",
        )
        return righe.iloc[0]

    def test_1_lettura_xml(self):
        df_codici = self.ns["df_codici"]
        df_documenti = self.ns["df_documenti"]

        self.assertFalse(df_codici.empty)
        self.assertFalse(df_documenti.empty)
        self.assertEqual(
            set(self.ns["df_errori"].columns),
            {"File", "Errore"},
        )
        self.assertTrue(self.ns["df_errori"].empty)

        tipi = set(df_codici["TipoChiave"])
        for atteso in (
            "EAN", "FORN", "CLI", "COD_F", "MINSAN", "XYZ",
            "BARCODE", "CODICE_27", "RIFERIMENTOAMMINISTRAZIONE",
        ):
            self.assertIn(atteso, tipi, f"tipo {atteso} non letto")

        # Solo FPR12: il file FPA11 deve essere stato scartato.
        self.assertNotIn(
            "IT04444444444_00011.xml",
            set(df_documenti["FileXML"]),
        )

        virtuali = df_codici.loc[
            df_codici["Origine"] == "VIRTUALE"
        ]
        self.assertFalse(virtuali.empty)
        self.assertTrue(
            (virtuali["CodiceTipoXML"] == "RiferimentoAmministrazione")
            .all()
        )

    def test_2_tipi_noti_e_non_articolo(self):
        attesi = {
            ("F001", "EAN"): "EAN",
            ("F001", "FORN"): "CODICE_FORNITORE",
            ("F001", "CLI"): "CODICE_CLIENTE",
            ("F002", "COD_F"): "CODICE_FORNITORE",
        }
        for (cfor, tipo), campo in attesi.items():
            riga = self._riga_tipo(cfor, tipo)
            self.assertEqual(
                riga["CampoCanonico"], campo,
                f"{cfor}/{tipo}: campo errato. {riga['Motivazione']}",
            )
            self.assertEqual(riga["Confidenza"], "ALTA")
            self.assertEqual(riga["Azione"], "GIA_PRESENTE")

        for cfor, tipo in (("F006", "MINSAN"), ("F005", "XYZ")):
            riga = self._riga_tipo(cfor, tipo)
            self.assertEqual(riga["CampoCanonico"], "")
            self.assertEqual(riga["Confidenza"], "NESSUNA")
            self.assertEqual(riga["Azione"], "DA_VERIFICARE")

        da_verificare = self.ns["df_da_verificare"]
        self.assertIn(
            "MINSAN", set(da_verificare["CodiceTipoXML"])
        )
        self.assertIn(
            "ministeriale",
            " ".join(
                da_verificare.loc[
                    da_verificare["CodiceTipoXML"] == "MINSAN",
                    "Motivazione",
                ]
            ).lower(),
        )

    def test_3_tipo_nuovo_riconosciuto_dal_riscontro(self):
        # Nome mai visto, ma entrambi i valori esistono in CART:
        # il riscontro in anagrafica deve bastare (confidenza MEDIA).
        riga = self._riga_tipo("F001", "CODICE_27")
        self.assertEqual(
            riga["CampoCanonico"], "CODICE_CLIENTE",
            riga["Motivazione"],
        )
        self.assertEqual(riga["Confidenza"], "MEDIA")
        self.assertEqual(riga["RiscCODICE_CLIENTE"], 2)
        self.assertEqual(riga["Azione"], "AGGIUNGI")

    def test_4_forma_gtin(self):
        riga = self._riga_tipo("F002", "BARCODE")
        self.assertEqual(riga["CampoCanonico"], "EAN")
        self.assertEqual(riga["Confidenza"], "ALTA")
        self.assertEqual(riga["QuotaEANValida"], 1.0)
        self.assertEqual(riga["Azione"], "AGGIUNGI")

    def test_5_tipo_virtuale_non_classificato(self):
        riga = self._riga_tipo(
            "F001", "RIFERIMENTOAMMINISTRAZIONE"
        )
        self.assertEqual(riga["Origine"], "VIRTUALE")
        self.assertEqual(riga["CampoCanonico"], "")

        da_verificare = self.ns["df_da_verificare"]
        righe = da_verificare.loc[
            da_verificare["CodiceTipoXML"]
            == "RiferimentoAmministrazione"
        ]
        self.assertEqual(len(righe), 1)
        self.assertEqual(
            righe.iloc[0]["Azione"], "DA_VERIFICARE"
        )

    def test_6_cfor_mancante_e_mappa_manuale(self):
        fornitori = self.ns["df_fornitori_da_mappare"]
        self.assertIn(
            "IT09999999999", set(fornitori["PartitaIVA"])
        )
        self.assertNotIn(
            "IT08888888888", set(fornitori["PartitaIVA"])
        )

        da_verificare = self.ns["df_da_verificare"]
        mancanti = da_verificare.loc[
            da_verificare["Azione"] == "CFOR_MANCANTE"
        ]
        self.assertFalse(mancanti.empty)
        self.assertTrue((mancanti["CFOR"] == "").all())
        # Il campo era stato dedotto, ma senza CFOR non si propone.
        self.assertEqual(
            mancanti.iloc[0]["CampoCanonico"],
            "CODICE_FORNITORE",
        )

        # Il fornitore mappato a mano produce una proposta vera.
        proposte = self.ns["df_proposte_xml"]
        f088 = proposte.loc[proposte["CFOR"] == "F088"]
        self.assertEqual(len(f088), 1)
        self.assertEqual(
            f088.iloc[0]["Azione"], "AGGIUNGI"
        )
        self.assertEqual(
            f088.iloc[0]["CampoCanonico"],
            "CODICE_FORNITORE",
        )

    def test_7_schema_proposte(self):
        proposte = self.ns["df_proposte_xml"]
        self.assertFalse(proposte.empty)
        self.assertEqual(
            list(proposte.columns[:5]),
            [
                "CFOR", "Denominazione", "CodiceTipoXML",
                "CampoCanonico", "RegolaNormalizzazione",
            ],
        )
        self.assertTrue((proposte["CFOR"] != "").all())
        self.assertTrue(
            proposte["CampoCanonico"]
            .isin(["EAN", "CODICE_CLIENTE", "CODICE_FORNITORE"])
            .all()
        )
        self.assertTrue(
            proposte["RegolaNormalizzazione"]
            .isin(self.ns["REGOLE_NOTE"])
            .all()
        )

        carico = self.ns["df_proposte_carico"]
        self.assertEqual(
            list(carico.columns[:4]),
            [
                "CFOR", "Denominazione", "CampoCanonico",
                "RegolaNormalizzazione",
            ],
        )
        nuove = carico.loc[carico["Azione"] == "AGGIUNGI"]
        coppie = set(zip(nuove["CFOR"], nuove["CampoCanonico"]))
        self.assertIn(("F002", "EAN"), coppie)
        self.assertIn(("F088", "CODICE_FORNITORE"), coppie)

    def test_8_regole_inutilizzate_e_anomalie(self):
        inutilizzate = self.ns["df_regole_inutilizzate"]
        self.assertIn(
            "DESCRIZIONE",
            set(inutilizzate["CodiceTipoXML"]),
        )

        anomalie = self.ns["df_anomalie"]
        valori = set(anomalie["Valore"])
        self.assertIn("CODICE_FORNTORE", valori)
        self.assertIn("REGOLA_INVENTATA", valori)
        self.assertIn(
            "chiave duplicata",
            " ".join(anomalie["Problema"]),
        )

    def test_9_export_e_dizionario_intatto(self):
        self.assertTrue(self.scritture)
        for percorso in self.scritture:
            self.assertEqual(
                Path(percorso).name,
                "proposte_dizionario_codici.xlsx",
                "l'assistente ha scritto un file non previsto",
            )

        file_excel = (
            self.cartella / "proposte_dizionario_codici.xlsx"
        )
        self.assertTrue(file_excel.exists())

        cartella_excel = openpyxl.load_workbook(file_excel)
        try:
            fogli = set(cartella_excel.sheetnames)
        finally:
            cartella_excel.close()

        for atteso in (
            "ProposteXML", "ProposteCarico", "DaVerificare",
            "DettaglioTipi", "FornitoriDaMappare",
            "RegoleInutilizzate", "AnomalieDizionario",
            "Riepilogo",
        ):
            self.assertIn(atteso, fogli)

        # Le righe del dizionario sintetico non sono state modificate.
        self.assertEqual(
            len(dati_sintetici.DIZIONARIO["RegoleCodiciXML"]),
            10,
        )
        self.assertEqual(
            len(dati_sintetici.DIZIONARIO["RegoleCodiciCarico"]),
            9,
        )

    def test_10_riepilogo(self):
        df = self.ns["df_riepilogo"]
        self.assertEqual(
            list(df.columns), ["Indicatore", "Valore"]
        )
        indicatori = dict(zip(df["Indicatore"], df["Valore"]))
        self.assertGreater(
            indicatori["Codici articolo letti"], 0
        )
        self.assertGreater(
            indicatori[
                "Tipi osservati (CFOR + CodiceTipoXML)"
            ],
            0,
        )
        self.assertGreater(
            indicatori[
                "Righe AGGIUNGI proposte per RegoleCodiciXML"
            ],
            0,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
