import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {runInNewContext} from 'node:vm';
import {createNotificationFeed} from '../static/notification-feed.js';

class Element {
  static active = null;
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.listeners = {};
    this.textContent = '';
    this.className = '';
    this.hidden = false;
    this.open = false;
    this.classList = {
      add: value => {this.className += ` ${value}`;},
      remove: value => {this.className = this.className.split(' ').filter(v => v !== value).join(' ');},
    };
  }
  append(...nodes) { for (const node of nodes) { node.parent = this; this.children.push(node); } }
  replaceChildren(...nodes) { if(this.contains(Element.active)) Element.active=null; this.children = []; this.append(...nodes); }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, callback) { this.listeners[key] = callback; }
  focus() { this.focused = true; Element.active=this; }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  closest() { return this.dataset.notificationEventId ? this : this.parent?.closest(); }
  scrollIntoView() {}
  showModal() { this.open = true; }
  close() { this.open = false; this.listeners.close?.(); }
  remove() { this.parent.children = this.parent.children.filter(node => node !== this); }
  get firstElementChild() { return this.children[0]; }
}

const source = (await readFile(new URL('../static/notifications.js', import.meta.url), 'utf8')).replace(/^import .*\n/, '');
const notificationLink = row => row.tagName === 'a' ? row : row.children[0];
const flush = async () => { for(let i=0;i<50;i++) await Promise.resolve(); };

async function environment(withHistory = false, initialCount = 1) {
  const nav = new Element('nav');
  const body = new Element('body');
  const history = withHistory ? new Element('section') : null;
  const events = [{event_id:1,run_id:'old',name:'Old task',status:'succeeded',status_label:'Succeeded',summary:'Done',read:false}];
  for(let id=2;id<=initialCount;id++) events.push({...events[0],event_id:id,run_id:`old-${id}`});
  let clearedThrough=0;
  let readThrough=0;
  const reads = [];
  const listeners = {};
  const document = {body, hidden:false, createElement:tag=>new Element(tag), querySelector:()=>nav,
    getElementById:id=>id === 'notificationHistory' ? history : null, addEventListener:(key, fn)=>{listeners[key]=fn;}};
  Object.defineProperty(document,'activeElement',{get:()=>Element.active});
  let interval;
  let offline = false;
  let calls = 0;
  let delayRead = false;
  let releaseRead;
  const navigations=[];
  const window = {location:{assign:url=>navigations.push(url)},addEventListener:(key,fn)=>{listeners[key]=fn;}, setInterval:fn=>{interval=fn;},history:{replaceState:()=>{}}};
  async function fetch(url, options) {
    calls++;
    if (offline) throw new Error('offline');
    let payload;
    if (url === '/api/notifications/read-all' || url === '/api/notifications/clear') {
      const {through} = JSON.parse(options.body);
      events.filter(e=>e.event_id<=through).forEach(e=>e.read=true);
      readThrough=Math.max(readThrough,through);
      if(url.endsWith('/clear'))clearedThrough=Math.max(clearedThrough,through);
      payload={unread_count:events.filter(e=>!e.read).length,read_through:readThrough,cleared_through:clearedThrough};
    } else if (url === '/api/notifications/read') {
      const ids = JSON.parse(options.body).event_ids;
      reads.push(...ids);
      events.filter(e=>ids.includes(e.event_id)).forEach(e=>e.read=true);
      payload = {unread_count:events.filter(e=>!e.read).length};
      if(delayRead) {
        delayRead=false;
        return new Promise((resolve,reject)=>{releaseRead=(failed=false)=>failed ? reject(Error('old read failed')) : resolve({ok:true,json:async()=>payload});});
      }
    } else if (url.startsWith('/api/notifications/runs?')) {
      payload = {runs:[],displayed_event_ids:[],has_more:false,next_cursor:null};
    } else if (url.startsWith('/api/notifications/events?')) {
      const cursor = Number(new URL(url,'http://local').searchParams.get('after'));
      payload = {events:events.filter(e=>e.event_id>Math.max(cursor,clearedThrough)).map(e=>({...e})),next_cursor:events.at(-1)?.event_id || cursor,has_more:false,unread_count:events.filter(e=>!e.read).length,read_through:readThrough,cleared_through:clearedThrough,inbox_events:events.filter(e=>e.event_id>clearedThrough && !e.read).slice(-25).map(e=>({...e})),inbox_cursor:events.at(-1)?.event_id || 0};
    } else {
      payload = {events:events.filter(e=>e.event_id>clearedThrough && !e.read).slice(-25).map(e=>({...e})),next_cursor:events.at(-1)?.event_id || 0,unread_count:events.filter(e=>!e.read).length,jobs:[],statuses:[],read_through:readThrough,cleared_through:clearedThrough};
    }
    return {ok:true,json:async()=>payload};
  }
  runInNewContext(source, {document,window,location:{search:''},URLSearchParams,fetch,createNotificationFeed,Map,Set,Date,Number,encodeURIComponent});
  await flush();
  return {nav,body,history,events,reads,listeners,document,navigations,poll:()=>{interval();},setOffline:value=>{offline=value;},delayNextRead:()=>{delayRead=true;},releaseRead:failed=>releaseRead(failed),get calls(){return calls;}};
}

