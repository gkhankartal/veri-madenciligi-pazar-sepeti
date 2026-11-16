"""Create the interim submission archive from an explicit public file list."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from verify_project import verify


PUBLIC_FILES=(
    '.gitignore','README.md','JOURNAL.md','requirements.txt','REFERENCES.bib','SOURCES.md',
    'literature.json','category_map.json',
    'download_data.py','run_experiments.py','extended_experiments.py','make_figures.py',
    'export_results.py','run_all.py','build_report.py','verify_project.py','build_release.py',
    'test_experiments.py','test_extended.py','test_delivery.py','demo.py',
    'report/ara_rapor.json','report/ara_rapor.md','report/ara_rapor.tex',
    'report/ara_rapor.pdf','report/IEEEtran.cls',
    'results/data_audit.json','results/mining.json','results/cart.json',
    'results/extended.json','results/environment.json','results/requirements.txt',
    'results/association_rules.csv','results/runtime_comparison.csv','results/threshold_sweep.csv',
    'results/cart_parameter_search.csv','results/cart_metrics.csv','results/cart_tree.txt',
    'results/extended_summary.csv','results/verification.json',
)
FIGURE_STEMS=(
    '01_missingness','02_basket_sizes','03_monthly_invoices','04_product_support',
    '05_runtime','06_basket_boxplot','07_product_correlation','08_cart_class_balance',
    '09_cart_confusion','10_cart_roc','11_cart_pr','extended_ablation',
    'extended_length_sensitivity','extended_monthly_stability',
)
REQUIRED_FILES={
    'README.md','requirements.txt','download_data.py','run_all.py','build_report.py',
    'report/ara_rapor.json','report/ara_rapor.md','report/ara_rapor.tex',
    'report/ara_rapor.pdf','report/IEEEtran.cls','results/verification.json',
}


def build(root,destination):
    root=Path(root).resolve()
    destination=Path(destination).resolve()
    verify(root)
    allowed=list(PUBLIC_FILES)+[f'results/figures/{name}.{ext}' for name in FIGURE_STEMS for ext in ['png','jpeg']]
    missing=sorted(name for name in REQUIRED_FILES if not (root/name).is_file())
    if missing:
        raise FileNotFoundError(', '.join(missing))
    files=[]
    for relative in allowed:
        path=(root/relative).resolve()
        path.relative_to(root)
        if path.is_file():
            files.append((relative,path))
    manifest={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files}
    manifest_data=dict(files=manifest,report='report/ara_rapor.pdf')
    manifest_bytes=(json.dumps(manifest_data,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    (root/'release_manifest.json').write_bytes(manifest_bytes)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for relative,path in files:
            archive.write(path,'market-basket/'+relative)
        archive.writestr('market-basket/release_manifest.json',manifest_bytes)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        expected={'market-basket/'+name for name in manifest}|{'market-basket/release_manifest.json'}
        assert set(archive.namelist())==expected
        for relative,digest in manifest.items():
            assert hashlib.sha256(archive.read('market-basket/'+relative)).hexdigest()==digest
    print(f'Archive verified: {destination.name}; {len(files)+1} files; {destination.stat().st_size:,} bytes.')
    return destination


def main():
    root=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser()
    parser.add_argument('--project-root',default=str(root))
    parser.add_argument('--destination',default=str(root.parent/'market-basket-proje.zip'))
    args=parser.parse_args()
    build(args.project_root,args.destination)


if __name__=='__main__':
    main()
