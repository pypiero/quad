"""Comportamento della scelta del primo valore disponibile nel report."""

import ast
import json
import unittest

import pandas as pd
import pandas.testing as pdt

import harness


class TestPrioritaReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(harness.NOTEBOOK, encoding="utf-8") as file:
            notebook = json.load(file)
        sorgente = next(
            "".join(notebook["cells"][i + 1]["source"])
            for i, cella in enumerate(notebook["cells"])
            if cella["cell_type"] == "markdown"
            and "".join(cella["source"]).startswith("## [17]")
        )
        albero = ast.parse(sorgente)
        funzioni = [nodo for nodo in albero.body if isinstance(nodo, ast.FunctionDef)
                    and nodo.name in ("pulisci_testo", "primo_valore_disponibile")]
        if len(funzioni) != 2:
            raise AssertionError("Funzioni di priorità report non trovate")
        namespace = {"pd": pd}
        exec(compile(ast.Module(body=funzioni, type_ignores=[]), "funzioni_report", "exec"), namespace)
        cls.funzione = staticmethod(namespace["primo_valore_disponibile"])

    def test_priorita_testi_vuoti_e_valore_predefinito(self):
        df = pd.DataFrame({"xml": [" A ", "  ", None], "carico": [" B ", " C ", ""]})
        risultato = self.funzione(df, ["xml", "carico"], default="Mancante")
        pdt.assert_series_equal(risultato, pd.Series(["A", "C", "Mancante"], dtype="string", name="xml"))

    def test_numeri_zero_e_date(self):
        df = pd.DataFrame({"xml": [0.0, None], "carico": [10.0, 20.0],
                           "data_xml": pd.to_datetime(["2025-01-02", None]),
                           "data_carico": pd.to_datetime(["2024-01-01", "2024-01-03"])})
        pdt.assert_series_equal(self.funzione(df, ["xml", "carico"]), pd.Series([0.0, 20.0], name="xml"))
        pdt.assert_series_equal(self.funzione(df, ["data_xml", "data_carico"]),
                                pd.Series(pd.to_datetime(["2025-01-02", "2024-01-03"]), name="data_xml"))

    def test_colonne_assenti_con_e_senza_permesso(self):
        df = pd.DataFrame({"presente": [" x ", ""]})
        with self.assertRaises(KeyError):
            self.funzione(df, ["assente", "presente"])
        pdt.assert_series_equal(
            self.funzione(df, ["assente", "presente"], default="n/a", ignora_colonne_assenti=True),
            pd.Series(["x", "n/a"], dtype="string", name="presente"),
        )
        self.assertEqual(
            self.funzione(df, ["assente"], default="n/a", ignora_colonne_assenti=True).tolist(),
            ["n/a", "n/a"],
        )


if __name__ == "__main__":
    unittest.main()
