"""
Test di Assistente_Dizionario_Codici.ipynb su dati sintetici.

Esegue le celle del notebook così come sono, sostituendo solo
notebookutils.fs, pd.read_excel e pd.ExcelWriter. Non richiede
OneLake né Fabric.

Uso, dalla radice del repository:

    python tests/test_assistente_dizionario.py
"""

import json
import re
import tempfile
import unicodedata
import unittest
import zipfile
from pathlib import Path

import openpyxl
import pandas as pd

import dati_sintetici

RADICE = Path(__file__).resolve().parents[1]
NOTEBOOK = RADICE / "Assistente_Dizionario_Codici.ipynb"
PRINCIPALE = RADICE / "Quadratura_Fatture.ipynb"


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


def _xml_aggiuntivi():
    """
    Pochi XML in più (in una sottocartella, così il nome file senza
    estensione resta il CEAS atteso dai carichi):

    - GTIN e CODICE_27: nomi di tipo mai visti, ma valori presenti
      rispettivamente in CEAN e in CART (il banco di prova non ha
      alias, deve trovarli normalizzando e basta);
    - un RiferimentoAmministrazione (tipo virtuale);
    - un DDT "A/001" su una fattura il cui carico ha "DIVERSO/77":
      se il confronto non fosse per fattura, "A/001" incrocerebbe
      invece la bolla "A-001" di un'altra fattura;
    - un file non FPR12 con un codice, che deve essere scartato.
    """
    riga_riferimento = (
        "<DettaglioLinee><NumeroLinea>4</NumeroLinea>"
        "<Descrizione>VOCE</Descrizione>"
        "<RiferimentoAmministrazione>C001"
        "</RiferimentoAmministrazione></DettaglioLinee>"
    )

    return {
        "nuovi/IT01111111111_00001.xml": dati_sintetici.xml_documento(
            "00001", "2025-01-10",
            dati_sintetici.ddt("A/001", "2025-01-05", [1, 2, 3, 4]),
            "".join([
                dati_sintetici.linea(
                    1, "GTIN", 1, 1, 1,
                    codici=[("GTIN", "8001111111111")],
                ),
                dati_sintetici.linea(
                    2, "CODICE 27 A", 1, 1, 1,
                    codici=[("CODICE_27", "C001")],
                ),
                dati_sintetici.linea(
                    3, "CODICE 27 B", 1, 1, 1,
                    codici=[("CODICE_27", "C002")],
                ),
                riga_riferimento,
            ]),
        ),
        "nuovi/IT01111111111_00002.xml": dati_sintetici.xml_documento(
            "00002", "2025-02-10",
            dati_sintetici.ddt("A/001", "2025-02-05", [1]),
            dati_sintetici.linea(1, "VOCE", 1, 1, 1),
        ),
        "nuovi/IT04444444444_00011.xml": dati_sintetici.xml_documento(
            "11", "2025-03-10", "",
            dati_sintetici.linea(
                1, "NON FPR12", 1, 1, 1,
                codici=[("NON_FPR12", "XYZ1")],
            ),
        ).replace('versione="FPR12"', 'versione="FPA11"'),
    }


def _leggi_excel_finta(percorso, sheet_name=None, **kwargs):
    nome = Path(str(percorso)).name

    if "Dizionario" in nome:
        raise AssertionError(
            "L'assistente semplificato non deve leggere il dizionario"
        )
    if "TAB_CM_Fatture_BI" in nome:
        return dati_sintetici.CARICHI.copy()
    if "ANAGRAFICA_EAN" in nome:
        return dati_sintetici.EAN.copy()
    if "ANAGRAFICA_CARF" in nome:
        return dati_sintetici.CARF.copy()

    raise AssertionError(
        f"Lettura Excel non prevista dal test: {percorso}"
    )


def _celle_notebook(percorso):
    with open(percorso, encoding="utf-8") as file:
        notebook = json.load(file)
    return [
        "".join(cella["source"])
        for cella in notebook["cells"]
        if cella.get("cell_type") == "code"
        and "".join(cella["source"]).strip()
    ]


def _esegui_notebook():
    celle = _celle_notebook(NOTEBOOK)

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

    cartella_output = Path(tempfile.mkdtemp(prefix="quad_prove_"))
    scritture = []
    letture = []

    lettura_originale = pd.read_excel
    scrittore_originale = pd.ExcelWriter

    def lettura_finta(percorso, **kwargs):
        letture.append(str(percorso))
        return _leggi_excel_finta(percorso, **kwargs)

    def scrittore_redirect(percorso, **kwargs):
        scritture.append(str(percorso))
        destinazione = cartella_output / Path(str(percorso)).name
        return scrittore_originale(destinazione, **kwargs)

    pd.read_excel = lettura_finta
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
    finally:
        pd.read_excel = lettura_originale
        pd.ExcelWriter = scrittore_originale

    return namespace, cartella_output, scritture, letture


