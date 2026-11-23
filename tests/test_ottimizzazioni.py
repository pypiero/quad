"""Regressioni delle semplificazioni: ordinamento XML e report rieseguibile."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pandas.testing as pdt

import harness


class TestOttimizzazioni(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.namespace = harness.esegui_notebook()

    def test_codici_xml_nascono_gia_ordinati(self):
        with open(harness.NOTEBOOK, encoding="utf-8") as file:
            notebook = json.load(file)
        # Esegue soltanto [1]-[3], prima che join e filtri modifichino i codici.
        notebook["cells"] = notebook["cells"][:7]
        with tempfile.TemporaryDirectory() as cartella:
            percorso = Path(cartella) / "prime_celle.ipynb"
            percorso.write_text(json.dumps(notebook), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                namespace = harness.esegui_notebook(percorso, cartella)
        codici = namespace["df_xml_codici_articolo"]
        self.assertGreater(len(codici), 0)
        # Prima del filtro dizionario non devono esistere codici virtuali
        # derivati dal tag Descrizione della linea.
        self.assertNotIn("Descrizione", set(codici["CodiceTipoXML"].dropna()))
        ordinati = codici.sort_values(
            ["ChiaveRigaXML", "ProgressivoCodiceXML"], na_position="last"
        ).reset_index(drop=True)
        pdt.assert_frame_equal(codici, ordinati)

    def test_report_non_modifica_merge_ed_e_rieseguibile(self):
        namespace = dict(self.namespace)
        prima = namespace["df_merge"].copy(deep=True)
        atteso = namespace["df_powerbi"].rename(
            columns=lambda nome: nome.replace("_", " ")
        )
        codice = harness._leggi_celle(harness.NOTEBOOK)[-2]
        excel_writer = pd.ExcelWriter
        with tempfile.TemporaryDirectory() as cartella:
            def redirect(percorso, **kwargs):
                return excel_writer(Path(cartella) / Path(str(percorso)).name, **kwargs)

            with patch.object(pd, "ExcelWriter", redirect), contextlib.redirect_stdout(io.StringIO()):
                for _ in range(2):
                    exec(compile(codice, "cella_17", "exec"), namespace)
                    pdt.assert_frame_equal(namespace["df_merge"], prima)
                    pdt.assert_frame_equal(namespace["df_powerbi"], atteso)


if __name__ == "__main__":
    unittest.main()
