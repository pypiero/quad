"""Verifica isolata della cella Delta, senza Fabric o un cluster Spark."""

import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import Mock

import pandas as pd

import harness


class TestScritturaDelta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(harness.RADICE / "Notebook_2 (1).ipynb", encoding="utf-8") as file:
            celle = json.load(file)["cells"]
        indici = [
            i for i, cella in enumerate(celle)
            if cella["cell_type"] == "markdown"
            and "".join(cella["source"]).startswith("## [18]")
        ]
        if len(indici) != 1 or celle[indici[0] + 1]["cell_type"] != "code":
            raise AssertionError("Cella di scrittura Delta [18] non trovata")
        cls.codice = compile("".join(celle[indici[0] + 1]["source"]), "cella_18", "exec")

    def test_scrive_dataframe_con_nomi_normalizzati_e_opzioni_previste(self):
        dataframe = pd.DataFrame({" Data fattura ": ["2026-01-01"], "CFOR": ["001"]})
        originale = dataframe.copy(deep=True)
        spark = harness._SparkFinto()
        namespace = {"df_powerbi": dataframe, "spark": spark}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            exec(self.codice, namespace)

        atteso = originale.set_axis(["Data_fattura", "CFOR"], axis=1)
        pd.testing.assert_frame_equal(dataframe, atteso)
        self.assertEqual(len(spark.scritture), 1)
        scrittura = spark.scritture[0]
        self.assertEqual(scrittura["nome"], "quadratura_powerbi")
        self.assertEqual(scrittura["formato"], "delta")
        self.assertEqual(scrittura["modalita"], "overwrite")
        self.assertEqual(scrittura["opzioni"], {"overwriteSchema": "true"})
        atteso = originale.set_axis(["Data_fattura", "CFOR"], axis=1)
        pd.testing.assert_frame_equal(scrittura["dataframe"], atteso)
        self.assertIn("con 1 righe", output.getvalue())

    def test_dataframe_vuoto_non_crea_dataframe_spark_ne_sovrascrive(self):
        dataframe = pd.DataFrame(columns=[" Data fattura "])
        originale = dataframe.copy(deep=True)
        spark = harness._SparkFinto()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            exec(self.codice, {"df_powerbi": dataframe, "spark": spark})

        pd.testing.assert_frame_equal(dataframe, originale.set_axis(["Data_fattura"], axis=1))
        self.assertEqual(spark.dataframe_creati, [])
        self.assertEqual(spark.scritture, [])
        self.assertIn("non è stata sovrascritta", output.getvalue())

    def test_errore_spark_non_viene_nascosto(self):
        spark = Mock()
        spark.createDataFrame.side_effect = RuntimeError("errore Spark")
        with self.assertRaisesRegex(RuntimeError, "errore Spark"):
            exec(self.codice, {"df_powerbi": pd.DataFrame({"colonna": [1]}), "spark": spark})


if __name__ == "__main__":
    unittest.main()