class TestAssistenteDizionario(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        (
            cls.ns,
            cls.cartella,
            cls.scritture,
            cls.letture,
        ) = _esegui_notebook()

    def test_1_regole_identiche_al_notebook_principale(self):
        """Il banco di prova normalizza come la quadratura."""
        celle = _celle_notebook(PRINCIPALE)
        codice_regole = next(
            c for c in celle
            if "REGOLE = {" in c and "def normalizza(" in c
        )
        ns_principale = {
            "pd": pd,
            "unicodedata": unicodedata,
            "DEBUG": False,
            "display": lambda *a, **k: None,
        }
        exec(
            compile(codice_regole, "regole_principali", "exec"),
            ns_principale,
        )

        self.assertEqual(
            set(self.ns["REGOLE_NOMI"]),
            set(ns_principale["REGOLE"]),
        )

        valori = [
            "ART-002", "art-002", "8001111111111", "00123",
            "A/001", "C001", "", "  x  ", "ÀRT", "ART/002",
            "123.45", "0", None, 12.0, "A 001", "F22-1",
            "SCONTO-9", "030999888",
        ]
        for regola in self.ns["REGOLE_NOMI"]:
            for valore in valori:
                self.assertEqual(
                    self.ns["normalizza"](valore, regola),
                    ns_principale["normalizza"](valore, regola),
                    f"valore={valore!r}, regola={regola}",
                )

    def test_2_codici_univoci_senza_fatture(self):
        df = self.ns["df_codici_univoci"]
        self.assertEqual(
            list(df.columns),
            ["CodiceTipoXML", "CodiceValoreXML", "ValorePulito"],
        )
        self.assertTrue(self.ns["df_errori"].empty)

        # Lo stesso EAN compare in quattro fatture diverse: una riga sola.
        ean = df.loc[
            (df["CodiceTipoXML"] == "EAN")
            & (df["ValorePulito"] == "8001111111111")
        ]
        self.assertEqual(len(ean), 1)

        tipi = set(df["CodiceTipoXML"])
        for atteso in (
            "EAN", "FORN", "CLI", "COD_F", "MINSAN", "XYZ",
            "GTIN", "CODICE_27", "RiferimentoAmministrazione",
        ):
            self.assertIn(atteso, tipi)
        self.assertNotIn("NON_FPR12", tipi)

    def test_3_griglia_tutte_le_combinazioni(self):
        df = self.ns["df_griglia_codici"]
        n_tipi = self.ns["df_codici_univoci"][
            "CodiceTipoXML"
        ].nunique()

        self.assertEqual(
            len(df),
            n_tipi * 3 * len(self.ns["REGOLE_NOMI"]) ** 2,
        )
        self.assertEqual(
            set(df["CampoCanonico"]),
            {"EAN", "CODICE_CLIENTE", "CODICE_FORNITORE"},
        )
        self.assertEqual(
            set(df["RegolaXML"]), set(self.ns["REGOLE_NOMI"])
        )
        self.assertEqual(
            set(df["RegolaCarico"]), set(self.ns["REGOLE_NOMI"])
        )
        self.assertTrue((df["Quota"] <= 1).all())

        # Una combinazione nota deve dare il match atteso.
        riga = df.loc[
            (df["CodiceTipoXML"] == "EAN")
            & (df["CampoCanonico"] == "EAN")
            & (df["RegolaXML"] == "RIMUOVI_SEPARATORI")
            & (df["RegolaCarico"] == "RIMUOVI_SEPARATORI")
        ]
        self.assertEqual(len(riga), 1)
        self.assertEqual(riga.iloc[0]["Match"], 1)

    def test_4_proposte_codici(self):
        proposte = self.ns["df_proposte_codici"].set_index(
            "CodiceTipoXML"
        )

        attesi = {
            "EAN": "EAN",
            "FORN": "CODICE_FORNITORE",
            "CLI": "CODICE_CLIENTE",
            "COD_F": "CODICE_FORNITORE",
            "GTIN": "EAN",
            "CODICE_27": "CODICE_CLIENTE",
        }
        for tipo, campo in attesi.items():
            self.assertEqual(
                proposte.loc[tipo, "CampoCanonico"],
                campo,
                f"{tipo}: {proposte.loc[tipo, 'EsempiMatch']}",
            )
            self.assertGreater(proposte.loc[tipo, "Match"], 0)
            self.assertEqual(proposte.loc[tipo, "Stato"], "OK")
            self.assertIn(
                proposte.loc[tipo, "RegolaXML"],
                self.ns["REGOLE_NOMI"],
            )
            self.assertIn(
                proposte.loc[tipo, "RegolaCarico"],
                self.ns["REGOLE_NOMI"],
            )

        # Tipi che non sono codici articolo: nessun match, nessuna proposta.
        for tipo in ("MINSAN", "XYZ"):
            self.assertEqual(
                proposte.loc[tipo, "CampoCanonico"], ""
            )
            self.assertEqual(proposte.loc[tipo, "Match"], 0)
            self.assertEqual(
                proposte.loc[tipo, "Stato"], "NESSUN MATCH"
            )

        # Ogni proposta è la riga con più match della sua griglia.
        griglia = self.ns["df_griglia_codici"]
        for tipo in attesi:
            self.assertEqual(
                proposte.loc[tipo, "Match"],
                griglia.loc[
                    griglia["CodiceTipoXML"] == tipo, "Match"
                ].max(),
            )

    def test_5_ddt_confronto_per_fattura(self):
        """Un DDT non può incrociare la bolla di un'altra fattura."""
        fatture = self.ns["fatture"]
        self.assertGreater(len(fatture), 0)
        normalizza = self.ns["normalizza"]
        regola = "RIMUOVI_SEPARATORI"

        riferimento_globale = set()
        per_fattura = 0
        globalmente = 0

        for fattura in fatture:
            self.assertEqual(
                len(fattura["ChiaveDocumento"]), 2
            )
            locale = {
                k
                for k in (
                    normalizza(v, regola)
                    for v in fattura["Carico"]
                )
                if k
            }
            riferimento_globale |= locale

            for valore in fattura["XML"]:
                chiave = normalizza(valore, regola)
                per_fattura += int(chiave in locale)

        # Conto "sbagliato": confronto globale, senza il vincolo
        # della fattura. Deve trovare almeno un match in più.
        globalmente = 0
        for fattura in fatture:
            for valore in fattura["XML"]:
                chiave = normalizza(valore, regola)
                globalmente += int(
                    chiave in riferimento_globale
                )

        griglia = self.ns["df_griglia_ddt_globale"]
        riga = griglia.loc[
            (griglia["CFOR"] == "TUTTI")
            & (griglia["RegolaDDTXML"] == regola)
            & (griglia["RegolaDDTCarico"] == regola)
        ]
        self.assertEqual(len(riga), 1)
        self.assertEqual(riga.iloc[0]["Match"], per_fattura)
        self.assertGreater(globalmente, per_fattura)

        # La fattura 00002 ha due DDT XML diversi e un solo DDT carico,
        # che non è quello dell'altra fattura.
        fattura_2 = [
            f for f in fatture
            if f["ChiaveDocumento"][1] == "00002"
        ]
        self.assertEqual(len(fattura_2), 1)
        self.assertEqual(
            fattura_2[0]["Carico"], {"DIVERSO/77"}
        )
        self.assertIn("A/001", fattura_2[0]["XML"])
        self.assertIn("X/1", fattura_2[0]["XML"])

    def test_6_proposte_ddt(self):
        griglia = self.ns["df_griglia_ddt_globale"]
        self.assertEqual(
            len(griglia),
            len(self.ns["REGOLE_NOMI"]) ** 2,
        )

        def match(r_xml, r_carico):
            return int(
                griglia.loc[
                    (griglia["RegolaDDTXML"] == r_xml)
                    & (griglia["RegolaDDTCarico"] == r_carico),
                    "Match",
                ].iloc[0]
            )

        self.assertGreater(
            match("RIMUOVI_SEPARATORI", "RIMUOVI_SEPARATORI"),
            match("NESSUNA_REGOLA", "NESSUNA_REGOLA"),
        )

        proposte = self.ns["df_proposte_ddt"].set_index("CFOR")
        self.assertIn("TUTTI", proposte.index)
        self.assertIn("F001", proposte.index)
        self.assertGreater(proposte.loc["TUTTI", "Match"], 0)
        self.assertEqual(
            proposte.loc["TUTTI", "Match"],
            griglia["Match"].max(),
        )
        self.assertGreater(proposte.loc["TUTTI", "DDTXML"], 0)
        self.assertEqual(proposte.loc["TUTTI", "Fatture"],
                         len(self.ns["fatture"]))

    def test_7_export_e_dizionario_non_toccato(self):
        self.assertFalse(
            any("Dizionario" in p for p in self.letture),
            "l'assistente ha letto il dizionario",
        )
        self.assertTrue(self.scritture)
        for percorso in self.scritture:
            self.assertEqual(
                Path(percorso).name,
                "proposte_dizionario_codici.xlsx",
            )

        file_excel = (
            self.cartella / "proposte_dizionario_codici.xlsx"
        )
        self.assertTrue(file_excel.exists())

        cartella_excel = openpyxl.load_workbook(file_excel)
        try:
            self.assertEqual(
                set(cartella_excel.sheetnames),
                {
                    "ProposteCodici", "ProposteDDT",
                    "GrigliaCodici", "GrigliaDDT",
                },
            )
        finally:
            cartella_excel.close()

        # Il dizionario sintetico resta intatto.
        self.assertEqual(
            len(dati_sintetici.DIZIONARIO["RegoleCodiciXML"]), 10
        )
        self.assertEqual(
            len(dati_sintetici.DIZIONARIO["RegoleCodiciCarico"]), 9
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
