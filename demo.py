"""Small training-only live-coding exercise; does not overwrite final experiment results."""
import argparse
import json
import math
import time
from pathlib import Path
from run_experiments import SEED,cache_policy,chronological_split,eclat,rules_from_counts


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache',default='work/clean_50000_raw_invoices.json')
    parser.add_argument('--support',type=float,default=.02)
    parser.add_argument('--confidence',type=float,default=.4)
    parser.add_argument('--lift',type=float,default=1)
    parser.add_argument('--max-len',type=int,default=3)
    args=parser.parse_args()
    if not 0<args.support<=1 or not 0<=args.confidence<=1 or args.max_len<1:
        parser.error('support must be in (0,1], confidence in [0,1], max-len >= 1')
    data=json.loads(Path(args.cache).read_text(encoding='utf-8'))
    if data.get('cache_policy')!=cache_policy():
        raise ValueError('Cache policy/SEED differs; regenerate with run_all.py first')
    train,_,_=chronological_split(data['baskets'])
    transactions=[set(row['products']) for row in train]
    start=time.perf_counter()
    counts=eclat(transactions,args.support,args.max_len)
    rules=[r for r in rules_from_counts(counts,len(train)) if r['confidence']>=args.confidence and r['lift']>args.lift]
    rules.sort(key=lambda r:(-r['lift'],-r['support'],r['antecedent'],r['consequent']))
    print(f'SEED={SEED}; training invoices={len(train)}; minimum count={math.ceil(args.support*len(train))}')
    print(f'Frequent itemsets={len(counts)}; rules={len(rules)}; elapsed seconds={time.perf_counter()-start:.3f}')
    for rule in rules[:5]:
        print(' + '.join(rule['antecedent']),'->',' + '.join(rule['consequent']),
              f"support={rule['support']:.4f}, confidence={rule['confidence']:.4f}, lift={rule['lift']:.3f}")


if __name__=='__main__':
    main()
