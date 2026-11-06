"""Content, navigation, boundary, and visual sampling checks for the print PDFs."""
from pathlib import Path
from bs4 import BeautifulSoup
from collections import Counter
from PIL import Image, ImageDraw
import pymupdf as fitz
import re,json,hashlib

ROOT=Path(__file__).resolve().parents[1]
def parse(x): return BeautifulSoup(x,'lxml')
def clean(a,book=False):
    for figure in a.select('figure.diagram'):
        for context in figure.select('.diagram-context'): figure.insert_before(context.extract())
    for el in list(a.select('pre, .code-bar, a.anchor, figure.diagram, .references, .section-number, .reference-mark, .code-label')):
        if el.parent: el.decompose()
    return re.sub(r'\s+',' ',a.get_text(' ',strip=True)).strip()

report={}
for lang,name in [('go','Go'),('python','Python')]:
    html=ROOT/'build'/f'book-{lang}.html'; pdf=ROOT/'editions'/f'Backend-from-First-Principles-{name}-A4.pdf'
    if not pdf.exists() or not html.exists(): continue
    book=parse(html.read_text()); doc=fitz.open(pdf)
    pages=json.loads((ROOT/'build'/f'pages-{lang}.json').read_text())
    inventory=json.loads((ROOT/'build'/f'inventory-{lang}.json').read_text())
    chapters=[]
    for chapter in book.select('section.chapter'):
        slug=chapter['id']; source=parse((ROOT/'source/dist'/slug/'index.html').read_text()).select_one('article.prose')
        for group in source.select('.codeblock'):
            panels=group.select(':scope > .code-panel')
            preferred=next((x for x in panels if x.get('data-panel')==lang),None)
            keep=[preferred] if preferred else panels
            keep += [x for x in panels if x.get('data-panel')=='sql' and x not in keep]
            for panel in panels:
                if panel not in keep: panel.decompose()
        expected=[p.get_text().expandtabs(4).strip('\n') for p in source.select('pre')]
        actual_code=[p.get_text().strip('\n') for p in chapter.select('pre')]
        assert expected==actual_code, f'{name}: code mismatch in {slug}'
        original=clean(source); actual=clean(parse(str(chapter.select_one('article.prose'))).article,True)
        assert original==actual, f'{name}: prose mismatch in {slug}'
        start=pages[slug]
        chapters.append({'chapter':int(slug[:2]),'title':chapter.h1.get_text(),'page':start,'prose_sha256':hashlib.sha256(original.encode()).hexdigest()})
    assert len(chapters)==27
    assert len(doc.get_toc())==434, f'Bookmark count {len(doc.get_toc())}'
    missing_targets=[]
    for link in book.select('a[href^="#"]'):
        if link['href'][1:] not in pages: missing_targets.append(link['href'])
    overflow=[]; short=[]; replacements=[]; tiny=[]
    for idx,page in enumerate(doc):
        words=page.get_text('words')
        if len(words)<12 and idx>2: short.append(idx+1)
        for w in words:
            if w[0]<36 or w[2]>page.rect.width-36 or w[1]<12 or w[3]>page.rect.height-12:
                overflow.append({'page':idx+1,'box':list(w[:4]),'text':w[4]})
        if '\ufffd' in page.get_text(): replacements.append(idx+1)
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    if span['size']<5.8 and len(span['text'].strip())>4:
                        tiny.append({'page':idx+1,'size':round(span['size'],2),'text':span['text'][:80]})
    # A whole-book contact sheet samples every chapter plus dense content pages.
    chosen=[0,1,2,3]
    for c in chapters:
        chosen.extend([c['page']-1,min(c['page']+1,len(doc)-1)])
    chosen=sorted(set(chosen))
    cw,ch=238,355
    for sheetno,offset in enumerate(range(0,len(chosen),24),1):
        chunk=chosen[offset:offset+24]; sheet=Image.new('RGB',(cw*4,ch*((len(chunk)+3)//4)),'#dce3e8'); draw=ImageDraw.Draw(sheet)
        for i,p in enumerate(chunk):
            pix=doc[p].get_pixmap(matrix=fitz.Matrix(.35,.35),alpha=False)
            im=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
            im.thumbnail((cw-24,ch-33))
            x=(i%4)*cw+12;y=(i//4)*ch+8; sheet.paste(im,(x,y));draw.text((x,y+im.height+5),f'{name} · page {p+1}',fill='black')
        sheet.save(ROOT/'build'/f'contact-{lang}-{sheetno}.jpg',quality=90)
    report[lang]={'file':pdf.name,'pages':len(doc),'size_bytes':pdf.stat().st_size,'chapters':chapters,'bookmarks':len(doc.get_toc()),'links':sum(len(p.get_links()) for p in doc),'missing_internal_targets':missing_targets,'margin_overflow':overflow,'nearly_empty_pages':short,'replacement_character_pages':replacements,'small_diagram_labels':tiny,'inventory_totals':{k:sum(c['after'][k] for c in inventory) for k in ['diagrams','tables','code','sections']}}
    print(name,len(doc),'pages; prose identical in all 27 chapters;',len(overflow),'boundary flags;',len(missing_targets),'missing targets;',len(tiny),'small label spans')
    print('Nearly empty',short)
    print('Overflow sample',overflow[:15])
(ROOT/'build/quality-report.json').write_text(json.dumps(report,indent=2))
