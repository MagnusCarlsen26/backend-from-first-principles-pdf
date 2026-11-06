#!/usr/bin/env python3
"""Build faithful, language-selected print editions from Astro's rendered chapters."""
from pathlib import Path
from bs4 import BeautifulSoup
from collections import Counter
from html import escape
import argparse, json, re, subprocess, logging
from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
OUT = ROOT / 'editions'
LANGS = {'go': 'Go', 'python': 'Python', 'js': 'JavaScript', 'ts': 'TypeScript', 'java': 'Java'}
LABELS = {**LANGS, 'sql':'SQL', 'json':'JSON', 'yaml':'YAML', 'bash':'Shell', 'text':'Text', 'plaintext':'Text', 'http':'HTTP', 'protobuf':'Protocol Buffers', 'dockerfile':'Dockerfile', 'html':'HTML', 'typescript':'TypeScript', 'nginx':'nginx'}
PARTS = [(1,7,'The Request Path'), (8,14,'State & Machinery'), (15,20,'Running in Production'), (21,24,'Distribution & Scale'), (25,26,'OpenAPI & AI Agents'), (27,27,'System Design')]
FORMATTER = HtmlFormatter(nowrap=True, style='friendly')
COMMIT = subprocess.check_output(['git','-C',str(ROOT/'source'),'rev-parse','HEAD'],text=True).strip()

def soup(text): return BeautifulSoup(text,'lxml')
def inner(el): return ''.join(str(x) for x in el.contents)

def source_chapters():
    chapters = []
    for p in sorted((ROOT/'source/dist').glob('*/index.html')):
        s = soup(p.read_text())
        a = s.select_one('article.prose')
        if not a: continue
        chapters.append(dict(slug=p.parent.name, number=int(p.parent.name[:2]),
            title=s.select_one('h1.chapter-title').get_text(),
            summary=s.select_one('.chapter-summary').get_text(), html=str(a)))
    assert [c['number'] for c in chapters] == list(range(1,28))
    return chapters

def prepare_diagrams(chapters):
    palette = dict(re.findall(r'(--dg-[\w-]+):\s*([^;]+);',(ROOT/'source/src/components/Diagram.astro').read_text().split(":global(:root[data-theme='dark'])")[0]))
    palette.update({'--font-diagram-mono':'JetBrains Mono', '--font-ui':'Noto Sans', '--font-prose':'Noto Serif'})
    ddir=BUILD/'diagrams'; ddir.mkdir(parents=True,exist_ok=True)
    diagrams=[]
    for c in chapters:
        a=soup(c['html'])
        for i,svg in enumerate(a.select('figure.diagram svg'),1):
            name=f"{c['number']:02d}-{i:02d}"
            raw=str(svg)
            for k,v in palette.items(): raw=raw.replace(f'var({k})',v.strip())
            assert 'var(' not in raw, name
            x=BeautifulSoup(raw,'xml').svg
            # SVG definitions are scoped explicitly for browser measurement and PDF export.
            for el in x.find_all(id=True):
                old=el['id']; new=f'd{name}-{old}'; raw=raw.replace(f'id="{old}"',f'id="{new}"').replace(f'#{old})',f'#{new})').replace(f'"#{old}"',f'"#{new}"')
            x=BeautifulSoup(raw,'xml').svg
            x['style']='font-family: Noto Sans; color: #20242a'
            for el in x.select('text'):
                if 'mono' in el.get('class','') or 'mono' in el.get('font-family','').lower(): el['font-family']='JetBrains Mono'
                elif 'serif' in el.get('class',''): el['font-family']='Noto Serif'
                else: el['font-family']='Noto Sans'
            x['data-diagram']=name
            path=ddir/f'{name}.svg'
            if not path.exists(): path.write_text(str(x))
            diagrams.append(dict(name=name, chapter=c['number'], caption=svg.parent.parent.select_one('figcaption').get_text() if svg.parent.parent.select_one('figcaption') else '', path=str(path)))
    (BUILD/'diagrams.json').write_text(json.dumps(diagrams,indent=2))
    return diagrams

