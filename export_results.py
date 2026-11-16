"""Export aggregate, human-readable result tables without original transaction data."""
import argparse
import csv
import json
from pathlib import Path


def table(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project-root',default=str(Path(__file__).resolve().parent))
    root=Path(parser.parse_args().project_root)
    result=root/'results'
    mining=json.loads((result/'mining.json').read_text(encoding='utf-8'))
    cart=json.loads((result/'cart.json').read_text(encoding='utf-8'))
    category=json.loads((root/'category_map.json').read_text(encoding='utf-8'))['items']
    rows=[]
    for i,rule in enumerate(mining['rules']):
        row=dict(antecedent=' + '.join(rule['antecedent']),consequent=' + '.join(rule['consequent']),
                 antecedent_description=' + '.join(mining['product_descriptions'].get(v,v) for v in rule['antecedent']),
                 consequent_description=' + '.join(mining['product_descriptions'].get(v,v) for v in rule['consequent']),
                 antecedent_category=' + '.join(category.get(v,{}).get('category','unknown') for v in rule['antecedent']),
                 consequent_category=' + '.join(category.get(v,{}).get('category','unknown') for v in rule['consequent']))
        for key in ['support','confidence','lift','conviction','conviction_infinite','joint_count']:
            row['train_'+key]=rule[key]
        for stage in ['validation','test']:
            evaluated=mining[stage][i]
            assert evaluated['antecedent']==rule['antecedent'] and evaluated['consequent']==rule['consequent']
            for key in ['support','confidence','lift','antecedent_count','joint_count']:
                row[stage+'_'+key]=evaluated[key]
        rows.append(row)
    table(result/'association_rules.csv',rows)
    table(result/'runtime_comparison.csv',[{k:v for k,v in r.items() if k!='seconds'} for r in mining['timings']])
    table(result/'threshold_sweep.csv',mining['threshold_sweep'])
    table(result/'cart_parameter_search.csv',[dict(**r['params'],validation_f1=r['validation_f1']) for r in cart['grid']])
    table(result/'cart_metrics.csv',[dict(model='CART',stage=stage,**{k:v for k,v in values.items() if k!='confusion_matrix'}) for stage,values in cart['cart'].items()]+[dict(model='majority',stage='test',**{k:v for k,v in cart['baseline_test'].items() if k!='confusion_matrix'})])
    (result/'cart_tree.txt').write_text(cart['tree_text'],encoding='utf-8')
    print('Exported aggregate rule, timing, threshold and classification tables.')


if __name__=='__main__':
    main()
