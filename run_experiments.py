"""Reproducible market basket analysis. Library APIs: see SOURCES.md.

python run_experiments.py --input online_retail_II.xlsx --cache work/clean.json --output results
Raw basket cache must remain local and must not be committed.
"""
import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from mlxtend.frequent_patterns import apriori, fpgrowth
from sklearn.dummy import DummyClassifier
from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
                             confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score, roc_curve, precision_recall_curve)
from sklearn.tree import DecisionTreeClassifier, export_text
from scipy.sparse import csc_matrix

SEED = 7017
EXCLUDED = {'POST', 'DOT', 'M', 'BANK CHARGES', 'ADJUST', 'D', 'S', 'AMAZONFEE', 'B', 'PADS'}


def cache_policy():
    return dict(version=4,seed=SEED,raw_invoice_sample_size=50000,
                excluded_codes=sorted(EXCLUDED),sampling_order='source encounter order',
                duplicate_policy='cross-sheet multiset union; within-sheet multiplicity preserved')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def clean(source, cache):
    digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()
    if Path(cache).exists():
        result = json.loads(Path(cache).read_text(encoding='utf-8'))
        if result['sha256'] == digest and result.get('cache_policy') == cache_policy():
            return result
    # Assignment section 8.1: replace the generic 80% rule with 50,000
    # invoice identifiers, sampled BEFORE cancellations/cleaning are removed.
    inventory = Counter()
    inventory_workbook = load_workbook(source, read_only=True, data_only=True)
    for sheet in inventory_workbook:
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if row[0] is not None:
                inventory[str(row[0])] += 1
    inventory_workbook.close()
    selected_ids = sample_invoice_ids(list(inventory),count=50000,seed=SEED)
    selected_set = set(selected_ids)
    sample_metadata = dict(unit='invoice', requested_n=50000, seed=SEED,
                           stage='raw invoice identifiers before cleaning; all rows of each selected invoice retained',
                           population_invoices=len(inventory), sampled_invoices=len(selected_ids),
                           selected_source_rows=sum(inventory[i] for i in selected_ids),
                           method=f'pandas.Series.drop_duplicates source encounter order; sample(n=50000, random_state={SEED})',
                           selected_invoice_sha256=hashlib.sha256('\n'.join(selected_ids).encode('utf-8')).hexdigest(),
                           assignment_reference='PDF section 8.1, page 5; supersedes generic 80% sampling on page 1')
    print('Raw invoice selection:',sample_metadata,flush=True)
    workbook = load_workbook(source, read_only=True, data_only=True)
    previous = Counter()
    invoices = {}
    audit = Counter()
    descriptions = {}
    missing = Counter()
    excluded = Counter()
    for sheet in workbook:
        current = Counter()
        for row in sheet.iter_rows(min_row=2, values_only=True):
            audit['source_raw_rows'] += 1
            if row[0] is None or str(row[0]) not in selected_set:
                audit['outside_invoice_sample_rows'] += 1
                continue
            audit['raw_rows'] += 1
            current[row] += 1
            if current[row] <= previous[row]:
                audit['cross_sheet_duplicates'] += 1
                continue
            inv, sku, desc, qty, date, price, customer, country = row
            for name, value in zip(['Invoice', 'StockCode', 'Description', 'Quantity', 'InvoiceDate', 'Price', 'Customer ID', 'Country'], row):
                if value is None:
                    missing[name] += 1
            if inv is None or sku is None or qty is None or price is None or date is None:
                audit['missing_required_fields'] += 1
                continue
            if str(inv).upper().startswith('C') or qty <= 0 or price <= 0:
                audit['cancelled_or_nonpositive'] += 1
                continue
            sku = str(sku).strip()
            if sku.upper() in EXCLUDED:
                audit['excluded_nonmerchandise_rows'] += 1
                excluded[sku] += 1
                continue
            audit['retained_rows'] += 1
            iid = str(inv)
            if iid not in invoices:
                invoices[iid] = {'invoice': iid, 'date': date.isoformat(), 'products': set()}
            invoices[iid]['date'] = min(invoices[iid]['date'], date.isoformat())
            invoices[iid]['products'].add(sku)
            if desc:
                descriptions.setdefault(sku, str(desc).strip())
        previous |= current
    workbook.close()
    baskets = []
    for item in invoices.values():
        item['products'] = sorted(item['products'])
        baskets.append(item)
    baskets.sort(key=lambda b: (b['date'], b['invoice']))
    assert sum(audit[k] for k in ['cross_sheet_duplicates', 'missing_required_fields', 'cancelled_or_nonpositive', 'excluded_nonmerchandise_rows', 'retained_rows']) == audit['raw_rows']
    assert audit['raw_rows'] == sample_metadata['selected_source_rows']
    assert audit['source_raw_rows'] == audit['raw_rows']+audit['outside_invoice_sample_rows']
    sample_metadata['eligible_invoices_after_cleaning'] = len(baskets)
    result = dict(version=4, cache_policy=cache_policy(),sha256=digest, sampling=sample_metadata, audit=dict(audit), missing_after_overlap=dict(missing),
                  excluded_codes=dict(excluded), descriptions=descriptions, baskets=baskets)
    save(cache, result)
    return result


