"""Independent correctness checks: python -m unittest test_experiments -v."""
import math
import unittest
from unittest.mock import patch
from itertools import combinations
from run_experiments import chronological_split, eclat, evaluate_rules, rules_from_counts, sample_invoice_ids,cache_policy


class ExperimentTests(unittest.TestCase):
    def test_cache_identity_changes_with_seed_or_cleaning_policy(self):
        original = cache_policy()
        with patch('run_experiments.SEED',7018):
            self.assertNotEqual(cache_policy(),original)
        with patch('run_experiments.EXCLUDED',{'POST'}):
            self.assertNotEqual(cache_policy(),original)
        self.assertEqual(cache_policy(),original)

    def test_sampling_is_repeatable_distinct_and_rejects_insufficient_population(self):
        invoices = [str(i) for i in range(20)]
        selected = sample_invoice_ids(invoices,count=16)
        self.assertEqual(len(selected),16)
        self.assertEqual(len(set(selected)),16)
        self.assertEqual(selected,sample_invoice_ids(invoices+invoices,count=16))
        self.assertNotEqual(selected,sample_invoice_ids(invoices,count=16,seed=7018))
        with self.assertRaises(ValueError):
            sample_invoice_ids(invoices,count=21)

    def test_eclat_matches_brute_force_and_support_boundary(self):
        rows = [{'A','B','C'}, {'A','B'}, {'B','C'}, {'A'}, set()]
        for support in [0.2, 0.4, 0.41, 0.6, 1.0]:
            expected = {}
            for length in range(1,4):
                for values in combinations(['A','B','C'], length):
                    itemset = frozenset(values)
                    count = sum(itemset <= row for row in rows)
                    if count >= math.ceil(support*len(rows)-1e-10):
                        expected[itemset] = count
            self.assertEqual(eclat(rows,support,3),expected)

    def test_rules_include_joint_antecedents_and_correct_metrics(self):
        rows = [{'A','B','C'}, {'A','B','C'}, {'A','B'}, {'C'}]
        rules = rules_from_counts(eclat(rows,.25,3),len(rows))
        rule = next(r for r in rules if r['antecedent']==['A','B'] and r['consequent']==['C'])
        self.assertEqual(rule['support'], .5)
        self.assertAlmostEqual(rule['confidence'], 2/3)
        self.assertAlmostEqual(rule['lift'], 8/9)
        self.assertAlmostEqual(rule['conviction'], .75)
        undefined = evaluate_rules([rule],[{'Z'}])[0]
        self.assertIsNone(undefined['confidence'])
        self.assertIsNone(undefined['lift'])

    def test_calendar_day_split_keeps_invoices_disjoint(self):
        baskets = [{'invoice':str(i),'date':f'2010-01-{i//2+1:02d}T12:00:00','products':['A']} for i in range(20)]
        train, valid, test = chronological_split(baskets)
        self.assertEqual(len(train)+len(valid)+len(test),20)
        self.assertFalse({x['date'][:10] for x in train}&{x['date'][:10] for x in valid})
        self.assertFalse({x['invoice'] for x in train}&{x['invoice'] for x in test})


if __name__ == '__main__':
    unittest.main()