def prepare_chapter(c,language):
    s=soup(c['html']); a=s.select_one('article')
    before={'diagrams':len(a.select('figure.diagram')), 'tables':len(a.select('table')), 'code':len(a.select('pre')), 'sections':len(a.select('h2'))}
    removed=[]; selected=[]
    # Select by PANEL identity, not syntax: Dockerfiles and YAML also have language variants.
    for group in a.select('.codeblock'):
        panels=group.select(':scope > .code-panel')
        preferred=next((x for x in panels if x.get('data-panel')==language),None)
        keep=[preferred] if preferred else panels
        # SQL in a tab group is the underlying query, useful in every language edition.
        keep += [x for x in panels if x.get('data-panel')=='sql' and x not in keep]
        for panel in panels:
            if panel not in keep:
                removed.extend(p.get_text() for p in panel.select('pre')); panel.decompose()
            else:
                selected.append(panel.get('data-panel'))
                panel.attrs.pop('hidden',None)
                for p in panel.select('pre'): p['data-variant']=LABELS.get(panel.get('data-panel'),panel.get('data-panel'))
        for bar in group.select('.code-bar'): bar.decompose()
    for el in a.select('script, button, a.anchor'): el.decompose()
    for el in a.find_all(True):
        el.attrs.pop('hidden',None)
        for k in list(el.attrs):
            if k.startswith('data-astro') or k in ['style','tabindex','aria-pressed']: del el[k]
    # Scope all original section IDs and update links so every chapter has independent anchors.
    for el in a.find_all(id=True): el['id']=f"{c['slug']}--{el['id']}"
    for link in a.select('a[href]'):
        href=link['href']
        if href.startswith('#'): link['href']=f"#{c['slug']}--{href[1:]}"
        elif href.startswith('/'):
            bits=href.strip('/').split('#',1)
            if bits[0] in SLUGS: link['href']='#'+bits[0]+('--'+bits[1] if len(bits)>1 else '')
            else: link['href']='https://backend-from-first-principle.vercel.app'+href
    headings=[]
    for i,h in enumerate(a.select('h2'),1):
        if not h.get('id'): h['id']=f"{c['slug']}--section-{i}"
        headings.append((h['id'],h.get_text()))
        label=s.new_tag('span',attrs={'class':'section-number'}); label.string=f'{i:02d}'; h.insert(0,label)
    for link in a.select('a[href]'):
        href=link['href']
        if href==f"#{c['slug']}--top": link['href']='#'+c['slug']
        match=re.fullmatch('#'+re.escape(c['slug'])+r'--s(\d+)',href)
        if match and 0<int(match[1])<=len(headings): link['href']='#'+headings[int(match[1])-1][0]
    fits={x['name']:x for x in json.loads((BUILD/'diagram-fit.json').read_text())}
    for i,fig in enumerate(a.select('figure.diagram'),1):
        svg=fig.select_one('svg'); name=f"{c['number']:02d}-{i:02d}"
        fit=fits[name]; width,height=fit['fitted'][2:]
        if fit['minFont']*490/width<6.1 and width/height>1.25:
            fig['class']=fig.get('class',[])+['landscape-diagram']
        replacement=s.new_tag('img',src=(BUILD/'diagrams'/f'{name}.svg').as_uri(),alt=svg.get('aria-label','Diagram'))
        svg.replace_with(replacement)
        frame=fig.select_one('.diagram-frame')
        if frame: frame.unwrap()
        # Keep three short introductions with the wide artwork they introduce.
        # Without this, the change of page orientation strands them on near-empty pages.
        previous=fig.find_previous_sibling()
        if previous and 'landscape-diagram' in fig.get('class',[]) and (
            previous.get_text()=='Chain Tasks: Video Upload Example'
            or previous.get_text().startswith('Under the hood, Node.js uses')
            or (c['number']==23 and i==1)
        ):
            previous['class']=previous.get('class',[])+['diagram-context']
            fig.insert(0,previous.extract())
            fig['class']=fig.get('class',[])+['has-context']
    # Keep every remaining source code character; light syntax colour and safe wrapping.
    code_texts=[]
    for pre in list(a.select('pre')):
        text=pre.get_text().expandtabs(4); code_texts.append(text)
        lang=pre.get('data-lang','text'); title=pre.get('data-title','')
        variant=pre.get('data-variant',''); label=LABELS.get(lang,lang)
        if variant and variant!=label: label=f'{variant} · {label}'
        if title: label+=' / '+title
        try: lexer=get_lexer_by_name(lang)
        except Exception: lexer=TextLexer()
        replacement=s.new_tag('div',attrs={'class':'listing'})
        cap=s.new_tag('p',attrs={'class':'code-label'}); cap.string=label
        replacement.append(cap)
        block=s.new_tag('pre'); block['class']='source-code'
        # ASCII architecture drawings must not wrap or lose their column alignment.
        if any(ch in text for ch in '┌┐└┘│─'):
            block['class']+=' ascii'
            maxline=max(map(len,text.splitlines()),default=1)
            block['style']=f'font-size:{min(7.8, 486/maxline/0.60):.2f}pt'
        code=s.new_tag('code')
        # Parse inside <pre>: HTML parsers collapse whitespace-only nodes in a div.
        rendered=soup('<pre>'+highlight(text,lexer,FORMATTER)+'</pre>').pre
        for el in list(rendered.contents): code.append(el.extract())
        assert code.get_text().strip('\n')==text.strip('\n'), f"Code whitespace changed in {c['slug']}"
        block.append(code); replacement.append(block); pre.replace_with(replacement)
    for table in a.select('table'):
        if len(table.select('thead th'))>=5: table['class']=['wide-table']
    for wrapper in list(a.select('.table-wrap')): wrapper.unwrap()
    refs=[]
    for link in a.select('a[href^="https://"], a[href^="http://"]'):
        url=link['href']
        if url not in refs: refs.append(url)
        note=s.new_tag('sup',attrs={'class':'reference-mark'}); note.string=f'[{refs.index(url)+1}]'; link.insert_after(note)
    ref_html=''
    if refs:
        ref_html='<section class="references"><h3>Links & further reading</h3><ol>'+''.join(f'<li><a href="{escape(u,quote=True)}">{escape(u)}</a></li>' for u in refs)+'</ol></section>'
    part=next(p[2] for p in PARTS if p[0]<=c['number']<=p[1])
    outline=''.join(f'<li><a href="#{escape(i)}">{escape(t)}</a></li>' for i,t in headings)
    content=f'''<section class="chapter" id="{c['slug']}"><div class="chapter-opening">
      <p class="part-label">{escape(part)}</p><p class="chapter-kicker">Chapter {c['number']:02d}</p>
      <h1 class="chapter-title">{escape(c['title'])}</h1><p class="chapter-summary">{escape(c['summary'])}</p>
      <h3 class="outline-label">In this chapter</h3><ol class="chapter-outline">{outline}</ol></div>
      <article class="prose">{inner(a)}{ref_html}</article></section>'''
    after={'diagrams':len(a.select('figure.diagram')), 'tables':len(a.select('table')), 'code':len(a.select('pre')), 'sections':len(a.select('h2'))}
    assert before['diagrams']==after['diagrams'] and before['tables']==after['tables'] and before['sections']==after['sections']
    assert before['code']==after['code']+len(removed)
    return content,dict(chapter=c['number'],title=c['title'],before=before,after=after,removed_alternatives=len(removed),selected_panels=Counter(selected),words=len(a.get_text().split()),code_characters=sum(map(len,code_texts)))

