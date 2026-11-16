"""Generate the interim report from report/ara_rapor.json using IEEEtran.

python build_report.py --project-root . --tectonic PATH/tectonic.exe
Without --tectonic, write the LaTeX and Markdown sources only.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


AUTHOR = 'Gökhan Kartal'
STUDENT_NUMBER = '2645007017'
SEED = 7017
REPOSITORY = 'https://github.com/gkhankartal/veri-madenciligi-pazar-sepeti'
TITLE = 'Pazar Sepeti Analizi: Veri, Yöntem Planı ve İlk Bulgular'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def synchronize_measured_tables(project_root, sections):
    """Refresh measured table cells while preserving narrative text and headers."""
    mining = json.loads((project_root/'results/mining.json').read_text(encoding='utf-8'))
    classification = json.loads((project_root/'results/cart.json').read_text(encoding='utf-8'))
    timing_rows = {row['algorithm']: row for row in mining['timings']
                   if abs(row['min_support'] - 0.02) < 1e-12}
    changed = False
    refreshed = set()
    for section in sections:
        for block in section['blocks']:
            if block['kind'] != 'table':
                continue
            headers = block['headers']
            if headers[:3] == ['Yöntem', 'Destek', 'Sık küme'] and len(headers) == 4:
                rows = []
                for existing in block['rows']:
                    measurement = timing_rows[existing[0]]
                    rows.append([existing[0], f"%{measurement['min_support']*100:.2f}",
                                 str(measurement['frequent_itemsets']),
                                 f"{measurement['mean_seconds']:.3f} ± {measurement['sample_std_seconds']:.3f}"])
                refreshed.add('runtime')
            elif headers == ['Model', 'Test F1', 'Precision', 'Recall']:
                models = {'CART': classification['cart']['test'],
                          'Çoğunluk': classification['baseline_test']}
                rows = [[existing[0]]+[f'{models[existing[0]][metric]:.3f}'
                                      for metric in ['f1', 'precision', 'recall']]
                        for existing in block['rows']]
                refreshed.add('classification')
            else:
                continue
            if rows != block['rows']:
                block['rows'] = rows
                changed = True
    if refreshed != {'runtime', 'classification'}:
        raise ValueError('The report must include runtime and classification result tables')
    return changed


def tex(value):
    replacements = {
        '\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
        '#': r'\#', '_': r'\_\allowbreak{}', '{': r'\{', '}': r'\}',
        '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
        '≥': r'$\geq$', '≤': r'$\leq$', '→': r'$\rightarrow$',
        '⇒': r'$\Rightarrow$', '∞': r'$\infty$', '±': r'$\pm$',
        '×': r'$\times$', '⁻': r'$^{-}$', '₂': r'$_2$', '₁': r'$_1$',
        '∪': r'$\cup$', '∩': r'$\cap$', '∅': r'$\emptyset$', '∈': r'$\in$',
        '−': '-', '\u2011': '-', '\u2013': '-', '\u2014': '-',
    }
    return ''.join(replacements.get(character, character) for character in str(value))


def table_tex(block):
    headers = block['headers']
    specification = '|'.join(r'>{\raggedright\arraybackslash}X' for _ in headers)
    lines = [r'\begin{table}[!ht]', r'\centering\footnotesize',
             r'\setlength{\tabcolsep}{3pt}', r'\renewcommand{\arraystretch}{1.15}',
             r'\begin{tabularx}{\columnwidth}{'+specification+'}', r'\hline',
             ' & '.join(r'\textbf{'+tex(value)+'}' for value in headers)+r' \\ \hline']
    for row in block['rows']:
        if len(row) != len(headers):
            raise ValueError('The table row length differs from the header length')
        lines.append(' & '.join(tex(value) for value in row)+r' \\')
    return '\n'.join(lines+[r'\hline', r'\end{tabularx}', r'\end{table}'])


def report_parts(sections):
    first = sections[0]['blocks']
    if first[0].get('text') != 'Özet' or first[1]['kind'] != 'p':
        raise ValueError('The first section must begin with the abstract')
    abstract = first[1]['text']
    if len(abstract.split()) > 150:
        raise ValueError('The abstract exceeds 150 words')
    keywords = first[2]['text'].split(':', 1)[1].strip()
    if not any(section['title'] == 'Kaynakça' for section in sections):
        raise ValueError('The report has no references section')
    return abstract, keywords


def write_sources(project_root, sections):
    report = project_root/'report'
    abstract, keywords = report_parts(sections)
    lines = [r'\documentclass[conference,a4paper]{IEEEtran}',
             '% IEEEtran.cls: CTAN, version 1.8b; original license retained.',
             r'\usepackage{fontspec}',
             r'\setmainfont{texgyretermes-regular.otf}[BoldFont=texgyretermes-bold.otf,ItalicFont=texgyretermes-italic.otf,BoldItalicFont=texgyretermes-bolditalic.otf]',
             r'\usepackage[turkish,shorthands=off]{babel}',
             r'\usepackage{graphicx,tabularx,array,amsmath,url}',
             r'\usepackage[hidelinks]{hyperref}', r'\usepackage{placeins}',
             r'\graphicspath{{../results/figures/}}', r'\urlstyle{same}',
             r'\begin{document}', r'\title{'+tex(TITLE)+'}',
             r'\author{\IEEEauthorblockN{'+tex(AUTHOR)+r'}\IEEEauthorblockA{Öğrenci No: '+STUDENT_NUMBER+
             r'\\SEED: '+str(SEED)+r'\\Veri Madenciliği Dönem Projesi - Ara Rapor\\16 Kasım 2026}}',
             r'\maketitle', r'{\small\raggedright\noindent\textbf{Kod deposu:} \url{'+REPOSITORY+r'}\par}',
             r'\begin{abstract}', tex(abstract), r'\end{abstract}',
             r'\begin{IEEEkeywords}', tex(keywords), r'\end{IEEEkeywords}']
    markdown = ['# '+TITLE, '', AUTHOR, '',
                f'Öğrenci No: {STUDENT_NUMBER} | SEED: {SEED} | 16 Kasım 2026', '',
                '[Kod deposu]('+REPOSITORY+')', '', '## Özet', '', abstract, '',
                '**Anahtar kelimeler:** '+keywords, '']
    figure_hashes = {}
    for section_index, section in enumerate(sections):
        heading = re.sub(r'^\d+\.\s*', '', section['title'])
        references = heading == 'Kaynakça'
        if references:
            lines += [r'\clearpage', r'\label{content-end}', r'\section*{Kaynakça}',
                      r'\label{references-start}']
        else:
            lines.append(r'\section{'+tex(heading)+'}')
        markdown.extend(['## '+heading, ''])
        for block_index, block in enumerate(section['blocks']):
            if section_index == 0 and block_index < 3:
                continue
            kind = block['kind']
            if kind == 'h':
                lines.append(r'\subsection{'+tex(block['text'])+'}')
                markdown.extend(['### '+block['text'], ''])
            elif kind == 'p':
                lines.extend([tex(block['text']), ''])
                markdown.extend([block['text'], ''])
            elif kind == 'table':
                lines.append(table_tex(block))
                markdown.extend(['| '+' | '.join(str(v) for v in block['headers'])+' |',
                                 '| '+' | '.join('---' for _ in block['headers'])+' |'])
                markdown.extend('| '+' | '.join(str(v) for v in row)+' |' for row in block['rows'])
                markdown.append('')
            elif kind == 'figure':
                filename = block['file']
                image = project_root/'results/figures'/filename
                if not image.is_file():
                    raise FileNotFoundError(image)
                figure_hashes[filename] = digest(image)
                caption = re.sub(r'^Şekil\s+\d+\.\s*', '', block['caption'])
                lines += [r'\begin{figure}[!ht]', r'\centering',
                          r'\includegraphics[width=\columnwidth,height=0.30\textheight,keepaspectratio]{'+filename+'}',
                          r'\caption{'+tex(caption)+'}', r'\end{figure}']
                markdown.extend(['!['+caption+'](../results/figures/'+filename+')', ''])
            elif kind == 'link':
                url = block['url']
                lines += [r'\noindent\url{'+url.replace('%', r'\%')+'}', r'\par']
                markdown.extend(['['+block.get('text', url)+']('+url+')', ''])
            else:
                raise ValueError('Unknown block kind: '+kind)
    lines.append(r'\end{document}')
    (report/'ara_rapor.tex').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (report/'ara_rapor.md').write_text('\n'.join(markdown)+'\n', encoding='utf-8')
    figure_manifest = json.dumps(dict(sorted(figure_hashes.items())), ensure_ascii=False, sort_keys=True)
    return {
        '/ReportSourceSHA256': digest(report/'ara_rapor.json'),
        '/ReportTexSHA256': digest(report/'ara_rapor.tex'),
        '/ReportClassSHA256': digest(report/'IEEEtran.cls'),
        '/ReportFiguresSHA256': hashlib.sha256(figure_manifest.encode('utf-8')).hexdigest(),
    }


def compile_report(project_root, executable, hashes):
    report = project_root/'report'
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise FileNotFoundError(executable)
    subprocess.run([str(executable), '--keep-logs', 'ara_rapor.tex'], cwd=report, check=True)
    from pypdf import PdfReader, PdfWriter
    pdf = report/'ara_rapor.pdf'
    reader = PdfReader(pdf)
    reference_pages = [index for index, page in enumerate(reader.pages)
                       if re.search(r'(?im)^\s*KAYNAKÇA\s*$', page.extract_text() or '')]
    if len(reference_pages) != 1 or not 1 <= reference_pages[0] <= 6:
        raise ValueError('The references boundary or the six-page content limit is invalid')
    first_page = reader.pages[0].extract_text() or ''
    for required in [AUTHOR, STUDENT_NUMBER, str(SEED)]:
        if required not in first_page:
            raise ValueError('Missing first-page identity field: '+required)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.add_metadata({**hashes, '/Author': AUTHOR, '/Title': TITLE,
                         '/Creator': 'build_report.py', '/ReportSourceFile': 'ara_rapor.json'})
    temporary = report/'ara_rapor.build.pdf'
    with temporary.open('wb') as stream:
        writer.write(stream)
    reader.close()
    writer.close()
    temporary.replace(pdf)
    verified = PdfReader(pdf)
    if not all(verified.metadata.get(key) == value for key, value in hashes.items()):
        raise ValueError('PDF source fingerprints differ from the current inputs')
    result = dict(total_pages=len(verified.pages), content_pages=reference_pages[0],
                  references_pages=len(verified.pages)-reference_pages[0], source_fingerprints_verified=True)
    verified.close()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', default=str(Path(__file__).resolve().parent))
    parser.add_argument('--tectonic', help='Path to the Tectonic executable; omit to generate sources only')
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()
    source = project_root/'report/ara_rapor.json'
    sections = json.loads(source.read_text(encoding='utf-8'))
    if synchronize_measured_tables(project_root, sections):
        source.write_text(json.dumps(sections, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    hashes = write_sources(project_root, sections)
    if args.tectonic:
        print(json.dumps(compile_report(project_root, args.tectonic, hashes), ensure_ascii=False))
    else:
        print('Generated report/ara_rapor.tex and report/ara_rapor.md; PDF compilation was not requested.')


if __name__ == '__main__':
    main()
