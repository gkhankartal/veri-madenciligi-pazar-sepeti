"""Scientific plots from the local clean cache and aggregate experiment results."""
import argparse
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', required=True)
    parser.add_argument('--results', required=True)
    args = parser.parse_args()
    cache = json.loads(Path(args.cache).read_text(encoding='utf-8'))
    result = Path(args.results)
    audit = json.loads((result/'data_audit.json').read_text(encoding='utf-8'))
    mining = json.loads((result/'mining.json').read_text(encoding='utf-8'))
    sampling = audit.get('sampling')
    baskets = cache['baskets']
    if isinstance(sampling,dict):
        assert len(baskets) == sampling['eligible_invoices_after_cleaning']
    output = result/'figures'
    output.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    def save(fig, name):
        fig.tight_layout()
        fig.savefig(output/name,dpi=170)
        fig.savefig(output/Path(name).with_suffix('.jpeg'),dpi=170,pil_kwargs={'quality':95,'subsampling':0})
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(8,4.5))
    missing = audit['missing_after_overlap']
    denominator = audit['audit']['raw_rows']-audit['audit']['cross_sheet_duplicates']
    labels = sorted(missing)
    values = [100*missing[k]/denominator for k in labels]
    ax.barh(labels,values,color='#386a8c')
    ax.set(xlabel='Missing values (% of sampled rows after overlap removal)',title='Sampled-source missingness before transaction cleaning')
    for i,v in enumerate(values):
        ax.text(v+.15,i,f'{v:.2f}%',va='center')
    ax.set_xlim(0,max(values)*1.22)
    save(fig,'01_missingness.png')
    fig, ax = plt.subplots(figsize=(8,4.5))
    sizes = [len(b['products']) for b in baskets]
    ax.hist(sizes,bins=np.geomspace(1,max(sizes)+1,35),color='#386a8c')
    ax.set(xscale='log',xlabel='Distinct merchandise products per invoice (log scale)',ylabel='Invoices',title='Sampled basket sizes; single-item baskets retained')
    save(fig,'02_basket_sizes.png')
    fig, ax = plt.subplots(figsize=(10,4.5))
    months = Counter(b['date'][:7] for b in baskets)
    ordered = sorted(months)
    ax.bar(ordered,[months[m] for m in ordered],color='#386a8c')
    ax.tick_params(axis='x',rotation=65)
    ax.set(xlabel='Month (first and last months may be partial)',ylabel='Invoices',title='Sampled invoices by month; overlapping source rows removed')
    save(fig,'03_monthly_invoices.png')
    fig, ax = plt.subplots(figsize=(8,4.5))
    cutoff = audit['splits']['validation']['date_min'][:10]
    train = [b for b in baskets if b['date'][:10]<cutoff]
    assert len(train) == audit['splits']['train']['invoices']
    frequencies = Counter(item for b in train for item in b['products'])
    values = sorted((v/len(train) for v in frequencies.values()),reverse=True)
    ax.plot(range(1,len(values)+1),values,color='#386a8c')
    ax.axhline(.02,color='#a45437',linestyle='--',label='Initial minimum support 2%')
    ax.set(xscale='log',yscale='log',xlabel='Product rank (training invoice frequency)',ylabel='Training support',title='Product popularity and long tail (training only)')
    ax.legend()
    save(fig,'04_product_support.png')
    fig, ax = plt.subplots(figsize=(8,4.5))
    for name,marker,color in [('apriori','o','#386a8c'),('fpgrowth','s','#a45437'),('eclat','^','#52794f')]:
        rows = sorted((r for r in mining['timings'] if r['algorithm']==name),key=lambda r:r['min_support'])
        ax.errorbar([r['min_support'] for r in rows],[r['mean_seconds'] for r in rows],yerr=[r['sample_std_seconds'] for r in rows],marker=marker,color=color,capsize=4,label=name)
    ax.set(yscale='log',xlabel='Minimum support',ylabel='Seconds (mean +/- sample SD; 3 runs, log scale)',title='Initial runtime comparison; maximum itemset length = 3')
    ax.legend()
    save(fig,'05_runtime.png')
    fig, ax = plt.subplots(figsize=(8,4.5))
    ax.boxplot(sizes,orientation='horizontal',showfliers=True)
    ax.set(xscale='log',xlabel='Distinct products per sampled invoice (log scale)',
           title='Basket-size outliers; no automatic outlier deletion',yticks=[])
    save(fig,'06_basket_boxplot.png')
    top = sorted(frequencies,key=lambda item:(-frequencies[item],item))[:10]
    matrix = np.array([[item in b['products'] for item in top] for b in train],dtype=float)
    correlation = np.corrcoef(matrix,rowvar=False)
    fig, ax = plt.subplots(figsize=(8,7))
    image = ax.imshow(correlation,vmin=-1,vmax=1,cmap='RdBu_r')
    ax.set(xticks=range(len(top)),yticks=range(len(top)),xticklabels=top,yticklabels=top,
           title='Binary product-presence correlations (training only)')
    ax.tick_params(axis='x',rotation=65)
    fig.colorbar(image,ax=ax,label='Pearson / phi coefficient')
    save(fig,'07_product_correlation.png')
    cart_path = result/'cart.json'
    if cart_path.exists():
        cart = json.loads(cart_path.read_text(encoding='utf-8'))
        stages = ['train','validation','test']
        positive = [cart['target_prevalence'][stage]*100 for stage in stages]
        fig, ax = plt.subplots(figsize=(8,4.5))
        ax.bar(stages,positive,color='#386a8c',label='Target present')
        ax.bar(stages,[100-v for v in positive],bottom=positive,color='#c7c7c7',label='Target absent')
        ax.set(ylabel='Invoices (%)',title=f'Class balance for training-selected target {cart["target"]}')
        ax.legend(loc='center right')
        save(fig,'08_cart_class_balance.png')
        matrix = np.array(cart['cart']['test']['confusion_matrix'])
        fig, ax = plt.subplots(figsize=(6,5))
        image = ax.imshow(matrix,cmap='Blues')
        for row in range(2):
            for col in range(2):
                ax.text(col,row,str(matrix[row,col]),ha='center',va='center',
                        color='white' if matrix[row,col]>matrix.max()/2 else 'black',fontsize=16)
        ax.set(xticks=[0,1],yticks=[0,1],xticklabels=['Absent','Present'],yticklabels=['Absent','Present'],
               xlabel='Prediction',ylabel='Observed target',title='CART test confusion matrix')
        fig.colorbar(image,ax=ax,label='Invoices')
        save(fig,'09_cart_confusion.png')
        if 'test_curves' in cart:
            curves = cart['test_curves']
            fig, ax = plt.subplots(figsize=(7,5))
            ax.plot(curves['roc_fpr'],curves['roc_tpr'],color='#386a8c',label=f"CART AUC = {cart['cart']['test']['roc_auc']:.3f}")
            ax.plot([0,1],[0,1],color='#777777',linestyle='--',label='Majority baseline AUC = 0.500')
            ax.set(xlabel='False positive rate',ylabel='True positive rate',title='Held-out period ROC curve')
            ax.legend()
            save(fig,'10_cart_roc.png')
            fig, ax = plt.subplots(figsize=(7,5))
            ax.step(curves['pr_recall'],curves['pr_precision'],where='post',color='#386a8c',label=f"CART AP = {cart['cart']['test']['average_precision']:.3f}")
            ax.axhline(cart['target_prevalence']['test'],color='#777777',linestyle='--',label='Target prevalence / baseline AP')
            ax.set(xlabel='Recall',ylabel='Precision',title='Held-out period precision-recall curve',xlim=(0,1),ylim=(0,1.02))
            ax.legend()
            save(fig,'11_cart_pr.png')
    print('Saved EDA and runtime figures in PNG and JPEG:',output)


if __name__ == '__main__':
    main()