def frontmatter(chapters,language):
    lang=LANGS[language]
    contents=''
    for start,end,title in PARTS:
        items=[c for c in chapters if start<=c['number']<=end]
        if not items: continue
        contents+=f'<div class="toc-part"><h3>{escape(title)}</h3><ol>'+''.join(f'<li><span class="toc-num">{c["number"]:02d}</span><a href="#{c["slug"]}">{escape(c["title"])}</a></li>' for c in items)+'</ol></div>'
    return f'''<section class="cover"><div class="cover-top">AN ENGINEERING REFERENCE · PRINT EDITION</div>
      <p class="cover-language">{lang} edition</p><h1>Backend<br>from First<br><em>Principles.</em></h1>
      <p class="cover-subtitle">Understand the machinery.<br>Build with confidence.</p>
      <div class="cover-rule"></div><p class="cover-topics">REQUESTS & APIS / DATA & STATE<br>RELIABILITY & SECURITY / DISTRIBUTED SYSTEMS</p>
      <div class="cover-bottom"><p>27 chapters · Theory, diagrams & code</p><p>Created & curated by<br><strong>DsThakurRawat & contributors</strong></p></div></section>
    <section class="edition-page"><p class="part-label">About this edition</p><h1>A reference for<br>your workbench.</h1>
      <p>This print edition brings all 27 chapters of <em>Backend from First Principles</em> into one searchable, bookmarked volume, with the original explanations, diagrams and tables.</p>
      <h3>Reading the {lang} edition</h3><p>Where the website offers equivalent language tabs, this edition selects <strong>{lang}</strong>. Shared SQL, protocol messages, commands and configuration remain. Examples that explain a specific runtime, or have no equivalent in the source, keep their original language and are labelled accordingly. The teaching text is in English.</p>
      <p>Section numbers restart in each chapter. The main contents and chapter outlines show printed page numbers. Links remain clickable; external reading links are also listed as full URLs at the end of each chapter.</p>
      <h3>Designed for paper</h3><p>A4 · mirrored binding margins · colour diagrams · white paper. Reading pages are portrait; dense, wide diagrams have landscape pages. Print at <strong>100% / Actual size</strong>, with automatic page orientation. For two-sided printing choose <strong>flip on the long edge</strong>. Chapters begin on the next available page.</p>
      <h3>Source & attribution</h3><p>Original content: <strong>DsThakurRawat & repository contributors</strong>.<br>Source website:<br><a href="https://backend-from-first-principle.vercel.app/">https://backend-from-first-principle.vercel.app/</a></p>
      <p>Repository:<br><a href="https://github.com/DsThakurRawat/Backend-from-first-Principle">https://github.com/DsThakurRawat/Backend-from-first-Principle</a></p>
      <p class="small">Prepared 6 November 2026 from repository snapshot<br><span class="commit">{COMMIT}</span>.<br>This is a personal print adaptation. Technical content and authorship remain with the original project; the layout and language-tab selection were adapted for this edition.</p></section>
    <nav class="contents"><p class="part-label">The complete reference</p><h1>Contents</h1>{contents}</nav>'''