const ui = await environment();
const drawer = ui.body.children.find(e=>e.tagName==='dialog');
const toasts = ui.body.children.find(e=>e.className==='notification-toasts');
assert.equal(toasts.children.length,0);
assert.equal(ui.nav.children[0].attributes['aria-label'],'Open notifications, 1 unread');
ui.events.push({event_id:2,run_id:'new',name:'<img onerror=bad()>',status:'running',status_label:'Last reported: running',summary:'Completion has not been reported',read:false});
ui.events.push({event_id:3,run_id:'new',name:'Safe task',status:'failed',status_label:'Failed',summary:'See job log',read:false});
ui.poll(); await flush();
assert.equal(toasts.children.length,2);
assert.equal(toasts.children[0].children[0].children[0].textContent,'<img onerror=bad()>');
assert.deepEqual(ui.reads,[]);
ui.nav.children[0].listeners.click(); await flush();
assert.equal(drawer.open,true);
assert.deepEqual(ui.reads,[],"opening the drawer must not mark its notifications read");
assert.equal(ui.nav.children[0].attributes['aria-label'],'Open notifications, 3 unread');
const focusedEvent = notificationLink(drawer.children.find(e=>e.className==='notification-recent').children[0]);
focusedEvent.focus();
ui.poll();await flush();
assert.ok(ui.document.activeElement, 'empty polling must preserve the focused notification');
assert.equal(ui.document.activeElement.href, focusedEvent.href);
focusedEvent.listeners.click({preventDefault(){}});await flush();
assert.deepEqual(ui.reads,[3]);
assert.equal(drawer.children.find(e=>e.className==='notification-recent').children.length,2);
assert.equal(ui.navigations.at(-1),'/notifications.html?run=new');
drawer.close();
ui.nav.children[0].listeners.click();await flush();
assert.equal(drawer.children.find(e=>e.className==='notification-recent').children.length,2);
drawer.close();
assert.equal(ui.nav.children[0].focused,true);
toasts.children[0].children[1].listeners.click();
assert.equal(toasts.children.length,1);
ui.document.hidden = true;
const prior = ui.calls;
ui.poll(); await flush();
assert.equal(ui.calls,prior);
ui.document.hidden = false;
ui.setOffline(true);ui.poll();await flush();
assert.match(ui.nav.children[0].title,/unavailable/);
ui.setOffline(false);ui.listeners.visibilitychange();await flush();
assert.equal(ui.nav.children[0].title,'Notifications');
const page = await environment(true);
assert.ok(page.history.children.some(e=>e.className==='notification-runs'));
assert.equal(page.history.children.find(e=>e.className==='notification-runs').children[0].className,'notification-empty');
const bulk=await environment(false,30);
bulk.nav.children[0].listeners.click();await flush();
const bulkDrawer=bulk.body.children.find(e=>e.tagName==='dialog');
const actions=bulkDrawer.children.find(e=>e.className==='notification-actions');
assert.ok(actions,'notification actions must be available');
const readAll=actions.children.find(e=>e.textContent==='Mark all read');
const clearAll=actions.children.find(e=>e.textContent==='Clear all');
assert.equal(readAll.disabled,false,'older unread notifications must remain actionable');
readAll.listeners.click();await flush();
assert.equal(bulk.nav.children[0].attributes['aria-label'],'Open notifications, 0 unread');
assert.equal(bulkDrawer.children.find(e=>e.className==='notification-recent').children[0].className,'notification-empty');
bulk.events.push({...bulk.events[0],event_id:31,run_id:'to-clear',read:false});bulk.poll();await flush();
clearAll.listeners.click();await flush();
assert.equal(bulkDrawer.children.find(e=>e.className==='notification-recent').children[0].className,'notification-empty');
bulk.poll();await flush();
assert.equal(bulkDrawer.children.find(e=>e.className==='notification-recent').children[0].className,'notification-empty');
bulk.events.push({...bulk.events[0],event_id:32,run_id:'new-after-clear',read:false});
bulk.poll();await flush();
assert.equal(notificationLink(bulkDrawer.children.find(e=>e.className==='notification-recent').children[0]).href,'/notifications.html?run=new-after-clear');
bulk.setOffline(true);clearAll.listeners.click();await flush();
assert.equal(notificationLink(bulkDrawer.children.find(e=>e.className==='notification-recent').children[0]).href,'/notifications.html?run=new-after-clear');
const race=await environment(false,30);
race.delayNextRead();
race.nav.children[0].listeners.click();await flush();
const raceDrawer=race.body.children.find(e=>e.tagName==='dialog');
notificationLink(raceDrawer.children.find(e=>e.className==='notification-recent').children[0]).listeners.click({preventDefault(){}});await flush();
raceDrawer.children.find(e=>e.className==='notification-actions').children.find(e=>e.textContent==='Clear all').listeners.click();await flush();
assert.equal(race.nav.children[0].attributes['aria-label'],'Open notifications, 0 unread');
race.releaseRead();await flush();
assert.equal(race.nav.children[0].attributes['aria-label'],'Open notifications, 0 unread','a pre-clear read response must not restore the old badge');
const errorRace=await environment(false,30);
errorRace.delayNextRead();
errorRace.nav.children[0].listeners.click();await flush();
const errorDrawer=errorRace.body.children.find(e=>e.tagName==='dialog');
notificationLink(errorDrawer.children.find(e=>e.className==='notification-recent').children[0]).listeners.click({preventDefault(){}});await flush();
errorDrawer.children.find(e=>e.className==='notification-actions').children.find(e=>e.textContent==='Clear all').listeners.click();await flush();
errorRace.releaseRead(true);await flush();
assert.match(errorDrawer.children[1].textContent,/0 unread/,'a superseded read error must not replace the successful clear status');
const single=await environment(false,2);
single.nav.children[0].listeners.click();await flush();
const singleDrawer=single.body.children.find(e=>e.tagName==='dialog');
const singleList=singleDrawer.children.find(e=>e.className==='notification-recent');
const dismissOne=singleList.children[0].children.find(e=>e.tagName==='button');
assert.ok(dismissOne,'each reminder needs its own dismiss button outside the details link');
dismissOne.focus();
dismissOne.listeners.click();await flush();
assert.deepEqual(single.reads,[2]);
assert.equal(single.navigations.length,0,'dismissing a reminder must not open details');
assert.equal(singleList.children.length,1);
assert.equal(notificationLink(singleList.children[0]).href,'/notifications.html?run=old');
assert.equal(single.nav.children[0].attributes['aria-label'],'Open notifications, 1 unread');
assert.equal(single.document.activeElement,notificationLink(singleList.children[0]));
single.poll();await flush();
assert.equal(singleList.children.length,1);
single.setOffline(true);
singleList.children[0].children.find(e=>e.tagName==='button').listeners.click();await flush();
assert.equal(singleList.children.length,1,'failed individual dismiss must retain the reminder');
const focusRace=await environment(false,2);
focusRace.nav.children[0].listeners.click();await flush();
const focusDrawer=focusRace.body.children.find(e=>e.tagName==='dialog');
const focusDismiss=focusDrawer.children.find(e=>e.className==='notification-recent').children[0].children[1];
focusDismiss.focus();focusRace.delayNextRead();focusDismiss.listeners.click();await flush();
const keepFocus=focusDrawer.children.find(e=>e.className==='notification-history-link');
keepFocus.focus();focusRace.releaseRead();await flush();
assert.equal(focusRace.document.activeElement,keepFocus,'completing a dismiss must not steal focus after the user moves it');
console.log('notification DOM behavior passed');
