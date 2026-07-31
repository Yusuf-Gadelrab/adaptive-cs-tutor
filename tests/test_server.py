"""
HTTP-level tests for server.py.

The server is started on an ephemeral port in a background thread and forced
into --no-llm mode, so the whole suite runs offline and deterministically.
"""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import graph_engine as ge
import server


class ServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.FORCE_NO_LLM = True  # never touch Ollama from the test suite
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        server.FORCE_NO_LLM = False

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path):
        with urllib.request.urlopen(self.url(path), timeout=15) as r:
            return r.status, r.read().decode("utf-8")

    def get_json(self, path):
        status, body = self.get(path)
        return status, json.loads(body)

    def post_json(self, path, obj):
        req = urllib.request.Request(
            self.url(path), data=json.dumps(obj).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))


class TestPages(ServerTestCase):
    def test_index_serves_html(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("<!doctype html>", body)
        self.assertIn("Adaptive CS Tutor", body)

    def test_index_carries_brand_palette(self):
        _, body = self.get("/")
        self.assertIn("#0a0a0a", body)
        self.assertIn("#d4af37", body)

    def test_index_cites_the_doi(self):
        _, body = self.get("/")
        self.assertIn("10.1145/3770761.3777339", body)

    def test_unknown_route_404s(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/nope")
        self.assertEqual(cm.exception.code, 404)


class TestGraphApi(ServerTestCase):
    def test_graph_payload_shape(self):
        status, data = self.get_json("/api/graph")
        self.assertEqual(status, 200)
        nodes = ge.load_graph()
        self.assertEqual(len(data["nodes"]), len(nodes))
        self.assertGreater(len(data["edges"]), 0)
        self.assertGreater(data["width"], 0)
        self.assertGreater(data["height"], 0)

    def test_every_node_has_a_position(self):
        _, data = self.get_json("/api/graph")
        for n in data["nodes"]:
            self.assertIsInstance(n["x"], int)
            self.assertIsInstance(n["y"], int)

    def test_edges_reference_real_nodes(self):
        _, data = self.get_json("/api/graph")
        ids = {n["id"] for n in data["nodes"]}
        for e in data["edges"]:
            self.assertIn(e["from"], ids)
            self.assertIn(e["to"], ids)

    def test_layout_places_prereqs_left_of_dependents(self):
        _, data = self.get_json("/api/graph")
        pos = {n["id"]: n for n in data["nodes"]}
        for e in data["edges"]:
            self.assertLess(pos[e["from"]]["x"], pos[e["to"]]["x"],
                            f"{e['from']} should sit left of {e['to']}")


class TestQuizApi(ServerTestCase):
    def test_quiz_never_leaks_the_answer_key(self):
        status, data = self.get_json("/api/quiz")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(data), 20)
        for q in data:
            self.assertNotIn("answer", q,
                             f"{q['id']} leaked its answer index to the client")

    def test_quiz_items_carry_what_the_ui_needs(self):
        _, data = self.get_json("/api/quiz")
        for q in data:
            self.assertTrue(q["prompt"])
            self.assertGreaterEqual(len(q["choices"]), 2)
            self.assertTrue(q["concept"])


class TestSubmitApi(ServerTestCase):
    def all_correct(self):
        return {q["id"]: q["answer"] for q in ge.load_quiz()}

    def test_perfect_score_leaves_no_gaps(self):
        status, data = self.post_json("/api/submit", {"answers": self.all_correct()})
        self.assertEqual(status, 200)
        self.assertEqual(data["shaky"], [])
        self.assertEqual(data["path"], [])
        self.assertTrue(all(s == "ok" for s in data["states"].values()))
        self.assertEqual(data["summary"]["at_risk"], 0)

    def test_scripted_demo_student_produces_expected_plan(self):
        quiz = ge.load_quiz()
        wrong = {"q2", "q9", "q18"}
        answers = {q["id"]: ((q["answer"] + 1) % len(q["choices"]))
                   if q["id"] in wrong else q["answer"] for q in quiz}
        _, data = self.post_json("/api/submit", {"answers": answers})
        self.assertEqual(data["shaky"], ["boolean_logic", "list_methods", "recursion"])
        self.assertEqual(data["path"][0]["concept"], "boolean_logic")
        self.assertGreater(data["summary"]["at_risk"], 0)
        self.assertEqual(data["summary"]["correct"], len(quiz) - 3)

    def test_path_rows_carry_display_names(self):
        quiz = ge.load_quiz()
        answers = {q["id"]: q["answer"] for q in quiz}
        answers["q2"] = (answers["q2"] + 1) % 4
        _, data = self.post_json("/api/submit", {"answers": answers})
        row = data["path"][0]
        self.assertEqual(row["name"], "Boolean Logic")
        self.assertEqual(len(row["unlock_names"]), len(row["unlocks"]))

    def test_empty_submission_marks_everything_missed(self):
        _, data = self.post_json("/api/submit", {"answers": {}})
        self.assertEqual(data["summary"]["correct"], 0)
        self.assertEqual(data["summary"]["answered"], 0)
        self.assertGreater(len(data["shaky"]), 0)

    def test_bad_json_is_rejected(self):
        req = urllib.request.Request(
            self.url("/api/submit"), data=b"{not json",
            headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=15)
        self.assertEqual(cm.exception.code, 400)

    def test_wrong_answers_type_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post_json("/api/submit", {"answers": ["a", "b"]})
        self.assertEqual(cm.exception.code, 400)

    def test_post_to_unknown_route_404s(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post_json("/api/nope", {})
        self.assertEqual(cm.exception.code, 404)


class TestExplainApi(ServerTestCase):
    def test_explain_returns_offline_passage_in_no_llm_mode(self):
        status, data = self.get_json("/api/explain?concept=recursion&lang=en")
        self.assertEqual(status, 200)
        self.assertEqual(data["source"], "fallback")
        self.assertTrue(data["text"].strip())

    def test_explain_reports_retrieval_provenance(self):
        _, data = self.get_json("/api/explain?concept=recursion&lang=en")
        self.assertTrue(data["retrieved"])
        self.assertEqual(len(data["retrieved_names"]), len(data["retrieved"]))
        self.assertIn("Functions", data["retrieved_names"])

    def test_arabic_response_is_arabic_and_keeps_code_english(self):
        _, data = self.get_json("/api/explain?concept=recursion&lang=ar")
        self.assertEqual(data["lang"], "ar")
        self.assertIn("keeps_code_english", data)

    def test_unknown_concept_404s(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get_json("/api/explain?concept=bogus")
        self.assertEqual(cm.exception.code, 404)

    def test_unsupported_language_falls_back_to_english(self):
        _, data = self.get_json("/api/explain?concept=lists&lang=fr")
        self.assertEqual(data["lang"], "en")

    def test_foundational_concept_has_no_prerequisites(self):
        _, data = self.get_json("/api/explain?concept=variables&lang=en")
        self.assertEqual(data["retrieved"], [])
        self.assertTrue(data["grounded"])  # nothing to build on

    def test_every_concept_is_explainable(self):
        for cid in ge.load_graph():
            _, data = self.get_json(f"/api/explain?concept={cid}&lang=en")
            self.assertTrue(data["text"].strip(), f"no explanation for {cid}")


class TestHealthApi(ServerTestCase):
    def test_health_reports_inventory(self):
        status, data = self.get_json("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["nodes"], len(ge.load_graph()))
        self.assertEqual(data["questions"], len(ge.load_quiz()))
        self.assertTrue(data["no_llm_forced"])
        self.assertFalse(data["ollama_available"])  # suppressed in no-llm mode


if __name__ == "__main__":
    unittest.main(verbosity=2)
