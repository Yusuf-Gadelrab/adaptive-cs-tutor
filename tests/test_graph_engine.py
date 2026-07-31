"""
Tests for graph_engine.py — no Ollama, no server, no network.
Run: uv run pytest
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


class TestLearningPath(unittest.TestCase):
    def setUp(self):
        self.nodes = ge.load_graph()
        self.dependents = ge.build_dependents(self.nodes)

    def test_empty_when_nothing_shaky(self):
        self.assertEqual(ge.learning_path(self.nodes, self.dependents, []), [])

    def test_covers_every_shaky_concept_exactly_once(self):
        shaky = ["recursion", "boolean_logic", "list_methods"]
        path = ge.learning_path(self.nodes, self.dependents, shaky)
        self.assertEqual(sorted(r["concept"] for r in path), sorted(shaky))

    def test_shallower_prerequisite_is_scheduled_first(self):
        # boolean_logic is an ancestor of recursion, so it must be repaired
        # first no matter what order it is passed in.
        path = ge.learning_path(self.nodes, self.dependents,
                                ["recursion", "boolean_logic"])
        order = [r["concept"] for r in path]
        self.assertLess(order.index("boolean_logic"), order.index("recursion"))

    def test_order_field_is_sequential_from_one(self):
        path = ge.learning_path(self.nodes, self.dependents,
                                ["recursion", "boolean_logic", "list_methods"])
        self.assertEqual([r["order"] for r in path], list(range(1, len(path) + 1)))

    def test_unlocks_excludes_other_shaky_nodes(self):
        path = ge.learning_path(self.nodes, self.dependents,
                                ["boolean_logic", "recursion"])
        row = next(r for r in path if r["concept"] == "boolean_logic")
        self.assertNotIn("recursion", row["unlocks"])

    def test_unlocks_matches_at_risk_set(self):
        shaky = ["boolean_logic"]
        path = ge.learning_path(self.nodes, self.dependents, shaky)
        states = ge.compute_states(self.nodes, self.dependents, shaky)
        at_risk = {n for n, s in states.items() if s == "at_risk"}
        self.assertEqual(set(path[0]["unlocks"]), at_risk)

    def test_ties_broken_deterministically(self):
        a = ge.learning_path(self.nodes, self.dependents, ["lists", "strings"])
        b = ge.learning_path(self.nodes, self.dependents, ["strings", "lists"])
        self.assertEqual([r["concept"] for r in a], [r["concept"] for r in b])

    def test_wider_blast_radius_wins_at_equal_depth(self):
        path = ge.learning_path(self.nodes, self.dependents, ["lists", "strings"])
        self.assertEqual(self.nodes["lists"]["prereqs"] and True, True)
        # both sit at the same depth; lists unblocks strictly more material
        depths = {r["concept"]: r["depth"] for r in path}
        self.assertEqual(depths["lists"], depths["strings"])
        self.assertEqual(path[0]["concept"], "lists")

    def test_unknown_concept_raises(self):
        with self.assertRaises(ValueError):
            ge.learning_path(self.nodes, self.dependents, ["nope"])


class TestQuizScoring(unittest.TestCase):
    def setUp(self):
        self.quiz = ge.load_quiz()

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

    def test_quiz_spans_every_cluster(self):
        nodes = ge.load_graph()
        self.assertGreaterEqual(len(self.quiz), 20)
        quiz_clusters = {nodes[q["concept"]]["cluster"] for q in self.quiz}
        all_clusters = {n["cluster"] for n in nodes.values()}
        self.assertEqual(quiz_clusters, all_clusters)

    def test_every_question_is_well_formed(self):
        nodes = ge.load_graph()
        seen = set()
        for q in self.quiz:
            self.assertNotIn(q["id"], seen, f"duplicate question id {q['id']}")
            seen.add(q["id"])
            self.assertIn(q["concept"], nodes, f"{q['id']} maps to unknown concept")
            self.assertGreaterEqual(len(q["choices"]), 2)
            self.assertIsInstance(q["answer"], int)
            self.assertTrue(0 <= q["answer"] < len(q["choices"]),
                            f"{q['id']} answer index out of range")
            self.assertEqual(len(set(q["choices"])), len(q["choices"]),
                             f"{q['id']} has duplicate choices")
            self.assertTrue(q["prompt"].strip())

    def test_answer_key_is_not_a_constant_index(self):
        # a quiz where the answer is always index 1 is guessable
        indices = {q["answer"] for q in self.quiz}
        self.assertGreater(len(indices), 1)

    def test_partial_answers_only_mark_the_missed_concepts(self):
        answers = {q["id"]: q["answer"] for q in self.quiz}
        target = self.quiz[3]
        answers[target["id"]] = (target["answer"] + 1) % len(target["choices"])
        shaky, _ = ge.score_quiz(self.quiz, answers)
        self.assertEqual(shaky, {target["concept"]})


class TestEndToEnd(unittest.TestCase):
    """The exact pipeline the demo runs, without any model involvement."""

    def test_quiz_to_states_to_path(self):
        nodes = ge.load_graph()
        dependents = ge.build_dependents(nodes)
        quiz = ge.load_quiz()
        wrong = {"q2", "q9", "q18"}
        answers = {
            q["id"]: ((q["answer"] + 1) % len(q["choices"])) if q["id"] in wrong
            else q["answer"]
            for q in quiz
        }
        shaky, results = ge.score_quiz(quiz, answers)
        self.assertEqual(len(shaky), 3)
        self.assertEqual(sum(1 for r in results if not r["correct"]), 3)

        states = ge.compute_states(nodes, dependents, shaky)
        self.assertEqual(sum(1 for s in states.values() if s == "shaky"), 3)
        self.assertGreater(sum(1 for s in states.values() if s == "at_risk"), 0)
        self.assertEqual(len(states), len(nodes))

        path = ge.learning_path(nodes, dependents, shaky)
        self.assertEqual(len(path), 3)
        # the foundational gap must be first
        self.assertEqual(path[0]["concept"], "boolean_logic")

    def test_states_partition_every_node(self):
        nodes = ge.load_graph()
        dependents = ge.build_dependents(nodes)
        states = ge.compute_states(nodes, dependents, ["variables"])
        self.assertEqual(set(states), set(nodes))
        self.assertTrue(all(s in ("ok", "shaky", "at_risk") for s in states.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
