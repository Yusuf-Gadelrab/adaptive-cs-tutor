"""
Standalone tests for graph_engine.py — no Ollama, no server, no network.
Run: python3 test_graph_engine.py
"""
import unittest
import graph_engine as ge


class TestGraphLoad(unittest.TestCase):
    def setUp(self):
        self.nodes = ge.load_graph()
        self.dependents = ge.build_dependents(self.nodes)

    def test_graph_loads_and_has_enough_nodes(self):
        self.assertGreaterEqual(len(self.nodes), 28)

    def test_no_missing_prereq_ids(self):
        # build_dependents raises if a prereq references an unknown id;
        # calling it in setUp already validates this, so just re-assert shape.
        for nid, deps in self.dependents.items():
            self.assertIsInstance(deps, list)

    def test_no_cycles(self):
        # topo_levels raises ValueError on cycles
        levels = ge.topo_levels(self.nodes)
        self.assertEqual(len(levels), len(self.nodes))

    def test_root_nodes_have_no_prereqs(self):
        self.assertEqual(self.nodes["variables"]["prereqs"], [])


class TestPropagation(unittest.TestCase):
    def setUp(self):
        self.nodes = ge.load_graph()
        self.dependents = ge.build_dependents(self.nodes)

    def test_no_shaky_all_ok(self):
        states = ge.compute_states(self.nodes, self.dependents, [])
        self.assertTrue(all(s == "ok" for s in states.values()))

    def test_root_shaky_marks_self_shaky(self):
        states = ge.compute_states(self.nodes, self.dependents, ["variables"])
        self.assertEqual(states["variables"], "shaky")

    def test_root_shaky_propagates_to_descendants(self):
        states = ge.compute_states(self.nodes, self.dependents, ["variables"])
        # data_types depends directly on variables
        self.assertEqual(states["data_types"], "at_risk")
        # lists depends on data_types (transitively on variables)
        self.assertEqual(states["lists"], "at_risk")
        # deep transitive descendant: sorting depends on lists
        self.assertEqual(states["sorting"], "at_risk")

    def test_unrelated_branch_stays_ok(self):
        # marking 'recursion' shaky should not affect 'lists' (no path)
        states = ge.compute_states(self.nodes, self.dependents, ["recursion"])
        self.assertEqual(states["lists"], "ok")

    def test_leaf_shaky_has_no_descendants_at_risk(self):
        # file_io is a leaf (nothing depends on it)
        states = ge.compute_states(self.nodes, self.dependents, ["file_io"])
        at_risk_count = sum(1 for s in states.values() if s == "at_risk")
        self.assertEqual(at_risk_count, 0)

    def test_multiple_shaky_union_of_descendants(self):
        states = ge.compute_states(self.nodes, self.dependents, ["loops_for", "loops_while"])
        self.assertEqual(states["nested_loops"], "at_risk")
        self.assertEqual(states["loops_for"], "shaky")
        self.assertEqual(states["loops_while"], "shaky")

    def test_shaky_wins_over_at_risk_if_both_apply(self):
        # functions depends on conditionals; mark both shaky directly
        states = ge.compute_states(self.nodes, self.dependents, ["conditionals", "functions"])
        self.assertEqual(states["functions"], "shaky")
        self.assertEqual(states["conditionals"], "shaky")

    def test_unknown_shaky_id_raises(self):
        with self.assertRaises(ValueError):
            ge.compute_states(self.nodes, self.dependents, ["not_a_real_concept"])


class TestPrereqChain(unittest.TestCase):
    def setUp(self):
        self.nodes = ge.load_graph()

    def test_root_has_empty_chain(self):
        self.assertEqual(ge.prereq_chain(self.nodes, "variables"), [])

    def test_chain_includes_all_ancestors_in_order(self):
        chain = ge.prereq_chain(self.nodes, "recursion")
        # recursion depends on functions + conditionals, which trace back to variables
        self.assertIn("functions", chain)
        self.assertIn("conditionals", chain)
        self.assertIn("boolean_logic", chain)
        self.assertIn("operators", chain)
        self.assertIn("variables", chain)
        # ancestors must come before the things that depend on them
        self.assertLess(chain.index("variables"), chain.index("operators"))
        self.assertLess(chain.index("operators"), chain.index("boolean_logic"))
        self.assertLess(chain.index("boolean_logic"), chain.index("conditionals"))
        self.assertLess(chain.index("conditionals"), chain.index("functions"))

    def test_unknown_concept_raises(self):
        with self.assertRaises(ValueError):
            ge.prereq_chain(self.nodes, "nope")


class TestQuizScoring(unittest.TestCase):
    def setUp(self):
        import json
        with open("quiz.json") as f:
            self.quiz = json.load(f)["questions"]

    def test_all_correct_no_shaky(self):
        answers = {q["id"]: q["answer"] for q in self.quiz}
        shaky, results = ge.score_quiz(self.quiz, answers)
        self.assertEqual(shaky, set())
        self.assertTrue(all(r["correct"] for r in results))

    def test_all_wrong_marks_every_concept_shaky(self):
        answers = {q["id"]: (q["answer"] + 1) % len(q["choices"]) for q in self.quiz}
        shaky, results = ge.score_quiz(self.quiz, answers)
        expected = {q["concept"] for q in self.quiz}
        self.assertEqual(shaky, expected)
        self.assertTrue(all(not r["correct"] for r in results))

    def test_missing_answer_counts_as_wrong(self):
        shaky, results = ge.score_quiz(self.quiz, {})
        self.assertEqual(len(shaky), len({q["concept"] for q in self.quiz}))

    def test_quiz_has_12_questions_across_multiple_clusters(self):
        self.assertEqual(len(self.quiz), 12)
        nodes = ge.load_graph()
        clusters = {nodes[q["concept"]]["cluster"] for q in self.quiz}
        self.assertGreaterEqual(len(clusters), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
