from pathlib import Path
from subprocess import run

from fastapi.testclient import TestClient

from app.api import app


ROOT = Path(__file__).resolve().parents[1]


def test_shared_ui_toasts_read_dismiss_visibility_and_recovery():
    result = run(["node", "tests/notifications_dom_harness.mjs"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_feed_initial_snapshot_backlog_retry_and_visibility_contract():
    script = """
import assert from 'node:assert/strict';
import {createNotificationFeed} from './static/notification-feed.js';
let pending = [];
let emitted = [];
let errors = 0;
let snapshots = 0;
let urls = [];
let release;
const feed = createNotificationFeed({
  request: async (url) => {urls.push(url); const item = pending.shift(); if(item instanceof Error) throw item; return item;},
  onSnapshot: () => snapshots++, onEvents: (events) => emitted.push(...events.map(e => e.event_id)),
  onError: () => errors++, onUnread: () => {}
});
pending.push({events:[{event_id:3}], next_cursor:3, unread_count:1});
await feed.tick();
assert.equal(snapshots,1); assert.deepEqual(emitted,[]);
pending.push({events:[{event_id:4}],next_cursor:4,has_more:true,unread_count:2});
pending.push(new Error('offline'));
await feed.tick();
assert.deepEqual(emitted,[4]); assert.equal(errors,1);
pending.push({events:[{event_id:5},{event_id:6}],next_cursor:6,has_more:false,unread_count:3});
await feed.tick();
assert.equal(urls.at(-1),'/api/notifications/events?after=4');
assert.deepEqual(emitted,[4,5,6]);
const blocking = createNotificationFeed({request: () => new Promise(r => release=r), onSnapshot:()=>{},onEvents:()=>{},onError:()=>{},onUnread:()=>{}});
const first=blocking.tick();
await blocking.tick();
release({events:[],next_cursor:0,unread_count:0});
await first;
let attempts=0;
const retry=createNotificationFeed({request:async()=>{attempts++; if(attempts===1) throw Error('offline');return {events:[],next_cursor:9,unread_count:0};},onSnapshot:()=>{},onEvents:()=>{},onError:()=>{},onUnread:()=>{}});
await retry.tick();await retry.tick();assert.equal(attempts,2);
let finishRequest;
let staleEvents=[];
let call=0;
const invalidated=createNotificationFeed({request:async()=>{
  if(call++===0)return {events:[],next_cursor:1,unread_count:0};
  return new Promise(resolve=>finishRequest=resolve);
},onSnapshot:()=>{},onEvents:events=>staleEvents.push(...events),onError:()=>{},onUnread:()=>{}});
await invalidated.tick();
const inflight=invalidated.tick();
invalidated.invalidate();
finishRequest({events:[{event_id:2}],next_cursor:2,unread_count:1});
await inflight;
assert.deepEqual(staleEvents,[]);
"""
    result = run(["node", "--input-type=module", "-e", script], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_history_page_and_shared_assets_are_served():
    client = TestClient(app)
    response = client.get("/notifications.html")
    assert response.status_code == 200
    assert 'id="notificationHistory"' in response.text
    for name in ("notifications.js", "notification-feed.js", "notifications.css"):
        assert client.get(f"/static/{name}").status_code == 200
    for name in ("macro-dashboard", "ticker-context", "portfolio", "quant-screen", "ticker-workflow"):
        html = (ROOT / "static" / f"{name}.html").read_text()
        assert '/static/notifications.js' in html