def build(chapters,language,render):
    pieces=[]; report=[]
    for c in chapters:
        html,stats=prepare_chapter(c,language); pieces.append(html); report.append(stats)
    css=(ROOT/'tools/print.css').read_text()+'\n'+FORMATTER.get_style_defs('.source-code')+'\n.source-code :is(.c,.c1,.cm,.cp,.cs,.ch,.cpf) { color:#506773; } .source-code :is(.m,.mi,.mf,.mh,.mo,.mb,.il) { color:#754272; } .source-code .err { border:0; color:#7d2929; background:none; }'
    html='<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Backend from First Principles — '+LANGS[language]+' edition</title><meta name="author" content="DsThakurRawat and contributors"><meta name="description" content="A complete A4 print adaptation of the 27-chapter engineering reference."><style>'+css+'</style></head><body>'+frontmatter(chapters,language)+''.join(pieces)+'</body></html>'
    path=BUILD/f'book-{language}.html'; path.write_text(html)
    (BUILD/f'inventory-{language}.json').write_text(json.dumps(report,indent=2))
    print(f'{LANGS[language]}: {len(chapters)} chapters; '+str({k:sum(r['after'][k] for r in report) for k in ['diagrams','tables','code','sections']}),flush=True)
    if render:
        render_existing(language)

def render_existing(language):
    from weasyprint import HTML
    from lxml import etree
    for svg in (BUILD/'diagrams').glob('*.svg'): etree.parse(str(svg))
    errors=[]
    class CaptureErrors(logging.Handler):
        def emit(self, record): errors.append(record.getMessage())
    logger=logging.getLogger('weasyprint'); handler=CaptureErrors(level=logging.ERROR)
    logger.setLevel(logging.ERROR); logger.addHandler(handler)
    doc=HTML(filename=BUILD/f'book-{language}.html').render()
    if errors: raise RuntimeError('PDF rendering errors: '+repr(errors))
    pages={}
    for number,p in enumerate(doc.pages,1):
        for anchor in p.anchors: pages.setdefault(anchor,number)
    (BUILD/f'pages-{language}.json').write_text(json.dumps(pages,indent=2))
    target=OUT/f'Backend-from-First-Principles-{LANGS[language]}-A4.pdf'
    doc.write_pdf(target, pdf_variant='pdf/a-3u', optimize_images=True)
    logger.removeHandler(handler)
    if errors: raise RuntimeError('PDF export errors: '+repr(errors))
    print(f'Wrote {target.name}: {len(doc.pages)} pages / {target.stat().st_size/1024/1024:.1f} MB; all diagram files valid and no rendering errors',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--languages',nargs='+',choices=LANGS,default=['go','python']); ap.add_argument('--render',action='store_true'); ap.add_argument('--render-only',action='store_true'); ap.add_argument('--chapters',nargs='+',type=int); ap.add_argument('--diagrams-only',action='store_true'); args=ap.parse_args()
    BUILD.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
    if args.render_only:
        for language in args.languages: render_existing(language)
        raise SystemExit(0)
    all_chapters=source_chapters(); SLUGS={c['slug'] for c in all_chapters}
    prepare_diagrams(all_chapters)
    if not args.diagrams_only:
        chapters=[c for c in all_chapters if not args.chapters or c['number'] in args.chapters]
        for language in args.languages: build(chapters,language,args.render)
