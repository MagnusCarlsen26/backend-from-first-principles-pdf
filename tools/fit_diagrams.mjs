import { chromium } from 'playwright-core';
import { readFile, writeFile } from 'node:fs/promises';
const diagrams=JSON.parse(await readFile(new URL('../build/diagrams.json',import.meta.url),'utf8'));
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1000,height:800}});
const results=[];
for (const d of diagrams) {
 const source=await readFile(d.path,'utf8');
 await page.setContent(`<html><body style="margin:0">${source}</body></html>`);
 if(d.name==='21-10') await page.evaluate(()=>{
  const s=document.querySelector('svg');
  s.setAttribute('viewBox','0 0 720 320');
  for(const t of s.querySelectorAll('text')){
   const text=t.textContent.trim();
   if(text.startsWith('api-server writes your desired state')){
    t.textContent=''; t.setAttribute('text-anchor','middle'); t.setAttribute('x','360');
    const lines=['api-server writes your desired state to etcd;', ' controllers + scheduler reconcile it onto nodes; kubelets run the pods.'];
    lines.forEach((line,i)=>{const span=document.createElementNS('http://www.w3.org/2000/svg','tspan');span.setAttribute('x','360');span.setAttribute('y',String(250+i*18));span.textContent=line;t.appendChild(span);});
   }
   if(text.startsWith('kubelets continuously report')) {t.setAttribute('text-anchor','middle');t.setAttribute('x','360');}
  }
 });
 await page.evaluate(()=>document.fonts.ready);
 const info=await page.evaluate(()=>{
  const s=document.querySelector('svg');
  const b=s.getBBox(), v=s.viewBox.baseVal;
  const x=Math.min(v.x,b.x-5), y=Math.min(v.y,b.y-5);
  const w=Math.max(v.x+v.width,b.x+b.width+5)-x, h=Math.max(v.y+v.height,b.y+b.height+5)-y;
  const original=[v.x,v.y,v.width,v.height];
  s.setAttribute('viewBox',[x,y,w,h].join(' '));
  const sizes=[...s.querySelectorAll('text')].filter(t=>t.textContent.trim()).map(t=>parseFloat(getComputedStyle(t).fontSize));
  return {original, fitted:[x,y,w,h],svg:s.outerHTML,text:s.textContent,minFont:Math.min(...sizes)};
 });
 // HTML's serializer uses &nbsp;, which is not a defined entity in standalone SVG/XML.
 await writeFile(d.path,info.svg.replaceAll('&nbsp;','&#160;'));
 results.push({name:d.name,original:info.original,fitted:info.fitted,minFont:info.minFont});
}
await writeFile(new URL('../build/diagram-fit.json',import.meta.url),JSON.stringify(results,null,2));
console.log(`Checked ${diagrams.length} SVG diagrams; expanded ${results.filter(x=>x.original.some((v,i)=>Math.abs(v-x.fitted[i])>8)).length} viewboxes to include overflow.`);
await browser.close();
