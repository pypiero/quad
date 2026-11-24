"""Verifica l'export diagnostico opzionale senza accedere a OneLake."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl
import pandas as pd
import pandas.testing as pdt

import harness


class TestExportDiagnostico(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(harness.NOTEBOOK, encoding="utf-8") as file:
            celle = json.load(file)["cells"]
        indici = [
            i for i, cella in enumerate(celle)
            if cella["cell_type"] == "markdown"
            and "".join(cella["source"]).startswith("## [16]")
        ]
        if len(indici) != 1 or celle[indici[0] + 1]["cell_type"] != "code":
            raise AssertionError("Cella export diagnostico [16] non trovata")
        cls.codice = compile("".join(celle[indici[0] + 1]["source"]), "cella_16", "exec")
        with contextlib.redirect_stdout(io.StringIO()):
            cls.namespace = harness.esegui_notebook()

    def test_disattivato_non_scrive_ne_cancella_export_precedente(self):
        namespace = dict(self.namespace, ESPORTA_DIAGNOSTICA=False)
        with tempfile.TemporaryDirectory() as cartella:
            percorso = Path(cartella) / "riconciliazione.xlsx"
            percorso.write_bytes(b"file precedente")
            with patch.object(pd, "ExcelWriter", side_effect=AssertionError("scrittura inattesa")):
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(self.codice, namespace)
            self.assertEqual(percorso.read_bytes(), b"file precedente")

    def test_notebook_con_export_attivo_mantiene_report_e_delta(self):
        with open(harness.NOTEBOOK, encoding="utf-8") as file:
            notebook = json.load(file)
        celle_config = [
            cella for cella in notebook["cells"]
            if cella["cell_type"] == "code"
            and "ESPORTA_DIAGNOSTICA = False" in "".join(cella["source"]).splitlines()
        ]
        self.assertEqual(len(celle_config), 1)
        cella = celle_config[0]
        cella["source"] = "".join(cella["source"]).replace(
            "ESPORTA_DIAGNOSTICA = False", "ESPORTA_DIAGNOSTICA = True"
        ).splitlines(keepends=True)
        with tempfile.TemporaryDirectory() as cartella:
            percorso = Path(cartella) / "notebook.ipynb"
            percorso.write_text(json.dumps(notebook), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                attivo = harness.esegui_notebook(percorso, cartella)
            self.assertTrue((Path(cartella) / "riconciliazione.xlsx").exists())
            self.assertFalse((Path(cartella) / "riconciliazione_powerbi.xlsx").exists())
            pdt.assert_frame_equal(attivo["df_merge"], self.namespace["df_merge"])
            pdt.assert_frame_equal(attivo["df_powerbi"], self.namespace["df_powerbi"])
            pdt.assert_frame_equal(
                attivo["spark"].dataframe_creati[0],
                self.namespace["spark"].dataframe_creati[0],
            )

    def test_attivato_esporta_df_merge(self):
        namespace = dict(self.namespace, ESPORTA_DIAGNOSTICA=True)
        prima = namespace["df_merge"].copy(deep=True)
        excel_writer = pd.ExcelWriter
        with tempfile.TemporaryDirectory() as cartella:
            def redirect(percorso, **kwargs):
                return excel_writer(Path(cartella) / Path(str(percorso)).name, **kwargs)

            with patch.object(pd, "ExcelWriter", redirect), contextlib.redirect_stdout(io.StringIO()):
                exec(self.codice, namespace)
            percorso = Path(cartella) / "riconciliazione.xlsx"
            self.assertTrue(percorso.exists())
            workbook = openpyxl.load_workbook(percorso, read_only=True)
            try:
                self.assertEqual(workbook.sheetnames, ["df_merge"])
                foglio = workbook["df_merge"]
                self.assertEqual([c.value for c in next(foglio.iter_rows())], list(prima.columns))
                self.assertEqual(foglio.max_row, len(prima) + 1)
            finally:
                workbook.close()
        pdt.assert_frame_equal(namespace["df_merge"], prima)


if __name__ == "__main__":
    unittest.main()
