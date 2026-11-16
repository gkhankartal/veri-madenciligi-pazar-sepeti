"""Additional train-defined sensitivity and temporal analyses.

python extended_experiments.py --cache work/clean_50000_raw_invoices.json --results results
No new external test set is claimed. Source fingerprint and sample fingerprint
bind these results to the main experiment. All resampling uses SEED=7017.
"""
import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from run_experiments import SEED, chronological_split, eclat, evaluate_rules, rules_from_counts, save


def key(rule):
    return (tuple(rule['antecedent']), tuple(rule['consequent']))


def policy(rules, confidence=0.4, lift=1.0):
    selected = [r for r in rules if r['confidence'] >= confidence and r['lift'] > lift]
    return sorted(selected, key=lambda r: (-r['lift'], -r['support'], key(r)))


def prune_redundant(rules, tolerance=1e-12):
    """A longer antecedent is redundant if a subset has equal/higher confidence.

    The consequent is identical. Opposite directions are NOT duplicates. The
    decision uses training metrics only; it is a concise presentation heuristic,
    not an assurance of equal future recommendation performance.
    """
    ordered = sorted(rules, key=lambda r: (len(r['antecedent']), key(r)))
    retained, removed = [], []
    for rule in ordered:
        dominator = next((other for other in retained
                          if other['consequent'] == rule['consequent']
                          and set(other['antecedent']) < set(rule['antecedent'])
                          and other['confidence'] + tolerance >= rule['confidence']), None)
        if dominator:
            removed.append(dict(rule=rule, dominated_by=dominator))
        else:
            retained.append(rule)
    return retained, removed


def weekly_table(rows, rules):
    weeks = defaultdict(lambda: np.zeros((len(rules), 4), dtype=np.int64))
    for basket in rows:
        date = datetime.fromisoformat(basket['date']).date()
        monday = (date - timedelta(days=date.weekday())).isoformat()
        products = set(basket['products'])
        for i, rule in enumerate(rules):
            a = set(rule['antecedent']) <= products
            b = set(rule['consequent']) <= products
            weeks[monday][i] += [1, int(a), int(b), int(a and b)]
    # Include zero-invoice weeks so the calendar spacing is not compressed.
    first = datetime.fromisoformat(min(weeks)).date()
    last = datetime.fromisoformat(max(weeks)).date()
    ordered = []
    while first <= last:
        ordered.append(weeks[first.isoformat()])
        first += timedelta(days=7)
    return np.array(ordered)


def metrics_from_totals(totals):
    n, a, b, joint = np.moveaxis(np.asarray(totals, dtype=float), -1, 0)
    with np.errstate(divide='ignore', invalid='ignore'):
        support = joint/n
        confidence = joint/a
        lift = joint*n/(a*b)
    return support, confidence, lift


