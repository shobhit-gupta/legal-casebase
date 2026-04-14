import importlib.util
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NORMALIZE_PATH = REPO_ROOT / "scripts" / "normalize.py"
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"


def load_normalize_module():
    spec = importlib.util.spec_from_file_location(
        "normalize_under_test", NORMALIZE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def squash_ws(text: str) -> str:
    return " ".join(text.split())


class NormalizeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

        self.dockets_dir = self.base / "dockets"
        self.clusters_dir = self.base / "clusters"
        self.opinions_dir = self.base / "opinions"
        self.dockets_dir.mkdir(parents=True, exist_ok=True)
        self.clusters_dir.mkdir(parents=True, exist_ok=True)
        self.opinions_dir.mkdir(parents=True, exist_ok=True)

        self.module = load_normalize_module()

        self.conn = sqlite3.connect(self.base / "casebase.db")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.date_ingested = "2026-04-13T00:00:00+00:00"

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def run_quietly(self, fn, *args, **kwargs):
        with redirect_stdout(io.StringIO()):
            return fn(*args, **kwargs)

    def write_json(
        self, directory: Path, prefix: str, object_id: int, payload: dict
    ) -> None:
        path = directory / f"{prefix}_{object_id}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    def count(self, table: str) -> int:
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_plain_text_wins_over_html(self):
        opinion = {
            "id": 1,
            "plain_text": "  Plain text wins.  ",
            "html_with_citations": "<p>HTML should not be used</p>",
            "html": "<p>Fallback HTML</p>",
        }

        clean_text, text_source = self.module.derive_clean_text(1, opinion)

        self.assertEqual(clean_text, "Plain text wins.")
        self.assertEqual(text_source, "plain_text")

    def test_html_with_citations_fallback_is_used(self):
        opinion = {
            "id": 2,
            "plain_text": "",
            "html_with_citations": "<p>Hello <a href='/x'>world</a></p>",
            "html": "",
        }

        clean_text, text_source = self.module.derive_clean_text(2, opinion)

        self.assertEqual(squash_ws(clean_text), "Hello world")
        self.assertEqual(text_source, "html_with_citations")
        self.assertNotIn("<", clean_text)
        self.assertNotIn(">", clean_text)

    def test_html_fallback_is_used(self):
        opinion = {
            "id": 3,
            "plain_text": "",
            "html_with_citations": "",
            "html": "<div>Fallback <b>HTML</b> text</div>",
        }

        clean_text, text_source = self.module.derive_clean_text(3, opinion)

        self.assertEqual(squash_ws(clean_text), "Fallback HTML text")
        self.assertEqual(text_source, "html")

    def test_tag_only_html_is_rejected(self):
        opinion = {
            "id": 4,
            "plain_text": "",
            "html_with_citations": "<p><br/></p>",
            "html": "<div></div>",
        }

        with self.assertRaises(RuntimeError):
            self.module.derive_clean_text(4, opinion)

    def test_multiple_clusters_map_to_one_case(self):
        docket = {
            "id": 1001,
            "court_id": "scotus",
            "absolute_url": "/docket/1001/",
            "slug": "example-docket",
            "case_name": "Example Case",
            "case_name_short": "Example",
            "docket_number": "24-1001",
            "appeal_from_str": "Fifth Circuit",
            "original_court_info": {"docket_number": "22-50001"},
            "date_filed": "2025-01-01",
            "date_argued": None,
            "audio_files": [],
            "blocked": False,
        }

        cluster_one = {
            "id": 2001,
            "docket_id": 1001,
            "absolute_url": "/cluster/2001/",
            "slug": "cluster-one",
            "case_name": "Example Case Revisions 1",
            "date_filed": "2025-02-01",
            "judges": "Judge One",
            "precedential_status": "Published",
            "source": "U",
            "blocked": False,
        }

        cluster_two = {
            "id": 2002,
            "docket_id": 1001,
            "absolute_url": "/cluster/2002/",
            "slug": "cluster-two",
            "case_name": "Example Case Revisions 2",
            "date_filed": "2025-02-02",
            "judges": "Judge Two",
            "precedential_status": "Published",
            "source": "U",
            "blocked": False,
        }

        opinion_one = {
            "id": 3001,
            "cluster_id": 2001,
            "absolute_url": "/opinion/3001/",
            "type": "010combined",
            "author_id": None,
            "author_str": "   ",
            "per_curiam": False,
            "page_count": 10,
            "download_url": None,
            "sha1": "sha1-one",
            "plain_text": "Opinion one text",
            "html_with_citations": "",
            "html": "",
            "extracted_by_ocr": False,
        }

        opinion_two = {
            "id": 3002,
            "cluster_id": 2002,
            "absolute_url": "/opinion/3002/",
            "type": "010combined",
            "author_id": None,
            "author_str": "",
            "per_curiam": False,
            "page_count": 12,
            "download_url": None,
            "sha1": "sha1-two",
            "plain_text": "Opinion two text",
            "html_with_citations": "",
            "html": "",
            "extracted_by_ocr": False,
        }

        self.write_json(self.dockets_dir, "docket", 1001, docket)
        self.write_json(self.clusters_dir, "cluster", 2001, cluster_one)
        self.write_json(self.clusters_dir, "cluster", 2002, cluster_two)
        self.write_json(self.opinions_dir, "opinion", 3001, opinion_one)
        self.write_json(self.opinions_dir, "opinion", 3002, opinion_two)

        self.run_quietly(
            self.module.normalize_corpus, self.conn, self.base, self.date_ingested
        )

        self.assertEqual(self.count("cases"), 1)
        self.assertEqual(self.count("clusters"), 2)
        self.assertEqual(self.count("opinions"), 2)

        case_row = self.conn.execute(
            "SELECT id, source_docket_id FROM cases WHERE source_docket_id = ?",
            (1001,),
        ).fetchone()
        self.assertIsNotNone(case_row)

        cluster_rows = self.conn.execute(
            "SELECT source_cluster_id, case_id FROM clusters ORDER BY source_cluster_id"
        ).fetchall()
        self.assertEqual(len(cluster_rows), 2)
        self.assertEqual(cluster_rows[0]["case_id"], case_row["id"])
        self.assertEqual(cluster_rows[1]["case_id"], case_row["id"])

        opinion_rows = self.conn.execute(
            """
            SELECT source_opinion_id, case_id, cluster_id, author_str, author_display, text_source
            FROM opinions
            ORDER BY source_opinion_id
            """
        ).fetchall()

        self.assertEqual(len(opinion_rows), 2)
        self.assertEqual(opinion_rows[0]["case_id"], case_row["id"])
        self.assertEqual(opinion_rows[1]["case_id"], case_row["id"])
        self.assertIsNone(opinion_rows[0]["author_str"])
        self.assertEqual(opinion_rows[0]["author_display"], "Judge One")
        self.assertEqual(opinion_rows[1]["author_display"], "Judge Two")
        self.assertEqual(opinion_rows[0]["text_source"], "plain_text")
        self.assertEqual(opinion_rows[1]["text_source"], "plain_text")

    def test_missing_parent_cluster_fails_fast(self):
        opinion = {
            "id": 4001,
            "cluster_id": 9999,
            "absolute_url": "/opinion/4001/",
            "type": "010combined",
            "author_id": None,
            "author_str": "",
            "per_curiam": False,
            "page_count": 1,
            "download_url": None,
            "sha1": "sha1-missing",
            "plain_text": "Missing cluster text",
            "html_with_citations": "",
            "html": "",
            "extracted_by_ocr": False,
        }

        self.write_json(self.opinions_dir, "opinion", 4001, opinion)

        with self.assertRaises(RuntimeError):
            self.run_quietly(
                self.module.normalize_opinions,
                self.conn,
                self.opinions_dir,
                self.date_ingested,
                {},
            )


if __name__ == "__main__":
    unittest.main()
