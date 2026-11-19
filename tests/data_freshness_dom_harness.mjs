import assert from 'node:assert/strict';
import {createFreshnessPage} from '../static/data-freshness.js';

class Element {
  constructor(tag) {this.tagName=tag;this.children=[];this.attributes={};this.dataset={};this.listeners={};this.textContent='';this.className='';this.value='';this.hidden=false;}
  append(...nodes) {for(const node of nodes){node.parent=this;this.children.push(node);}}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  setAttribute(key,value){this.attributes[key]=String(value);}
  addEventListener(key,callback){this.listeners[key]=callback;}
  focus(){Element.active=this;}
}
const nodes=Object.fromEntries(['freshnessApp','freshnessAsOf','freshnessStats','freshnessSearch','freshnessCategory','freshnessReset','freshnessCount','freshnessRows','freshnessMessage','freshnessSchedules','freshnessReload'].map(id=>[id,new Element('div')]));
const document={createElement:tag=>new Element(tag),getElementById:id=>nodes[id]};
const status=[['due','Update due'],['missing','Missing'],['processing','Processing needed'],['unknown','Unknown'],['current','Fresh']].map(([code,label])=>({code,label}));
const payload={as_of:'2026-11-13T12:00:00Z',timezone:'Asia/Shanghai',availability:'available',history_available:true,unavailable_datasets:0,statuses:status,counts:Object.fromEntries(status.map(s=>[s.code,1])),categories:['Policy','Prices'],collection_schedules:[{label:'Macro data refresh',cadence:'Daily at 12:00 and 20:00',timezone:'Asia/Shanghai',verified_at:'2026-11-13'}],datasets:status.map((s,i)=>({id:String(i),name:i===0?'<img onerror=bad()>':'Example '+i,source:'Fed',source_url:i===0?'javascript:bad()':'https://www.federalreserve.gov/',category:i===0?'Prices':'Policy',status:s.code,status_label:s.label,current_period:'2026-10-01',period_basis:'month',frequency:'Monthly',storage_frequency:'Monthly',reason:'Example reason',schedule:{note:'Verified schedule',source_url:'https://www.federalreserve.gov/',coverage_start:'2026-01-01',coverage_end:'2026-12-31',verified_at:'2026-11-13'},next_release:{at:'2026-11-18T14:00:00-05:00',precision:'exact',period:'2026-10-01',timezone:'America/New_York'},history:{availability:'available',last_successful_check:{at:'2026-11-13T12:00:00Z',status_label:'Succeeded',href:'/notifications.html?run=abc'},last_attempt:{status_label:'Failed',href:'javascript:bad()'}}}))};
let offline=false;
payload.datasets[0].current_period='2026-10';
payload.datasets[0].source_observation_date='2026-10-01';
payload.datasets[0].stored_period='2026-11-08';
payload.datasets[0].lineage_basis='reconstructed_from_cached_source';
payload.datasets[0].comparison_basis='Source-date monitoring window: 5 calendar days';
payload.datasets[1].lineage_basis='conflicting';
payload.datasets[2].period_basis='quarter';
payload.datasets[2].current_period='2026-12-31';
payload.datasets[2].period_note='Quarter in progress';
payload.datasets[2].expected_quarter='2026-12-31';
let response=payload;
let calls=0;
const page=createFreshnessPage({document,request:async url=>{assert.equal(url,'/api/macro-data-freshness');calls++;if(offline)throw Error('secret');return response;}});
assert.equal(nodes.freshnessApp.attributes['aria-busy'],'true');
await page.ready;
assert.equal(nodes.freshnessApp.attributes['aria-busy'],'false');
assert.equal(nodes.freshnessStats.children.length,5);
const descendants=node=>[node,...node.children.flatMap(descendants)];
const metricRows=()=>descendants(nodes.freshnessRows).filter(node=>node.tagName==='tbody').flatMap(node=>node.children);
const text=node=>[node.textContent,...node.children.map(text)].join(' ');
assert.match(text(nodes.freshnessRows),/<img onerror=bad\(\)>/);
assert.match(text(nodes.freshnessRows),/Oct 2026/);
assert.match(text(nodes.freshnessRows),/Stored date \/ label/);
assert.match(text(nodes.freshnessRows),/2026-11-08/);
assert.match(text(nodes.freshnessRows),/Verified against cached source/);
assert.match(text(nodes.freshnessRows),/Source-date monitoring window/);
assert.match(text(nodes.freshnessRows),/Conflicting source evidence/);
const quarterRow=metricRows().find(row=>row.children.some(cell=>text(cell).includes('Example 2')));
assert.match(text(quarterRow),/Q4 2026/);
assert.match(text(quarterRow),/Quarter in progress/);
assert.ok(!descendants(nodes.freshnessRows).some(x=>x.tagName==='img'));
assert.ok(!descendants(nodes.freshnessRows).some(x=>String(x.href).startsWith('javascript:')));
assert.equal(metricRows().length,10);
assert.equal(nodes.freshnessRows.children.length,2);
assert.ok(nodes.freshnessRows.children.every(group=>group.tagName==='details' && !group.open),'categories must start collapsed');
const prices=nodes.freshnessRows.children.find(group=>group.dataset.category==='Prices');
assert.match(text(prices.children[0]),/Prices/);
assert.match(text(prices.children[0]),/1 dataset/);
assert.match(text(prices.children[0]),/Update due.*1/);
prices.open=true;prices.listeners.toggle();
const priceRows=descendants(prices).find(node=>node.tagName==='tbody').children;
const expand=descendants(priceRows[0]).find(x=>x.tagName==='button');
expand.focus();expand.listeners.click();
assert.equal(expand.attributes['aria-expanded'],'true');
assert.equal(priceRows[1].hidden,false);
assert.equal(Element.active,expand);
expand.listeners.click();assert.equal(priceRows[1].hidden,true);
nodes.freshnessStats.children[0].listeners.click();
assert.equal(metricRows().length,2);
assert.equal(nodes.freshnessRows.children.length,1);
assert.equal(nodes.freshnessRows.children[0].open,true,'status filters should reveal matching rows');
assert.equal(nodes.freshnessStats.children[0].attributes['aria-pressed'],'true');
nodes.freshnessReset.listeners.click();
nodes.freshnessCategory.value='Policy';nodes.freshnessCategory.listeners.change();
assert.equal(metricRows().length,8);
assert.equal(nodes.freshnessRows.children[0].open,true);
assert.match(text(nodes.freshnessRows.children[0].children[0]),/4 datasets/);
nodes.freshnessSearch.value='no matches';nodes.freshnessSearch.listeners.input();
assert.match(text(nodes.freshnessRows),/No matching datasets/);
nodes.freshnessReset.listeners.click();assert.equal(metricRows().length,10);
assert.equal(nodes.freshnessRows.children.find(g=>g.dataset.category==='Prices').open,true,'reset restores browsing expansion');
assert.equal(nodes.freshnessRows.children.find(g=>g.dataset.category==='Policy').open,false);
offline=true;await page.reload();
assert.match(text(nodes.freshnessMessage),/unavailable.*retry/i);
assert.ok(!text(nodes.freshnessMessage).includes('secret'));
offline=false;response={...payload,availability:'partial',history_available:false,unavailable_datasets:1};
await page.reload();
assert.match(text(nodes.freshnessMessage),/1 dataset/);
assert.match(text(nodes.freshnessMessage),/Task history is unavailable/);
assert.equal(metricRows().length,10);
response={...payload,datasets:[]};await page.reload();
assert.match(text(nodes.freshnessMessage),/unavailable/i);
assert.equal(nodes.freshnessRows.children.find(g=>g.dataset.category==='Prices').open,true,'reload keeps expansion');
assert.equal(calls,4);
console.log('freshness DOM interactions passed');
