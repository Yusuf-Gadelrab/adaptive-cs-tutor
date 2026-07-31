"""
Tests for explainer.py — retrieval, prompt construction, reasoning-strip and
the offline fallback contract.

No network. Every test that touches the model path monkeypatches
explainer.call_ollama, so the suite passes with Ollama stopped.
"""
import json
import unittest
import urllib.error

import explainer
import graph_engine as ge


class TestStripThinking(unittest.TestCase):
    def test_wellformed_block_removed(self):
        self.assertEqual(
            explainer.strip_thinking("<think>reasoning here</think>\n\nThe answer."),
            "The answer.")

    def test_orphan_closing_tag_removed(self):
        # what qwen3-fast actually emits: the opening tag is consumed by the
        # chat template, so only the closing tag reaches us
        raw = "We are asked to explain X.\n We should mention Y.\n</think>\n\nX is a thing."
        self.assertEqual(explainer.strip_thinking(raw), "X is a thing.")

    def test_unterminated_block_yields_nothing_usable(self):
        # reasoning ran past num_predict and was cut off mid-thought
        self.assertEqual(explainer.strip_thinking("<think>still reasoning and rea"), "")

    def test_last_closing_tag_wins(self):
        raw = "a</think>b</think>final answer"
        self.assertEqual(explainer.strip_thinking(raw), "final answer")

    def test_clean_text_untouched(self):
        self.assertEqual(explainer.strip_thinking("  Just an answer.  "),
                         "Just an answer.")

    def test_empty_input(self):
        self.assertEqual(explainer.strip_thinking(""), "")
        self.assertEqual(explainer.strip_thinking(None), "")


class TestRetrieval(unittest.TestCase):
    def setUp(self):
        self.nodes = ge.load_graph()

    def test_foundational_concept_retrieves_nothing(self):
        ctx = explainer.retrieve(self.nodes, "variables")
        self.assertEqual(ctx["retrieved"], [])
        self.assertEqual(ctx["full_chain"], [])

    def test_retrieves_at_most_k(self):
        ctx = explainer.retrieve(self.nodes, "recursion_complexity", k=4)
        self.assertLessEqual(len(ctx["retrieved"]), 4)

    def test_retrieved_are_genuine_ancestors(self):
        ctx = explainer.retrieve(self.nodes, "recursion")
        chain = set(ge.prereq_chain(self.nodes, "recursion"))
        for p in ctx["retrieved"]:
            self.assertIn(p["id"], chain)

    def test_retrieves_nearest_ancestors_not_roots(self):
        # the last K of a root-first chain are the most recently taught
        ctx = explainer.retrieve(self.nodes, "recursion", k=2)
        got = [p["id"] for p in ctx["retrieved"]]
        self.assertEqual(got, ge.prereq_chain(self.nodes, "recursion")[-2:])

    def test_every_passage_carries_real_text(self):
        ctx = explainer.retrieve(self.nodes, "sorting")
        self.assertTrue(ctx["retrieved"])
        for p in ctx["retrieved"]:
            self.assertTrue(p["text"].strip(), f"empty passage for {p['id']}")

    def test_arabic_retrieval_returns_arabic_passages(self):
        ctx = explainer.retrieve(self.nodes, "sorting", lang="ar")
        self.assertTrue(any(explainer.has_arabic(p["text"]) for p in ctx["retrieved"]))


