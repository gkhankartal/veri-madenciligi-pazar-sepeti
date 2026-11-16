"""Independent checks of nontrivial extended-experiment logic."""
import unittest
import numpy as np
from extended_experiments import prune_redundant, weekly_table, moving_week_bootstrap, metrics_from_totals


class ExtendedTests(unittest.TestCase):
    def test_redundancy_requires_same_consequent_and_subset(self):
        simple=dict(antecedent=['A'],consequent=['B'],confidence=.8)
        redundant=dict(antecedent=['A','C'],consequent=['B'],confidence=.7)
        useful=dict(antecedent=['A','D'],consequent=['B'],confidence=.9)
        reciprocal=dict(antecedent=['B'],consequent=['A'],confidence=.7)
        kept,removed=prune_redundant([redundant,useful,reciprocal,simple])
        self.assertEqual(len(kept),3)
        self.assertEqual(removed[0]['rule'],redundant)
        self.assertIn(reciprocal,kept)

    def test_metrics_match_hand_counts(self):
        support,confidence,lift=metrics_from_totals(np.array([[10,5,4,3]]))
        self.assertAlmostEqual(support[0],.3)
        self.assertAlmostEqual(confidence[0],.6)
        self.assertAlmostEqual(lift[0],1.5)

    def test_calendar_gaps_and_degenerate_bootstrap(self):
        rule=dict(antecedent=['A'],consequent=['B'])
        rows=[dict(date='2020-01-06T00:00:00',products=['A','B']),dict(date='2020-01-20T00:00:00',products=['A','B'])]
        table=weekly_table(rows,[rule])
        self.assertEqual(table.shape,(3,1,4))
        self.assertEqual(table[1].sum(),0)
        result=moving_week_bootstrap(rows,[rule],repetitions=30,seed=7017)
        self.assertEqual(result['rules'][0]['confidence']['estimate'],1)
        self.assertEqual(result['rules'][0]['confidence']['percentile_95'],[1,1])
        self.assertEqual(result,moving_week_bootstrap(rows,[rule],repetitions=30,seed=7017))


if __name__=='__main__':
    unittest.main()