def chronological_split(baskets):
    # Calendar-day boundaries ensure an entire day and every invoice stay together.
    first = baskets[int(len(baskets)*0.6)]['date'][:10]
    second = baskets[int(len(baskets)*0.8)]['date'][:10]
    train = [b for b in baskets if b['date'][:10] < first]
    valid = [b for b in baskets if first <= b['date'][:10] < second]
    test = [b for b in baskets if b['date'][:10] >= second]
    assert max(b['date'] for b in train) < min(b['date'] for b in valid)
    assert max(b['date'] for b in valid) < min(b['date'] for b in test)
    assert len(train)+len(valid)+len(test) == len(baskets)
    return train, valid, test


def sample_invoice_ids(invoice_ids, count=50000, seed=SEED):
    """Sample distinct raw invoice IDs in source encounter order, without replacement.

    Insufficient population raises ValueError; never silently reduce n or replace
    missing invoices with duplicated baskets.
    """
    unique = pd.Series(invoice_ids, dtype='object').drop_duplicates()
    return unique.sample(n=count,random_state=seed,replace=False).tolist()


def eclat(transactions, support, max_len=3):
    minimum = math.ceil(support*len(transactions)-1e-10)
    vertical = defaultdict(set)
    for tid, transaction in enumerate(transactions):
        for item in transaction:
            vertical[item].add(tid)
    items = [(item, tids) for item, tids in sorted(vertical.items()) if len(tids)>=minimum]
    found = {}

    def visit(prefix, candidates):
        for index, (item, tids) in enumerate(candidates):
            new = prefix+(item,)
            found[frozenset(new)] = len(tids)
            if len(new) < max_len:
                following = []
                for other, other_tids in candidates[index+1:]:
                    overlap = tids & other_tids
                    if len(overlap) >= minimum:
                        following.append((other, overlap))
                visit(new, following)
    visit((), items)
    return found


def rules_from_counts(counts, n):
    result = []
    for items, joint in counts.items():
        if len(items) < 2:
            continue
        ordered = sorted(items)
        for length in range(1, len(items)):
            for left in combinations(ordered, length):
                a = frozenset(left)
                b = items-a
                confidence = joint/counts[a]
                consequent_support = counts[b]/n
                result.append(dict(antecedent=sorted(a), consequent=sorted(b),
                                   support=joint/n, confidence=confidence,
                                   lift=confidence/consequent_support,
                                   conviction=None if confidence == 1 else (1-consequent_support)/(1-confidence),
                                   conviction_infinite=confidence == 1,
                                   joint_count=joint))
    return result


def evaluate_rules(rules, transactions):
    index = defaultdict(set)
    for tid, row in enumerate(transactions):
        for item in row:
            index[item].add(tid)
    def tids(items):
        return set.intersection(*(index[item] for item in items))
    results = []
    for rule in rules:
        a, b = tids(rule['antecedent']), tids(rule['consequent'])
        both = len(a & b)
        confidence = both/len(a) if a else None
        lift = confidence/(len(b)/len(transactions)) if a and b else None
        results.append(dict(antecedent=rule['antecedent'], consequent=rule['consequent'],
                            antecedent_count=len(a), joint_count=both,
                            support=both/len(transactions), confidence=confidence, lift=lift))
    return results


