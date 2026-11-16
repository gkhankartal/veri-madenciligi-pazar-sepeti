"""Download UCI Online Retail II from the official dataset link (CC BY 4.0)."""
import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

DATASET_URL = 'https://archive.ics.uci.edu/dataset/502/online+retail+ii'
ZIP_URL = 'https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip'


def extract_workbook(archive, destination):
    """Extract a single expected workbook, never archive-supplied filesystem paths."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        members = [i for i in bundle.infolist() if Path(i.filename).name.lower()=='online_retail_ii.xlsx']
        if len(members)!=1:
            raise ValueError('Expected exactly one online_retail_II.xlsx in UCI archive')
        staged = destination.with_suffix('.xlsx.part')
        try:
            with bundle.open(members[0]) as source, staged.open('wb') as target:
                shutil.copyfileobj(source,target)
            staged.replace(destination)
        finally:
            if staged.exists():
                staged.unlink()
    return destination


def download(destination):
    destination = Path(destination)
    if destination.exists():
        return destination
    destination.parent.mkdir(parents=True,exist_ok=True)
    request = urllib.request.Request(ZIP_URL,headers={'User-Agent':'MarketBasketAcademicProject/1.0'})
    with tempfile.TemporaryFile() as archive:
        with urllib.request.urlopen(request,timeout=120) as response:
            shutil.copyfileobj(response,archive)
        archive.seek(0)
        extract_workbook(archive,destination)
    manifest = dict(dataset=DATASET_URL,download=ZIP_URL,doi='10.24432/C5CG6D',license='CC BY 4.0',
                    sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
    destination.with_suffix('.source.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return destination


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination',default='data/online_retail_II.xlsx')
    args = parser.parse_args()
    print(download(args.destination))