def moving_week_bootstrap(rows, rules, repetitions=1000, block_weeks=4, seed=SEED):
    table = weekly_table(rows, rules)
    weeks = len(table)
    rng = np.random.default_rng(seed)
    values = {name: [] for name in ['support', 'confidence', 'lift']}
    for _ in range(repetitions):
        starts = rng.integers(0, weeks, size=math.ceil(weeks/block_weeks))
        indices = ((starts[:,None]+np.arange(block_weeks)) % weeks).ravel()[:weeks]
        totals = table[indices].sum(axis=0)
        for name, metric in zip(values, metrics_from_totals(totals)):
            values[name].append(metric)
    result = []
    point = metrics_from_totals(table.sum(axis=0))
    for index, rule in enumerate(rules):
        record = dict(antecedent=rule['antecedent'], consequent=rule['consequent'])
        for j, name in enumerate(values):
            distribution = np.array(values[name])[:,index]
            distribution = distribution[np.isfinite(distribution)]
            estimate = float(point[j][index])
            record[name] = dict(estimate=estimate if np.isfinite(estimate) else None,
                                percentile_95=[float(x) for x in np.percentile(distribution,[2.5,97.5])] if len(distribution) else None,
                                finite_replicates=len(distribution))
        result.append(record)
    return dict(weeks=weeks, block_weeks=block_weeks, repetitions=repetitions,
                method='circular moving-block bootstrap of weekly aggregate counts; 4 adjacent weeks per block',
                limitation='Sensitivity interval, not a causal or fully calibrated inferential guarantee. Blocks approximate temporal dependence; repeated-customer dependence is not explicitly modeled. Circular wrap joins period endpoints. Test was previously inspected.',
                rules=result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', required=True)
    parser.add_argument('--results', required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.cache).read_text(encoding='utf-8'))
    results = Path(args.results)
    main_result = json.loads((results/'mining.json').read_text(encoding='utf-8'))
    audit = json.loads((results/'data_audit.json').read_text(encoding='utf-8'))
    assert audit['source_sha256'] == data['sha256'], 'Source fingerprint mismatch'
    assert audit['sampling']['selected_invoice_sha256'] == data['sampling']['selected_invoice_sha256'], 'Sample fingerprint mismatch'
    train, valid, test = chronological_split(data['baskets'])
    assert len(train) == main_result['training_baskets']
    tx = [set(b['products']) for b in train]
    vtx = [set(b['products']) for b in valid]
    ttx = [set(b['products']) for b in test]
    base_rules = policy(rules_from_counts(eclat(tx,.02,3),len(tx)))
    assert {key(r) for r in base_rules} == {key(r) for r in main_result['rules']}
    sensitivity = []
    all_counts = {}
    for support in [.01,.02]:
        for length in [2,3,4]:
            start = perf_counter()
            counts = eclat(tx,support,length)
            all_counts[(support,length)] = counts
            selected = policy(rules_from_counts(counts,len(tx)))
            sensitivity.append(dict(min_support=support,max_len=length,itemsets=len(counts),
                                    itemsets_by_length=dict(Counter(len(items) for items in counts)),
                                    rules=len(selected),seconds=perf_counter()-start))
            print('Length/support sensitivity',sensitivity[-1],flush=True)
    n_remove = math.ceil(.01*len(train))
    largest_ids = {b['invoice'] for b in sorted(train,key=lambda b:(-len(b['products']),b['date'],b['invoice']))[:n_remove]}
    variants = [('baseline',train),('remove_single_product_baskets',[b for b in train if len(b['products'])>1]),
                ('remove_largest_one_percent_baskets',[b for b in train if b['invoice'] not in largest_ids])]
    baseline_keys = {key(r) for r in base_rules}
    ablations = []
    for name, rows in variants:
        rows_tx = [set(b['products']) for b in rows]
        rules = policy(rules_from_counts(eclat(rows_tx,.02,3),len(rows_tx)))
        ids = {key(r) for r in rules}
        evaluated = evaluate_rules(rules,vtx)
        eligible = [r for r in evaluated if r['antecedent_count']>=20]
        passes = [r for r in eligible if r['confidence']>=.4 and r['lift'] is not None and r['lift']>1]
        ablations.append(dict(variant=name,training_baskets=len(rows),removed_training_baskets=len(train)-len(rows),
                              training_rules=len(rules),baseline_rule_jaccard=len(ids & baseline_keys)/len(ids|baseline_keys) if ids|baseline_keys else 1,
                              validation_eligible_rules=len(eligible),validation_passing_rules=len(passes),
                              note='All original validation baskets retained; denominator changes only in altered training data. This is a sensitivity study, not selection of a final preprocessing policy.'))
    high_counts = eclat(tx,.10,3)
    high_rules = policy(rules_from_counts(high_counts,len(tx)))
    certainty_rules = policy(rules_from_counts(all_counts[(.02,3)],len(tx)),confidence=1.0)
    failed = [dict(name='Minimum support 10%',reason_tried='Prefer common, well-supported cross-sell patterns.',
                   actual=dict(itemsets=len(high_counts),rules=len(high_rules)),
                   outcome='No actionable cross-sell rules under this training-only threshold.' if not high_rules else 'Rules retained; this cannot be honestly classified as a complete failure.',
                   is_failed_for_cross_sell_objective=not bool(high_rules)),
              dict(name='Minimum confidence 100%',reason_tried='Seek perfectly reliable training associations.',
                   actual=dict(rules=len(certainty_rules)),
                   outcome='No rules survive; perfect training confidence is too restrictive at support >= 2%.' if not certainty_rules else 'Some rules survive; perfection on training is not proof of future reliability.',
                   is_failed_for_cross_sell_objective=not bool(certainty_rules))]
    relaxed = policy(rules_from_counts(all_counts[(.01,4)],len(tx)))
    retained, removed = prune_redundant(relaxed)
    selected = base_rules[:3]  # Training-only lift ranking, fixed before evaluating later periods.
    monthly = []
    grouped = defaultdict(list)
    for basket in data['baskets']:
        grouped[basket['date'][:7]].append(set(basket['products']))
    for month, rows in sorted(grouped.items()):
        values = evaluate_rules(selected,rows)
        for rule in values:
            monthly.append(dict(month=month,invoices=len(rows),**rule))
    temporal_summary = {}
    for name, rows in [('train',tx),('validation',vtx),('test',ttx)]:
        evaluated = evaluate_rules(base_rules,rows)
        enough = [r for r in evaluated if r['antecedent_count']>=20]
        passes = [r for r in enough if r['confidence']>=.4 and r['lift'] is not None and r['lift']>1]
        temporal_summary[name] = dict(invoices=len(rows),eligible_rules=len(enough),passing_rules=len(passes),
                                      evaluated_rules=len(evaluated),mean_confidence=float(np.mean([r['confidence'] for r in enough])),
                                      mean_lift=float(np.mean([r['lift'] for r in enough if r['lift'] is not None])))
    out = dict(seed=SEED,source_sha256=data['sha256'],sample_fingerprint=data['sampling']['selected_invoice_sha256'],
               protocol='All thresholds and variants are specified in code; training rules define later-period evaluation. No variant is selected using test metrics. Previously inspected test is an exploratory temporal check, not a new external holdout.',
               length_sensitivity=sensitivity,ablation=ablations,unsuccessful_experiments=failed,
               redundancy_filter=dict(min_support=.01,max_len=4,before=len(relaxed),after=len(retained),removed=len(removed),
                                      definition=prune_redundant.__doc__,examples=removed[:10]),
               temporal_summary=temporal_summary,monthly_selected_rules=monthly,
               bootstrap_validation=moving_week_bootstrap(valid,selected),bootstrap_test=moving_week_bootstrap(test,selected),
               selected_rule_basis='Top three training lift-ranked rules at support >= 2%, confidence >= 40%, lift > 1. Reciprocal directions retained.',
               metric_note='Algorithm itemsets are identical at matching settings: quality differences are not attributed to Apriori/FP-Growth/ECLAT. Runtime measurements are implementation and environment dependent.')
    save(results/'extended.json',out)
    csv_rows = [dict(section='length_sensitivity',**r) for r in sensitivity]+[dict(section='ablation',**r) for r in ablations]
    fields = sorted({field for row in csv_rows for field in row})
    with (results/'extended_summary.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer = csv.DictWriter(handle,fieldnames=fields)
        writer.writeheader(); writer.writerows(csv_rows)
    figures = results/'figures'
    figures.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    def figure_save(fig,name):
        fig.tight_layout()
        fig.savefig(figures/f'{name}.png',dpi=170)
        fig.savefig(figures/f'{name}.jpeg',dpi=170,pil_kwargs={'quality':95,'subsampling':0})
        plt.close(fig)
    fig,ax = plt.subplots(figsize=(8,4.5))
    ax.bar(['Baseline','Remove single-product','Remove largest 1%'],[r['training_rules'] for r in ablations],color='#386a8c')
    ax.set(ylabel='Training rules',title='Sensitivity to training basket removal; support >= 2%')
    figure_save(fig,'extended_ablation')
    fig,ax = plt.subplots(figsize=(10,4.8))
    for rule in selected:
        rows = [r for r in monthly if key(r)==key(rule)]
        ax.plot([r['month'] for r in rows],[r['confidence'] if r['antecedent_count']>=20 else np.nan for r in rows],marker='.',label=f'{"+".join(rule["antecedent"])} -> {"+".join(rule["consequent"])}')
    ax.axhline(.4,color='#777777',linestyle='--',label='Initial confidence threshold')
    ax.set(ylabel='Monthly confidence',title='Training-selected rules over time; months with <20 antecedents hidden',ylim=(0,1))
    ax.tick_params(axis='x',rotation=65); ax.legend(fontsize=8)
    figure_save(fig,'extended_monthly_stability')
    fig,ax = plt.subplots(figsize=(8,4.5))
    for support in [.01,.02]:
        rows=[r for r in sensitivity if r['min_support']==support]
        ax.plot([r['max_len'] for r in rows],[r['rules'] for r in rows],marker='o',label=f'Support {support:.0%}')
    ax.set(xticks=[2,3,4],xlabel='Maximum itemset length',ylabel='Rules',title='Rule count versus maximum itemset length; confidence >= 40%, lift > 1')
    ax.legend()
    figure_save(fig,'extended_length_sensitivity')
    print('Ablations',ablations,flush=True)
    print('Failed/limited experiments',failed,flush=True)
    print('Redundancy filter',len(relaxed),len(retained),flush=True)
    print('Saved',results/'extended.json',flush=True)


if __name__ == '__main__':
    main()
