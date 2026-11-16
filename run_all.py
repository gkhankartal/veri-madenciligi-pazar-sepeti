"""Regenerate experiment results and the interim report sources in one command."""
import argparse
import os
import subprocess
import sys
from pathlib import Path
from download_data import download


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',help='Existing workbook; otherwise download from UCI into data/')
    parser.add_argument('--cache',default=str(root/'work/clean_50000_raw_invoices.json'))
    parser.add_argument('--tectonic',help='Tectonic executable; compile the interim PDF after regenerating sources')
    args = parser.parse_args()
    source = Path(args.input).resolve() if args.input else download(root/'data/online_retail_II.xlsx')
    if not source.is_file():
        raise FileNotFoundError(source)
    cache = Path(args.cache).resolve()
    results = root/'results'
    environment = dict(os.environ)
    environment.setdefault('MPLCONFIGDIR',str(root/'work/matplotlib'))
    commands = [
        [sys.executable,str(root/'run_experiments.py'),'--input',str(source),'--cache',str(cache),'--output',str(results)],
        [sys.executable,str(root/'extended_experiments.py'),'--cache',str(cache),'--results',str(results)],
        [sys.executable,str(root/'export_results.py'),'--project-root',str(root)],
    ]
    report_command=[sys.executable,str(root/'build_report.py'),'--project-root',str(root)]
    verification_command=[sys.executable,str(root/'verify_project.py'),'--project-root',str(root)]
    if args.tectonic:
        engine=Path(args.tectonic).resolve()
        if not engine.is_file():
            raise FileNotFoundError(engine)
        report_command += ['--tectonic',str(engine)]
    else:
        verification_command.append('--sources-only')
        print('Report sources will be regenerated; PDF compilation requires --tectonic.',flush=True)
    commands.extend([report_command,verification_command])
    for command in commands:
        print('Running:',Path(command[1]).name,flush=True)
        subprocess.run(command,cwd=root,env=environment,check=True)


if __name__=='__main__':
    main()
