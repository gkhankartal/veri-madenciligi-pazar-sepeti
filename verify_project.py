"""Check experiment consistency and the interim report against generated sources."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from pypdf import PdfReader


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def report_abstract(sections):
    for section in sections:
        following=False
        for block in section.get('blocks',[]):
            if block.get('kind')=='h':
                following=block.get('text','').strip().casefold() in {'özet','abstract'}
            elif following and block.get('kind')=='p':
                return block['text']
    raise ValueError('An abstract paragraph following the abstract heading is required')


def report_figure_hashes(root,sections):
    figures={}
    for section in sections:
        for block in section.get('blocks',[]):
            if block.get('kind')=='figure':
                filename=block['file']
                path=(root/'results/figures'/filename).resolve()
                path.relative_to(root.resolve())
                figures[filename]=sha256(path)
    return dict(sorted(figures.items()))


def verify(root,sources_only=False):
    root=Path(root).resolve()
    checks=[]
    def check(name,condition,detail):
        checks.append(dict(name=name,passed=bool(condition),detail=detail))
        if not condition:
            raise AssertionError(name+': '+str(detail))
    def read(relative):
        return json.loads((root/relative).read_text(encoding='utf-8'))
    audit=read('results/data_audit.json')
    mining=read('results/mining.json')
    cart=read('results/cart.json')
    extra=read('results/extended.json')
    literature=read('literature.json')
    sections=read('report/ara_rapor.json')
    sample=audit['sampling']
    check('seed',sample['seed']==7017 and mining['seed']==7017,dict(sampling=sample['seed'],mining=mining['seed']))
    check('invoice_sampling',sample['unit']=='invoice' and sample['sampled_invoices']==50000 and sample['population_invoices']==53628,dict(unit=sample['unit'],sampled=sample['sampled_invoices'],population=sample['population_invoices']))
    check('source_row_reconciliation',audit['audit']['source_raw_rows']==audit['audit']['raw_rows']+audit['audit']['outside_invoice_sample_rows'],audit['audit']['source_raw_rows'])
    check('cleaning_reconciliation',sum(audit['audit'].get(k,0) for k in ['cross_sheet_duplicates','missing_required_fields','cancelled_or_nonpositive','excluded_nonmerchandise_rows','retained_rows'])==audit['audit']['raw_rows'],audit['audit'])
    check('split_coverage',sum(x['invoices'] for x in audit['splits'].values())==sample['eligible_invoices_after_cleaning'],audit['splits'])
    check('date_boundaries',audit['splits']['train']['date_max']<audit['splits']['validation']['date_min'] and audit['splits']['validation']['date_max']<audit['splits']['test']['date_min'],audit['splits'])
    check('training_population',mining['training_baskets']==audit['splits']['train']['invoices'],mining['training_baskets'])
    check('algorithm_agreement',mining['algorithms_agree'] is True,mining['algorithms_agree'])
    check('benchmark_repetitions',len(mining['timings'])==9 and all(len(r['seconds'])==3 for r in mining['timings']),dict(settings=len(mining['timings']),repetitions=3))
    check('threshold_grid',len(mining['threshold_sweep'])==27,len(mining['threshold_sweep']))
    check('association_rule_count',len(mining['rules'])==61,len(mining['rules']))
    check('rule_metric_bounds',all(0<r['support']<=1 and 0<r['confidence']<=1 and r['lift']>1 for r in mining['rules']),len(mining['rules']))
    check('rule_evaluation_alignment',all(len(mining[stage])==len(mining['rules']) and all(a['antecedent']==b['antecedent'] and a['consequent']==b['consequent'] for a,b in zip(mining['rules'],mining[stage])) for stage in ['validation','test']),dict(validation=len(mining['validation']),test=len(mining['test'])))
    with (root/'results/association_rules.csv').open(encoding='utf-8-sig',newline='') as handle:
        rows=list(csv.DictReader(handle))
    check('exported_rule_count',len(rows)==len(mining['rules']),len(rows))
    check('exported_rule_metrics',all(abs(float(row['train_support'])-rule['support'])<1e-12 and abs(float(row['train_confidence'])-rule['confidence'])<1e-12 and abs(float(row['train_lift'])-rule['lift'])<1e-10 for row,rule in zip(rows,mining['rules'])),len(rows))
    check('target_excluded',cart['target'] not in cart['features'],cart['target'])
    check('cart_grid',len(cart['grid'])==24,len(cart['grid']))
    matrix=cart['cart']['test']['confusion_matrix']
    tn,fp=matrix[0]
    fn,tp=matrix[1]
    actual_f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0
    check('cart_test_reconciliation',tn+fp+fn+tp==audit['splits']['test']['invoices'] and abs(actual_f1-cart['cart']['test']['f1'])<1e-12,dict(confusion_matrix=matrix,f1=actual_f1))
    check('extended_same_source',extra['source_sha256']==audit['source_sha256'] and extra['sample_fingerprint']==sample['selected_invoice_sha256'],extra['sample_fingerprint'])
    check('literature_count',len(literature['papers'])>=5 and all(p['peer_reviewed'] and p['url'].startswith('https://') for p in literature['papers']),len(literature['papers']))
    check('data_license',literature['dataset']['uci_id']==502 and '4.0' in literature['dataset']['license'],literature['dataset']['license'])
    abstract=report_abstract(sections)
    word_count=len(abstract.split())
    check('abstract_word_limit',0<word_count<=150,word_count)
    figures=report_figure_hashes(root,sections)
    eda_stems={'01_missingness','02_basket_sizes','03_monthly_invoices','04_product_support','06_basket_boxplot','07_product_correlation','08_cart_class_balance'}
    eda={Path(path).stem for path in figures if Path(path).stem in eda_stems}
    check('report_eda_figures',len(eda)>=4,sorted(eda))
    text='\n'.join(str(block.get('text','')) for section in sections for block in section.get('blocks',[]))
    check('report_reference_links',all(p['url'] in text or (p.get('doi') and p['doi'] in text) for p in literature['papers']),[p['id'] for p in literature['papers']])
    tex_path=root/'report/ara_rapor.tex'
    tex=tex_path.read_text(encoding='utf-8')
    check('report_identity_source',all(value in tex for value in ['Gökhan Kartal','2645007017','7017']),dict(author='Gökhan Kartal',student_number='2645007017',seed=7017))
    check('ieee_class',bool(re.search(r'\\documentclass(?:\[[^\]]*\])?\{IEEEtran\}',tex)) and (root/'report/IEEEtran.cls').is_file(),sha256(root/'report/IEEEtran.cls'))
    check('report_rule_count_source',bool(re.search(r'\b61\b',text)),61)
    reported_counts=[sample['population_invoices'],sample['sampled_invoices'],sample['eligible_invoices_after_cleaning']]
    check('report_population_counts',all(any(form in text for form in [str(value),format(value,','),format(value,',').replace(',','.')]) for value in reported_counts),reported_counts)
    reported_f1=f'{actual_f1:.3f}'
    check('report_cart_f1',reported_f1 in text or reported_f1.replace('.',',') in text,reported_f1)
    for filename in ['README.md','requirements.txt','download_data.py','run_all.py','build_report.py','REFERENCES.bib','report/ara_rapor.md']:
        check('file_'+filename,(root/filename).is_file(),filename)
    expected={
        '/ReportSourceSHA256':sha256(root/'report/ara_rapor.json'),
        '/ReportTexSHA256':sha256(tex_path),
        '/ReportClassSHA256':sha256(root/'report/IEEEtran.cls'),
        '/ReportFiguresSHA256':hashlib.sha256(json.dumps(figures,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest(),
    }
    pdf_path=root/'report/ara_rapor.pdf'
    pdf_measurements=dict(exists=pdf_path.is_file(),current=False)
    if pdf_path.is_file():
        pdf=PdfReader(pdf_path)
        pages=len(pdf.pages)
        page_text=[page.extract_text() or '' for page in pdf.pages]
        reference_start=next((index for index,value in enumerate(page_text) if value.splitlines() and value.splitlines()[0].strip().casefold() in {'kaynakça','references'}),pages)
        matches={name:str(pdf.metadata.get(name,''))==value for name,value in expected.items()}
        current=all(matches.values())
        pdf_measurements.update(pages=pages,content_pages=reference_start,reference_pages=pages-reference_start,sha256=sha256(pdf_path),metadata_matches=matches,current=current)
        if not sources_only:
            check('report_pdf_matches_sources',current,matches)
            check('interim_page_limit',1<=reference_start<=6,dict(content_pages=reference_start,reference_pages=pages-reference_start,total_pages=pages))
            check('report_identity_pdf',all(value in page_text[0] for value in ['Gökhan Kartal','2645007017','7017']),dict(author='Gökhan Kartal',student_number='2645007017',seed=7017))
            check('report_pdf_rule_count',bool(re.search(r'\b61\b','\n'.join(page_text))),61)
    elif not sources_only:
        check('report_pdf_exists',False,str(pdf_path.relative_to(root)))
    output=dict(status='source_checks_passed' if sources_only else 'checks_passed',mode='sources' if sources_only else 'existing_pdf_and_sources',checks=checks,
                measurements=dict(abstract_words=word_count,eda_figures=len(eda),literature_sources=len(literature['papers']),association_rules=len(mining['rules']),pdf=pdf_measurements),report_source_hashes=expected)
    (root/'results/verification.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(checks)} checks passed; PDF source fingerprint current: {pdf_measurements["current"]}.')
    return output


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project-root',default=str(Path(__file__).resolve().parent))
    parser.add_argument('--sources-only',action='store_true',help='Validate regenerated sources without requiring PDF compilation')
    args=parser.parse_args()
    verify(args.project_root,args.sources_only)


if __name__=='__main__':
    main()
