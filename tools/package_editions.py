"""Split editions on the website's six parts, preserving printed page labels."""
from pathlib import Path
import json,zipfile,hashlib
import pymupdf as fitz

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'editions'
report=json.loads((ROOT/'build/quality-report.json').read_text())
parts=[(1,7,'The-Request-Path'),(8,14,'State-and-Machinery'),(15,20,'Running-in-Production'),(21,24,'Distribution-and-Scale'),(25,26,'OpenAPI-and-AI-Agents'),(27,27,'System-Design')]
lines=['# Backend from First Principles — print editions','',
 'Original content by DsThakurRawat and repository contributors.',
 'Source: https://backend-from-first-principle.vercel.app/',
 'Repository: https://github.com/DsThakurRawat/Backend-from-first-Principle','',
 '## Printing','',
 '- Select A4 paper, 100% / Actual size, and automatic orientation.',
 '- For two-sided printing, use long-edge binding. Preview the mixed portrait/landscape pages in your print dialog.',
 '- Text, tables and code listings use black ink. Colour is retained in the original diagrams.',
 '- Print one edition. The Go and Python books contain the same teaching text.',
 '- Each language edition has all 27 chapters, 243 vector diagrams, 126 tables, 313 code blocks, and 434 bookmarks.',
 '- Where the source offers language tabs, each edition selects that language, including language-specific Dockerfiles and deployment configuration. SQL and shared examples remain. Standalone examples explaining another runtime remain labelled with their source language.',
 '- Dense wide diagrams occupy separate landscape pages for readability.','',
 '## Full editions and smaller printing batches','']
for lang,name in [('go','Go'),('python','Python')]:
    r=report[lang]
    assert not r['missing_internal_targets'] and not r['margin_overflow']
    original=OUT/r['file']; doc=fitz.open(original)
    # Retain a word space in the outline even for exports whose section number
    # was separated from its heading by a typographic margin rather than text.
    toc=doc.get_toc(); chapter=section_number=0; changed=False
    for entry in toc:
        if entry[0]==1: chapter+=1; section_number=0
        elif entry[0]==2:
            section_number+=1; prefix=f'{chapter}.{section_number}'
            if entry[1].startswith(prefix) and not entry[1][len(prefix):].startswith(' '):
                entry[1]=prefix+' '+entry[1][len(prefix):].lstrip(); changed=True
    if changed:
        doc.set_toc(toc,collapse=1); doc.saveIncr(); doc.close(); doc=fitz.open(original)
    folder=OUT/f'{name}-printing-parts'; folder.mkdir(exist_ok=True)
    chapters=r['chapters']; starts={c['chapter']:c['page'] for c in chapters}
    lines.extend([f'### {name} edition — {len(doc)} pages', '',f'Full book: `{original.name}`','', '| Part | Chapters | Printed pages | PDF pages |','| --- | --- | --- | --- |'])
    part_files=[]
    for n,(first,last,title) in enumerate(parts,1):
        start=1 if n==1 else starts[first]
        end=starts[last+1]-1 if last<27 else len(doc)
        target=folder/f'{n:02d}-{title}-{name}.pdf'
        section=fitz.open(); section.insert_pdf(doc,from_page=start-1,to_page=end-1,links=True,annots=True)
        section.set_metadata({'title':f'Backend from First Principles — {name} — Part {n}: {title.replace("-"," ")}', 'author':'DsThakurRawat and contributors', 'subject':f'Chapters {first}–{last}. Original printed pages {start}–{end}.'})
        bookmarks=[[level,t,p-start+1] for level,t,p in doc.get_toc() if start<=p<=end]
        if bookmarks: section.set_toc(bookmarks)
        section.set_page_labels([{'startpage':0,'prefix':'','style':'D','firstpagenum':start}])
        section.save(target,garbage=4,deflate=True)
        part_files.append(target)
        lines.append(f'| {n}. {title.replace("-"," ")} | {first}–{last} | {start}–{end} | {len(section)} |')
        section.close()
    guide=f'{name} printing batches\n\nThe six PDFs are in reading order. They preserve the full book\'s printed page numbers. Part 1 includes the cover, source note and complete contents.\n\nA4 paper; Actual size / 100%; automatic orientation; duplex long-edge binding.\n\nUse the full PDF for cross-part links and the complete navigation. Individual part files retain bookmarks for their own chapters; cross-part links may not be available.\n\nOriginal content: DsThakurRawat & contributors\nhttps://backend-from-first-principle.vercel.app/\n'
    (folder/'READ-ME.txt').write_text(guide)
    with zipfile.ZipFile(OUT/f'{name}-Print-in-Parts.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for p in part_files+[folder/'READ-ME.txt']: archive.write(p,arcname=f'{name}-printing-parts/{p.name}')
    doc[0].get_pixmap(matrix=fitz.Matrix(1,1),alpha=False).save(OUT/f'{name}-cover.png')
    lines.append('')
    print(f'{name}: full edition and six smaller printing parts packaged.')
lines.extend(['## Quality checks','',
 'All 27 chapters’ teaching prose and all selected code examples were checked against the repository’s rendered source. Diagram, table, section and code counts were checked. Every internal link target in the full books resolves. All pages were scanned for text outside the paper boundaries, and page samples from every chapter were visually reviewed.','',
 'The repository snapshot and rebuild instructions are recorded in the workspace `README.md`.'])
(OUT/'PRINTING-GUIDE.md').write_text('\n'.join(lines)+'\n')
checksums=[]
for p in sorted(OUT.glob('*.pdf'))+sorted(OUT.glob('*.zip')):
    checksums.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name)
(OUT/'SHA256SUMS.txt').write_text('\n'.join(checksums)+'\n')