def classifier(train, valid, test):
    counts = Counter(item for row in train for item in row)
    target = sorted(counts, key=lambda item: (-counts[item], item))[0]
    features = sorted(item for item, count in counts.items() if item != target and count >= 20)
    lookup = {item:index for index,item in enumerate(features)}
    def encode(rows):
        row_indices, column_indices = [], []
        for index,row in enumerate(rows):
            for item in sorted(row):
                if item in lookup:
                    row_indices.append(index)
                    column_indices.append(lookup[item])
        x = csc_matrix((np.ones(len(row_indices),dtype=np.float32),
                        (row_indices,column_indices)),shape=(len(rows),len(features)))
        return x, np.array([target in row for row in rows], dtype=np.uint8)
    xtrain, ytrain = encode(train)
    xvalid, yvalid = encode(valid)
    xtest, ytest = encode(test)
    assert target not in features
    best = None
    grid = []
    for depth in [3, 5, 8, None]:
        for leaf in [5, 20, 50]:
            for weight in [None, 'balanced']:
                params = dict(max_depth=depth, min_samples_leaf=leaf, class_weight=weight)
                model = DecisionTreeClassifier(**params, random_state=SEED).fit(xtrain, ytrain)
                pred = model.predict(xvalid)
                score = f1_score(yvalid, pred, zero_division=0)
                grid.append(dict(params=params, validation_f1=float(score)))
                print('CART validation',params,'F1',round(float(score),4),flush=True)
                if best is None or score > best[0]:
                    best = (score, params, model)
    # Preserve the train-only fit so train/validation/test metrics refer to the same model.
    model = best[2]
    baseline = DummyClassifier(strategy='most_frequent', random_state=SEED).fit(xtrain, ytrain)
    def metrics(estimator, x, y):
        pred = estimator.predict(x)
        probabilities = estimator.predict_proba(x)
        pos = list(estimator.classes_).index(1)
        p = probabilities[:, pos]
        return dict(f1=float(f1_score(y,pred,zero_division=0)),
                    precision=float(precision_score(y,pred,zero_division=0)),
                    recall=float(recall_score(y,pred,zero_division=0)),
                    balanced_accuracy=float(balanced_accuracy_score(y,pred)),
                    average_precision=float(average_precision_score(y,p)),
                    roc_auc=float(roc_auc_score(y,p)),
                    confusion_matrix=confusion_matrix(y,pred,labels=[0,1]).tolist())
    test_prediction = model.predict(xtest)
    test_probability = model.predict_proba(xtest)[:,list(model.classes_).index(1)]
    fpr,tpr,roc_thresholds = roc_curve(ytest,test_probability)
    precision,recall,pr_thresholds = precision_recall_curve(ytest,test_probability)
    rng = np.random.default_rng(SEED)
    bootstrap = []
    for _ in range(1000):
        indices = rng.integers(0,len(ytest),size=len(ytest))
        truth,pred = ytest[indices],test_prediction[indices]
        tp = int(np.sum((truth==1)&(pred==1)))
        fp = int(np.sum((truth==0)&(pred==1)))
        fn = int(np.sum((truth==1)&(pred==0)))
        bootstrap.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.0)
    error_profiles = {}
    for name,mask in [('false_positive',(ytest==0)&(test_prediction==1)),
                      ('false_negative',(ytest==1)&(test_prediction==0))]:
        counts = Counter(item for i,row in enumerate(test) if mask[i] for item in row if item!=target)
        error_profiles[name] = dict(invoices=int(mask.sum()),
            frequent_other_products=[dict(stockcode=item,invoices=count) for item,count in counts.most_common(10)])
    return dict(target=target, feature_count=len(features), features=features, best_params=best[1],
                selection_metric='validation F1; threshold 0.5; ties use first grid entry', grid=grid,
                target_prevalence=dict(train=float(ytrain.mean()), validation=float(yvalid.mean()), test=float(ytest.mean())),
                cart={name:metrics(model,x,y) for name,x,y in [('train',xtrain,ytrain),('validation',xvalid,yvalid),('test',xtest,ytest)]},
                baseline_test=metrics(baseline,xtest,ytest),
                test_curves=dict(roc_fpr=fpr.tolist(),roc_tpr=tpr.tolist(),
                                 pr_precision=precision.tolist(),pr_recall=recall.tolist()),
                test_f1_bootstrap=dict(seed=SEED,repetitions=1000,confidence_level=.95,
                    percentile_interval=np.quantile(bootstrap,[.025,.975]).tolist(),
                    assumption='IID invoice resampling conditional on the fixed fitted model; repeated customers and temporal dependence are not modeled; exploratory test already examined'),
                error_profiles=error_profiles,
                tree_text=export_text(model,feature_names=features, max_depth=8))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output)
    data = clean(args.input, args.cache)
    print('Cleaning complete:', data['audit'], flush=True)
    sampled = data['baskets']
    sample_metadata = data['sampling']
    print('Invoice sample:',sample_metadata,flush=True)
    train, valid, test = chronological_split(sampled)
    splits = {}
    for name, rows in [('train',train),('validation',valid),('test',test)]:
        splits[name] = dict(invoices=len(rows), date_min=rows[0]['date'], date_max=rows[-1]['date'])
    save(out/'data_audit.json', dict(seed=SEED, source_sha256=data['sha256'], audit=data['audit'],
         missing_after_overlap=data['missing_after_overlap'], excluded_codes=data['excluded_codes'], splits=splits,
         sampling=sample_metadata,
         special_code_exclusions='Predefined transaction/service code exclusions are listed in excluded_codes; basket-removal sensitivity is evaluated separately'))
    transactions = [set(b['products']) for b in train]
    valid_tx = [set(b['products']) for b in valid]
    test_tx = [set(b['products']) for b in test]
    freq = Counter(item for row in transactions for item in row)
    vocabulary = sorted(item for item,count in freq.items() if count/len(train)>=0.02)
    frame = pd.DataFrame(np.array([[item in row for item in vocabulary] for row in transactions], dtype=bool), columns=vocabulary)
    filtered = [row & set(vocabulary) for row in transactions]
    timings = []
    all_counts = {}
    rng = np.random.default_rng(SEED)
    for support in [0.02, 0.03, 0.05]:
        reference = None
        durations = defaultdict(list)
        for repetition in range(3):
            for name in rng.permutation(['apriori','fpgrowth','eclat']):
                start = time.perf_counter()
                if name == 'eclat':
                    counts = eclat(filtered,support,3)
                else:
                    function = apriori if name == 'apriori' else fpgrowth
                    options = dict(min_support=support, use_colnames=True, max_len=3)
                    if name == 'apriori':
                        options['low_memory'] = True
                    found = function(frame,**options)
                    counts = {frozenset(row.itemsets):round(row.support*len(train)) for row in found.itertuples()}
                duration = time.perf_counter()-start
                durations[name].append(duration)
                if reference is None:
                    reference = counts
                assert counts == reference, f'Algorithm mismatch: {name}, support {support}'
                print('Mining',support,repetition,name,len(counts),round(duration,3),flush=True)
        all_counts[support] = reference
        for name, values in durations.items():
            timings.append(dict(algorithm=name,min_support=support,max_len=3,
                                frequent_itemsets=len(reference),seconds=values,
                                mean_seconds=statistics.mean(values),sample_std_seconds=statistics.stdev(values)))
    sweep = []
    for support, counts in all_counts.items():
        rules = rules_from_counts(counts,len(train))
        for confidence in [0.2,0.4,0.6]:
            for lift in [1,2,3]:
                selected = [r for r in rules if r['confidence']>=confidence and r['lift']>lift]
                sweep.append(dict(min_support=support,min_confidence=confidence,min_lift_exclusive=lift,rules=len(selected)))
    # Predeclared first policy, not selected by looking at test results.
    selected = [r for r in rules_from_counts(all_counts[0.02],len(train)) if r['confidence']>=0.4 and r['lift']>1]
    selected.sort(key=lambda r:(-r['lift'],-r['support'],r['antecedent'],r['consequent']))
    save(out/'mining.json',dict(seed=SEED,training_baskets=len(train),vocabulary_size=len(vocabulary),
         max_len=3, algorithms_agree=True,benchmark_note='3 warm-process repetitions; input preparation excluded; Python result conversion included; not a memory benchmark',
         timings=timings,threshold_sweep=sweep,initial_policy='support >= .02, confidence >= .4, lift > 1; exploratory, not validation-optimized',
         rules=selected, validation=evaluate_rules(selected,valid_tx),test=evaluate_rules(selected,test_tx),
         product_descriptions={item:data['descriptions'].get(item) for item in vocabulary}))
    classification = classifier(transactions,valid_tx,test_tx)
    classification['target_description'] = data['descriptions'].get(classification['target'])
    save(out/'cart.json',classification)
    versions = {name:importlib.metadata.version(name) for name in ['numpy','pandas','openpyxl','mlxtend','scikit-learn','scipy','matplotlib']}
    save(out/'environment.json',dict(python=sys.version,platform=platform.platform(),packages=versions))
    (out/'requirements.txt').write_text('\n'.join(f'{name}=={version}' for name,version in versions.items())+'\n',encoding='utf-8')
    print('CART test:',classification['cart']['test'],flush=True)
    print('Baseline test:',classification['baseline_test'],flush=True)
    subprocess.run([sys.executable,str(Path(__file__).with_name('make_figures.py')),
                    '--cache',args.cache,'--results',str(out)],check=True)


if __name__ == '__main__':
    main()
