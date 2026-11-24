"""Test delle diagnostiche del report e dell'export Excel opzionale."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import pandas.testing as pdt

import harness


class TestReportMatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.namespace = harness.esegui_notebook()
        with open(harness.NOTEBOOK, encoding="utf-8") as file:
            celle = json.load(file)["cells"]
        def codice(label):
            indici = [i for i, cella in enumerate(celle)
                      if cella["cell_type"] == "markdown"
                      and "".join(cella["source"]).startswith(f"## [{label}]")]
            if len(indici) != 1 or celle[indici[0] + 1]["cell_type"] != "code":
                raise AssertionError(f"Cella [{label}] non trovata")
            return compile("".join(celle[indici[0] + 1]["source"]), f"cella_{label}", "exec")
        cls.codice_6bis = codice("6-bis")

    def test_diagnostica_regole_silenziosa_se_non_ci_sono_anomalie(self):
        for anomalie in (pd.DataFrame(), pd.DataFrame({"Stato": ["NON RICONOSCIUTA"]})):
            viste = []
            namespace = {"dizionari": {"Anomalie": anomalie, "ChiaviDuplicate": pd.DataFrame()},
                         "display": viste.append}
            with contextlib.redirect_stdout(io.StringIO()) as output:
                exec(self.codice_6bis, namespace)
            self.assertNotIn("Nessuna regola non riconosciuta", output.getvalue())
            if anomalie.empty:
                self.assertEqual(viste, [])
            else:
                self.assertIn("Regole non riconosciute", output.getvalue())
                self.assertIs(viste[0], anomalie)

    def test_match_report_replica_merge_e_preserva_casi_speciali(self):
        ns = self.namespace
        report = ns["df_powerbi"]
        merge = ns["df_merge"]
        for nome, originale in (
            ("Tipo_match_articolo", "TipoMatch"),
            ("Metodo_match_DDT", "MetodoMatchDDT"),
        ):
            pdt.assert_series_equal(
                report[nome], merge[originale].astype("string").fillna("").reset_index(drop=True),
                check_names=False,
            )
        self.assertTrue({"EAN", "CART", "CALA", "Nessun match", "Solo carico"}.issubset(
            set(report["Tipo_match_articolo"])))
        self.assertTrue({"TESTO", "DATA_UNIVOCA", "UNICO_RESIDUO_DATA_MANCANTE"}.issubset(
            set(report["Metodo_match_DDT"])))
        derivato = merge["OrigineChiaveDDT"].eq("DDT_UNICO_CARICO").fillna(False)
        self.assertTrue(derivato.any())
        self.assertTrue(report.loc[derivato, "Metodo_match_DDT"].eq("").all())
        solo_carico = report["Stato_abbinamento"].eq("Solo carico")
        self.assertTrue(report.loc[solo_carico, "Metodo_match_DDT"].eq("").all())
        self.assertNotIn("Origine_chiave_DDT", report.columns)
        pdt.assert_frame_equal(ns["spark"].dataframe_creati[0], report)

    def test_excel_powerbi_disattivato_e_attivabile_senza_cambiare_delta(self):
        with tempfile.TemporaryDirectory() as cartella:
            path = Path(cartella) / "riconciliazione_powerbi.xlsx"
            path.write_bytes(b"file precedente")
            with contextlib.redirect_stdout(io.StringIO()):
                disattivo = harness.esegui_notebook(cartella_output=cartella)
            self.assertEqual(path.read_bytes(), b"file precedente")
            with contextlib.redirect_stdout(io.StringIO()):
                attivo = harness.esegui_notebook(cartella_output=cartella, esporta_excel_powerbi=True)
            self.assertNotEqual(path.read_bytes(), b"file precedente")
            pdt.assert_frame_equal(attivo["df_merge"], disattivo["df_merge"])
            pdt.assert_frame_equal(attivo["df_powerbi"], disattivo["df_powerbi"])
            pdt.assert_frame_equal(attivo["spark"].dataframe_creati[0], disattivo["spark"].dataframe_creati[0])


if __name__ == "__main__":
    unittest.main()