class TestPromptConstruction(unittest.TestCase):
    def setUp(self):
        self.nodes = ge.load_graph()

    def test_prompt_contains_retrieved_passages(self):
        ctx = explainer.retrieve(self.nodes, "recursion")
        msgs = explainer.build_messages(ctx, "en")
        blob = " ".join(m["content"] for m in msgs)
        for p in ctx["retrieved"]:
            self.assertIn(p["name"], blob)

    def test_arabic_prompt_demands_english_identifiers(self):
        ctx = explainer.retrieve(self.nodes, "recursion", lang="ar")
        blob = " ".join(m["content"] for m in explainer.build_messages(ctx, "ar"))
        self.assertTrue(explainer.has_arabic(blob))
        self.assertIn("English", blob)

    def test_foundational_prompt_says_no_prior_knowledge(self):
        ctx = explainer.retrieve(self.nodes, "variables")
        blob = " ".join(m["content"] for m in explainer.build_messages(ctx, "en"))
        self.assertIn("no prior programming knowledge", blob)

    def test_chatml_preencloses_an_empty_think_block(self):
        """The whole reason generation stays fast and clean."""
        rendered = explainer.render_chatml([
            {"role": "system", "content": "S"},
            {"role": "user", "content": "U"},
        ])
        self.assertTrue(rendered.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n"))
        self.assertIn("<|im_start|>system\nS<|im_end|>", rendered)
        self.assertIn("<|im_start|>user\nU<|im_end|>", rendered)

    def test_chatml_think_block_is_empty(self):
        rendered = explainer.render_chatml([{"role": "user", "content": "U"}])
        between = rendered.split("<think>")[1].split("</think>")[0]
        self.assertEqual(between.strip(), "")


class TestFallbackContract(unittest.TestCase):
    """explain() must never raise because of the model."""

    def setUp(self):
        self.nodes = ge.load_graph()
        self._real = explainer.call_ollama

    def tearDown(self):
        explainer.call_ollama = self._real

    def test_no_llm_flag_never_calls_model(self):
        def boom(*a, **k):
            raise AssertionError("model was called despite no_llm=True")
        explainer.call_ollama = boom
        res = explainer.explain(self.nodes, "recursion", no_llm=True)
        self.assertEqual(res["source"], "fallback")
        self.assertTrue(res["text"].strip())

    def test_connection_error_falls_back(self):
        def boom(*a, **k):
            raise urllib.error.URLError("connection refused")
        explainer.call_ollama = boom
        res = explainer.explain(self.nodes, "recursion", use_cache=False)
        self.assertEqual(res["source"], "fallback")
        self.assertTrue(res["text"].strip())

    def test_timeout_falls_back(self):
        def boom(*a, **k):
            raise TimeoutError("too slow")
        explainer.call_ollama = boom
        res = explainer.explain(self.nodes, "lists", use_cache=False)
        self.assertEqual(res["source"], "fallback")

    def test_garbage_response_falls_back(self):
        def junk(*a, **k):
            raise json.JSONDecodeError("bad", "", 0)
        explainer.call_ollama = junk
        res = explainer.explain(self.nodes, "lists", use_cache=False)
        self.assertEqual(res["source"], "fallback")

    def test_empty_generation_falls_back(self):
        explainer.call_ollama = lambda *a, **k: ("", 0.1)
        res = explainer.explain(self.nodes, "lists", use_cache=False)
        self.assertEqual(res["source"], "fallback")

    def test_reasoning_only_generation_falls_back(self):
        """Truncated chain-of-thought must never be served as a lesson."""
        explainer.call_ollama = lambda *a, **k: ("<think>hmm let me consider", 0.1)
        res = explainer.explain(self.nodes, "lists", use_cache=False)
        self.assertEqual(res["source"], "fallback")
        self.assertNotIn("<think>", res["text"])

    def test_successful_generation_is_reported_as_llm(self):
        explainer.call_ollama = lambda *a, **k: ("Lists hold ordered values.", 1.5)
        res = explainer.explain(self.nodes, "lists", use_cache=False)
        self.assertEqual(res["source"], "llm")
        self.assertEqual(res["text"], "Lists hold ordered values.")
        self.assertEqual(res["elapsed"], 1.5)

    def test_result_shape_is_stable_across_sources(self):
        keys = {"concept", "lang", "text", "source", "retrieved", "chain_len", "elapsed"}
        explainer.call_ollama = lambda *a, **k: ("ok", 1.0)
        live = explainer.explain(self.nodes, "lists", use_cache=False)
        offline = explainer.explain(self.nodes, "lists", no_llm=True)
        self.assertEqual(set(live), keys)
        self.assertEqual(set(offline), keys)

    def test_fallback_covers_every_concept_in_both_languages(self):
        for cid in self.nodes:
            for lang in ("en", "ar"):
                text = explainer.canned_explanation(cid, lang)
                self.assertTrue(text.strip(), f"missing {lang} fallback for {cid}")
        # the Arabic corpus really is Arabic
        arabic = [explainer.canned_explanation(c, "ar") for c in self.nodes]
        self.assertTrue(all(explainer.has_arabic(t) for t in arabic))


class TestMetrics(unittest.TestCase):
    def setUp(self):
        self.nodes = ge.load_graph()

    def test_grounded_detects_named_prerequisite(self):
        ctx = explainer.retrieve(self.nodes, "recursion")
        self.assertTrue(explainer.grounded_in(
            "Recursion builds on Functions by calling itself.", ctx))

    def test_grounded_is_false_when_no_prerequisite_mentioned(self):
        ctx = explainer.retrieve(self.nodes, "recursion")
        self.assertFalse(explainer.grounded_in("It is a thing that repeats.", ctx))

    def test_foundational_concept_is_grounded_by_definition(self):
        ctx = explainer.retrieve(self.nodes, "variables")
        self.assertTrue(explainer.grounded_in("anything at all", ctx))

    def test_code_preservation_detects_english_keywords(self):
        self.assertTrue(explainer.preserves_code_identifiers(
            "الدالة تستدعي نفسها. مثال: `def factorial(n): return 1`"))

    def test_code_preservation_false_for_pure_arabic_prose(self):
        self.assertFalse(explainer.preserves_code_identifiers(
            "هذا شرح بالعربية بدون أي رمز برمجي على الإطلاق."))

    def test_code_preservation_detects_code_fence(self):
        self.assertTrue(explainer.preserves_code_identifiers(
            "شرح\n```python\nx = 5\n```"))

    def test_has_arabic(self):
        self.assertTrue(explainer.has_arabic("مرحبا"))
        self.assertFalse(explainer.has_arabic("hello world"))
        self.assertFalse(explainer.has_arabic(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
