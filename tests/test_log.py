"""Log testuale e debug: test con filesystem e Spark simulati."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pandas.testing as pdt

import dati_sintetici
import harness


class TestLog(unittest.TestCase):
    def esegui(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return harness.esegui_notebook(**kwargs)

    def test_log_iniziale_e_finale_con_avvisi(self):
        ns = self.esegui()
        fs = ns["notebookutils"].fs
        self.assertEqual(len(fs.scritture), 2)
        self.assertEqual(fs.scritture[0][0], fs.scritture[1][0])
        self.assertTrue(fs.scritture[0][0].endswith(".txt"))
        self.assertIn("Stato: IN_CORSO", fs.scritture[0][1])
        log = fs.scritture[1][1]
        self.assertIn("Stato: OK_CON_AVVISI", log)
        self.assertIn("Tabella aggiornata: SI", log)
        self.assertIn("Regole anomale o con default: 1", log)
        self.assertIn("Chiavi dizionario duplicate: 1", log)
        self.assertIn("XML non elaborati: 0", log)
        self.assertEqual(fs.file_scritti[ns["file_log"]], log)

    def test_log_senza_avvisi_e_senza_scrittura(self):
        ns = self.esegui()
        ns["df_errori"] = pd.DataFrame(columns=["File", "Errore"])
        ns["dizionari"]["Anomalie"] = pd.DataFrame()
        ns["dizionari"]["ChiaviDuplicate"] = pd.DataFrame()
        ns["regole_non_allineate"] = pd.DataFrame()
        ns["campi_non_riconosciuti"] = []
        ns["fatture_ambiguity"] = pd.Series(dtype="object")
        with contextlib.redirect_stdout(io.StringIO()):
            ns["concludi_log"](True)
        log = ns["notebookutils"].fs.file_scritti[ns["file_log"]]
        self.assertIn("Stato: OK\n", log)
        with contextlib.redirect_stdout(io.StringIO()):
            ns["concludi_log"](False)
        log = ns["notebookutils"].fs.file_scritti[ns["file_log"]]
        self.assertIn("Stato: OK_CON_AVVISI", log)
        self.assertIn("Tabella aggiornata: NO", log)

    def test_log_dizionario_mancante(self):
        ns = self.esegui()
        ns["df_diz_codici_xml"] = None
        with contextlib.redirect_stdout(io.StringIO()):
            ns["concludi_log"](True)
        log = ns["notebookutils"].fs.file_scritti[ns["file_log"]]
        self.assertIn("Fogli dizionario mancanti: 1", log)
        self.assertIn("Stato: OK_CON_AVVISI", log)

    def test_log_colonne_dizionario_mancanti(self):
        ns = self.esegui()
        ns["df_diz_codici_xml"] = ns["df_diz_codici_xml"].drop(columns=["CodiceTipoXML"])
        with contextlib.redirect_stdout(io.StringIO()):
            ns["concludi_log"](True)
        log = ns["notebookutils"].fs.file_scritti[ns["file_log"]]
        self.assertIn("Colonne dizionario mancanti: 1", log)
        self.assertIn("RegoleCodiciXML.CodiceTipoXML", log)
        self.assertIn("Stato: OK_CON_AVVISI", log)

    def test_log_errori_xml_limitati_a_cento(self):
        ns = self.esegui()
        ns["df_errori"] = pd.DataFrame({
            "File": [f"file_{i}.xml" for i in range(105)],
            "Errore": ["test\nerrore"] * 105,
        })
        with contextlib.redirect_stdout(io.StringIO()):
            ns["concludi_log"](True)
        log = ns["notebookutils"].fs.file_scritti[ns["file_log"]]
        self.assertIn("XML non elaborati: 105", log)
        self.assertIn("Ulteriori errori XML non elencati: 5", log)
        self.assertEqual(log.count("XML non elaborato:"), 100)
        self.assertIn("test errore", log)

    def test_nome_log_con_ora_italiana_e_ora_legale(self):
        with open(harness.NOTEBOOK, encoding="utf-8") as file:
            notebook = json.load(file)
        # Basta la cella di configurazione, che crea il log iniziale.
        notebook["cells"] = notebook["cells"][:3]
        cella = notebook["cells"][2]
        codice = "".join(cella["source"])
        for momento, atteso in (
            ("datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)", "20260115T130000000000+0100"),
            ("datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)", "20260715T140000000000+0200"),
            ("datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)", "20261025T023000000000+0200"),
            ("datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)", "20261025T023000000000+0100"),
        ):
            with self.subTest(momento=momento), tempfile.TemporaryDirectory() as cartella:
                cella["source"] = codice.replace("datetime.now(timezone.utc)", momento).splitlines(keepends=True)
                percorso = Path(cartella) / "notebook.ipynb"
                percorso.write_text(json.dumps(notebook), encoding="utf-8")
                ns = self.esegui(percorso_notebook=percorso, cartella_output=cartella)
                self.assertIn(f"quadratura_{atteso}_", ns["file_log"])
                self.assertIn("Inizio UTC:", ns["notebookutils"].fs.file_scritti[ns["file_log"]])

    def test_due_esecuzioni_non_sovrascrivono_lo_stesso_log(self):
        prima, seconda = self.esegui(), self.esegui()
        self.assertNotEqual(prima["file_log"], seconda["file_log"])

    def test_xml_non_leggibile_non_blocca_pubblicazione_e_va_nel_log(self):
        with patch.dict(dati_sintetici.XML_FILES, {"rotto.xml": "<xml non valido"}):
            ns = self.esegui()
        log = ns["notebookutils"].fs.file_scritti[ns["file_log"]]
        self.assertIn("Stato: OK_CON_AVVISI", log)
        self.assertIn("XML non elaborati: 1", log)
        self.assertIn("XML non elaborato: rotto.xml", log)
        self.assertIn("Tabella aggiornata: SI", log)
        self.assertEqual(ns["spark"].tabelle_scritte, ["quadratura_powerbi"])

    def test_errore_delta_e_registrato_e_non_nascosto(self):
        ns = self.esegui()
        codice = harness._leggi_celle(harness.NOTEBOOK)[-1]
        ns["spark"] = Mock()
        ns["spark"].createDataFrame.side_effect = RuntimeError("errore Spark")
        with self.assertRaisesRegex(RuntimeError, "errore Spark"):
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(codice, "cella_18", "exec"), ns)
        log = ns["notebookutils"].fs.file_scritti[ns["file_log"]]
        self.assertIn("Stato: ERRORE", log)
        self.assertIn("Tabella aggiornata: NON_CONFERMATA", log)
        self.assertIn("Errore scrittura Delta: RuntimeError: errore Spark", log)

    def test_errore_log_finale_dopo_scrittura_delta_e_segnalato(self):
        ns = self.esegui()
        codice = harness._leggi_celle(harness.NOTEBOOK)[-1]
        spark = harness._SparkFinto()
        ns["spark"] = spark
        with patch.object(ns["notebookutils"].fs, "put", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "Impossibile scrivere il log"):
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(codice, "cella_18", "exec"), ns)
        self.assertEqual(spark.tabelle_scritte, ["quadratura_powerbi"])

    def test_errore_precedente_lascia_log_in_corso(self):
        utils = harness._NotebookutilsFinto()
        with patch.object(harness, "_NotebookutilsFinto", return_value=utils), \
             patch.object(harness, "_lettura_excel_finta", side_effect=RuntimeError("input non leggibile")):
            with self.assertRaisesRegex(RuntimeError, "input non leggibile"):
                self.esegui()
        self.assertEqual(len(utils.fs.file_scritti), 1)
        self.assertIn("Stato: IN_CORSO", next(iter(utils.fs.file_scritti.values())))

    def test_errore_nella_scrittura_iniziale_non_e_nascosto(self):
        with patch.object(harness._FilesystemFinto, "put", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "Impossibile scrivere il log"):
                self.esegui()

    def test_debug_cambia_anteprime_ma_non_risultati(self):
        normale = self.esegui()
        with open(harness.NOTEBOOK, encoding="utf-8") as file:
            notebook = json.load(file)
        for cella in notebook["cells"]:
            if cella["cell_type"] == "code":
                sorgente = "".join(cella["source"])
                if "DEBUG = False" in sorgente.splitlines():
                    cella["source"] = sorgente.replace("DEBUG = False", "DEBUG = True").splitlines(keepends=True)
                    break
        else:
            self.fail("Flag DEBUG non trovato")
        with tempfile.TemporaryDirectory() as cartella:
            percorso = Path(cartella) / "debug.ipynb"
            percorso.write_text(json.dumps(notebook), encoding="utf-8")
            debug = self.esegui(percorso_notebook=percorso)
        pdt.assert_frame_equal(normale["df_merge"], debug["df_merge"])
        pdt.assert_frame_equal(normale["df_powerbi"], debug["df_powerbi"])
        pdt.assert_frame_equal(normale["spark"].dataframe_creati[0], debug["spark"].dataframe_creati[0])
        self.assertIn("Stato: OK_CON_AVVISI", debug["notebookutils"].fs.file_scritti[debug["file_log"]])


if __name__ == "__main__":
    unittest.main()
