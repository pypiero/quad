"""
Esegue il notebook di riconciliazione senza Fabric.

Il notebook dipende da servizi e file non disponibili in locale.
Qui vengono sostituiti:

    notebookutils.fs.*   -> filesystem finto
    pd.read_excel        -> dati sintetici in memoria
    pd.ExcelWriter       -> cartella temporanea locale
    spark                -> simulazione di scrittura Delta
    display()            -> funzione che non stampa nulla

Il codice del notebook NON viene modificato: viene letto
dall'.ipynb ed eseguito così com'è, cella per cella.
"""

import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

import dati_sintetici

RADICE = Path(__file__).resolve().parents[1]

# Si può puntare a un altro notebook con QUAD_NOTEBOOK, utile per
# provare il test contro una versione modificata.
NOTEBOOK = Path(
    os.environ.get("QUAD_NOTEBOOK", RADICE / "Quadratura_Fatture.ipynb")
)


class _FilesystemFinto:
    """Sostituisce notebookutils.fs e registra i log in memoria."""

    def __init__(self):
        self.file_scritti = {}
        self.scritture = []

    def put(self, percorso, contenuto, overwrite=False):
        if not overwrite and percorso in self.file_scritti:
            return False
        self.file_scritti[percorso] = contenuto
        self.scritture.append((percorso, contenuto))
        return True

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
        self.fs = _FilesystemFinto()


class _ScrittoreDeltaFinto:
    """Registra la configurazione e la destinazione della scrittura Spark."""

    def __init__(self, spark, dataframe):
        self.spark = spark
        self.dataframe = dataframe
        self.formato = None
        self.modalita = None
        self.opzioni = {}

    def format(self, formato):
        self.formato = formato
        return self

    def mode(self, modalita):
        self.modalita = modalita
        return self

    def option(self, nome, valore):
        self.opzioni[nome] = valore
        return self

    def saveAsTable(self, nome):
        self.spark.tabelle_scritte.append(nome)
        self.spark.scritture.append({
            "nome": nome,
            "formato": self.formato,
            "modalita": self.modalita,
            "opzioni": self.opzioni.copy(),
            "dataframe": self.dataframe,
        })


class _DataFrameSparkFinto:
    def __init__(self, spark, dataframe):
        self.write = _ScrittoreDeltaFinto(spark, dataframe)


class _SparkFinto:
    """Registra le conversioni e scritture senza richiedere Fabric."""

    def __init__(self):
        self.tabelle_scritte = []
        self.scritture = []
        self.dataframe_creati = []

    def createDataFrame(self, dataframe):
        self.dataframe_creati.append(dataframe.copy())
        return _DataFrameSparkFinto(self, dataframe.copy())

    def table(self, nome):
        raise AssertionError(f"Accesso a tabella Spark non previsto dal test: {nome}")


def _leggi_celle(percorso_notebook):
    """Restituisce il codice delle celle di codice non vuote, in ordine."""
    with open(percorso_notebook, encoding="utf-8") as file:
        notebook = json.load(file)

    celle_codice = []
    for cella in notebook["cells"]:
        if cella.get("cell_type") != "code":
            continue
        codice = "".join(cella.get("source", []))
        if codice.strip():
            celle_codice.append(codice)

    return celle_codice


def _percorso_zip(codice):
    """
    Trova il percorso locale dello ZIP usato dal notebook, così il
    test resta valido anche se il percorso cambia nel notebook.
    """
    trovato = re.search(
        r'zip_locale_python\s*=\s*"([^"]+)"',
        codice,
    )

    if trovato is None:
        raise RuntimeError(
            "zip_locale_python non trovato nel notebook: "
            "aggiornare tests/harness.py"
        )

    return Path(trovato.group(1))


def _scrivi_zip(percorso):
    percorso.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(percorso, "w") as archivio:
        for nome, contenuto in dati_sintetici.XML_FILES.items():
            archivio.writestr(nome, contenuto)


def _lettura_excel_finta(percorso, sheet_name=None, **kwargs):
    """
    Smista le letture Excel del notebook sui dati sintetici, in base
    al nome del file. Un nome non previsto è un errore: meglio
    accorgersene subito che testare dati sbagliati in silenzio.
    """

    nome = Path(str(percorso)).name

    if nome.startswith("Dizionario"):
        return {
            foglio: tabella.copy()
            for foglio, tabella in dati_sintetici.DIZIONARIO.items()
        }

    tabelle = {
        "TAB_CM_Fatture_BI.xlsx": dati_sintetici.CARICHI,
        "ANAGRAFICA_PDV.xlsx": dati_sintetici.CPCO,
        "TAB_ANAGRAFICA_EAN.xlsx": dati_sintetici.EAN,
        "TAB_ANAGRAFICA_CARF.xlsx": dati_sintetici.CARF,
    }

    if nome in tabelle:
        return tabelle[nome].copy()

    raise AssertionError(
        f"Lettura Excel non prevista dal test: {percorso}"
    )


def esegui_notebook(percorso_notebook=NOTEBOOK, cartella_output=None, esporta_excel_powerbi=None):
    """
    Esegue le celle del notebook e restituisce il namespace finale
    (con dentro df_merge, df_fatture, map_ddt, ...).

    Se cartella_output è indicata, i file Excel prodotti vengono
    scritti lì; altrimenti in una cartella temporanea. Il parametro opzionale
    esporta_excel_powerbi sovrascrive il flag di configurazione nei test.
    """

    celle = _leggi_celle(percorso_notebook)

    _scrivi_zip(_percorso_zip("\n".join(celle)))

    if cartella_output is None:
        cartella_output = tempfile.mkdtemp(prefix="quad_test_")

    cartella_output = Path(cartella_output)
    cartella_output.mkdir(parents=True, exist_ok=True)

    lettura_originale = pd.read_excel
    scrittore_originale = pd.ExcelWriter

    def scrittura_redirect(percorso, **kwargs):
        destinazione = cartella_output / Path(str(percorso)).name
        return scrittore_originale(destinazione, **kwargs)

    pd.read_excel = _lettura_excel_finta
    pd.ExcelWriter = scrittura_redirect

    namespace = {
        "pd": pd,
        "notebookutils": _NotebookutilsFinto(),
        "spark": _SparkFinto(),
        # nel notebook display() mostra i DataFrame: qui non serve
        "display": lambda *argomenti, **kwargs: None,
        "__name__": "__main__",
    }

    try:
        for indice, codice_cella in enumerate(celle, start=1):
            exec(compile(codice_cella, f"cella_{indice}", "exec"), namespace)
            if indice == 1 and esporta_excel_powerbi is not None:
                namespace["ESPORTA_EXCEL_POWERBI"] = esporta_excel_powerbi
    finally:
        pd.read_excel = lettura_originale
        pd.ExcelWriter = scrittore_originale

    namespace["_cartella_output"] = str(cartella_output)

    return namespace
