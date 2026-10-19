"""
Esegue il notebook di riconciliazione senza Fabric.

Il notebook dipende da tre cose che in locale non esistono:
notebookutils (accesso a OneLake), i file Excel di origine e la
scrittura dell'export su OneLake. Qui vengono sostituite:

    notebookutils.fs.*   -> filesystem finto
    pd.read_excel        -> dati sintetici in memoria
    pd.ExcelWriter       -> cartella temporanea locale
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
    os.environ.get("QUAD_NOTEBOOK", RADICE / "Notebook_2 (1).ipynb")
)


class _FilesystemFinto:
    """Sostituisce notebookutils.fs: il notebook crede di lavorare."""

    def exists(self, percorso):
        return True

    def rm(self, percorso):
        return True

    def cp(self, sorgente, destinazione):
        return True

    def mkdirs(self, percorso):
        return True


class _NotebookutilsFinto:
    fs = _FilesystemFinto()


def _leggi_celle(percorso_notebook):
    """Restituisce il codice delle celle, come stringhe."""
    with open(percorso_notebook, encoding="utf-8") as file:
        notebook = json.load(file)

    return ["".join(cella["source"]) for cella in notebook["cells"]]


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


def esegui_notebook(percorso_notebook=NOTEBOOK, cartella_output=None):
    """
    Esegue le celle del notebook e restituisce il namespace finale
    (con dentro df_merge, df_fatture, map_ddt, ...).

    Se cartella_output è indicata, i file Excel prodotti vengono
    scritti lì; altrimenti in una cartella temporanea.
    """

    celle = _leggi_celle(percorso_notebook)
    codice_processo = celle[0]
    codice_export = celle[1] if len(celle) > 1 else ""

    _scrivi_zip(_percorso_zip(codice_processo))

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
        # nel notebook display() mostra i DataFrame: qui non serve
        "display": lambda *argomenti, **kwargs: None,
        "__name__": "__main__",
    }

    try:
        exec(compile(codice_processo, "cella_processo", "exec"), namespace)
        exec(compile(codice_export, "cella_export", "exec"), namespace)
    finally:
        pd.read_excel = lettura_originale
        pd.ExcelWriter = scrittore_originale

    namespace["_cartella_output"] = str(cartella_output)

    return namespace
