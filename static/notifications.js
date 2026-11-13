import { createNotificationFeed } from './notification-feed.js';

const nav = document.querySelector('.topnav');
const historyRoot = document.getElementById('notificationHistory');
const recent = new Map();
let unreadCount = 0;
let feedError = false;
let historyVersion = 0;
let historyBefore = null;
let historyNext = null;
let historyStack = [];
let currentRunId = new URLSearchParams(location.search).get('run');
let detailVersion = 0;
let lastReadError = false;
let latestCursor = 0;
let clearedThrough = 0;
let readThrough = 0;
let actionBusy = false;
let actionError = '';
let mutationVersion = 0;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(label, handler, className = 'notification-button') {
  const node = el('button', className, label);
  node.type = 'button';
  node.addEventListener('click', handler);
  return node;
}

async function request(url, options) {
  const response = await fetch(url, { cache: 'no-store', ...options });
  if (!response.ok) throw new Error('Notification history is unavailable; please retry');
  return response.json();
}

function when(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? '—' : date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function duration(run) {
  const seconds = Math.max(0, Math.round(((run.ended_at ? new Date(run.ended_at) : new Date()) - new Date(run.started_at)) / 1000));
  if (!Number.isFinite(seconds)) return '—';
  const value = seconds < 60 ? `${seconds}s` : seconds < 3600 ? `${Math.floor(seconds / 60)}m ${seconds % 60}s` : `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m`;
  return run.ended_at ? value : `${value} since start`;
}

function title(run) {
  return run.target ? `${run.name} · ${run.target}` : run.name;
}

function badge(run) {
  const node = el('span', 'notification-badge', run.status_label);
  node.dataset.status = run.status;
  return node;
}

const bell = button('', () => openDrawer(), 'notification-bell');
bell.id = 'notificationBell';
bell.setAttribute('aria-label', 'Open notifications');
bell.setAttribute('aria-haspopup', 'dialog');
bell.setAttribute('aria-controls', 'notificationDrawer');
const bellIcon = el('span', 'notification-bell-icon');
bellIcon.setAttribute('aria-hidden', 'true');
bellIcon.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Z"/><path d="M10 21h4"/></svg>';
const count = el('span', 'notification-count');
count.hidden = true;
bell.append(bellIcon, count);
nav?.append(bell);

const drawer = el('dialog', 'notification-drawer');
drawer.id = 'notificationDrawer';
drawer.setAttribute('aria-labelledby', 'notificationDrawerTitle');
const drawerHead = el('header', 'notification-drawer-head');
const drawerTitle = el('h2', '', 'Notifications');
drawerTitle.id = 'notificationDrawerTitle';
const close = button('×', () => drawer.close(), 'notification-close');
close.setAttribute('aria-label', 'Close notifications');
drawerHead.append(drawerTitle, close);
const drawerStatus = el('p', 'notification-muted');
drawerStatus.setAttribute('role', 'status');
const drawerActions = el('div', 'notification-actions');
const readAllButton = button('Mark all read', () => bulkAction('read-all'));
const clearAllButton = button('Clear all', () => bulkAction('clear'));
clearAllButton.title = 'Clear reminders from this panel. Task execution history is kept.';
drawerActions.append(readAllButton, clearAllButton);
const drawerList = el('div', 'notification-recent');
const historyLink = el('a', 'notification-history-link', 'View execution history →');
historyLink.href = '/notifications.html';
drawer.append(drawerHead, drawerStatus, drawerActions, drawerList, historyLink);
document.body.append(drawer);
drawer.addEventListener('close', () => { if (nav) bell.focus(); });
drawer.addEventListener('click', event => { if (event.target === drawer) { const r = drawer.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) drawer.close(); } });

const toasts = el('div', 'notification-toasts');
toasts.setAttribute('aria-live', 'polite');
toasts.setAttribute('aria-relevant', 'additions');
document.body.append(toasts);

function setUnread(value) {
  unreadCount = value;
  count.textContent = value > 99 ? '99+' : String(value);
  count.hidden = value === 0;
  bell.setAttribute('aria-label', `Open notifications, ${value} unread`);
}

function remember(events) {
  for (const event of events) if (event.event_id > clearedThrough && event.event_id > readThrough && !event.read) {
    recent.set(event.event_id, event);
  }
  const sorted = [...recent.keys()].sort((a, b) => b - a);
  for (const id of sorted.slice(25)) recent.delete(id);
}

function applyNotificationState(payload) {
  latestCursor = Math.max(latestCursor, payload.next_cursor || 0, payload.inbox_cursor || 0);
  clearedThrough = Math.max(clearedThrough, payload.cleared_through || 0);
  readThrough = Math.max(readThrough, payload.read_through || 0);
  for (const [id, event] of recent) {
    if (id <= clearedThrough || id <= readThrough || event.read) recent.delete(id);
  }
  for (const node of [...toasts.children]) if (Number(node.dataset.eventId) <= clearedThrough) node.remove();
}

async function bulkAction(action) {
  if (actionBusy || feedError) return;
  const through = latestCursor;
  actionBusy = true;
  actionError = '';
  mutationVersion++;
  feed.invalidate();
  renderDrawer();
  try {
    const result = await request(`/api/notifications/${action}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ through }),
    });
    feed.invalidate();
    applyNotificationState(result);
    lastReadError = false;
    setUnread(result.unread_count);
  } catch {
    actionError = 'Could not update notifications. Please retry.';
  } finally {
    actionBusy = false;
    renderDrawer();
  }
}

async function markRead(ids) {
  if (actionBusy) return;
  const version = mutationVersion;
  const pending = [...new Set(ids)].filter(id => !recent.get(id)?.read);
  if (!pending.length) return;
  feed.invalidate();
  try {
    for (let offset = 0; offset < pending.length; offset += 200) {
      const batch = pending.slice(offset, offset + 200);
      const result = await request('/api/notifications/read', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ event_ids: batch }) });
      if (version !== mutationVersion) return;
      feed.invalidate();
      for (const id of batch) recent.delete(id);
      setUnread(result.unread_count);
    }
    lastReadError = false;
  } catch {
    if (version === mutationVersion) lastReadError = true;
  }
  renderDrawer();
}

function renderDrawer() {
  const focusedEventId = drawer.open && drawerList.contains(document.activeElement)
    ? document.activeElement.closest('[data-notification-event-id]')?.dataset.notificationEventId : null;
  const focusedDismiss = document.activeElement?.dataset.notificationDismiss === 'true';
  let focusedLink = null;
  drawerList.replaceChildren();
  drawerStatus.textContent = actionError || (feedError ? 'Notifications are unavailable. Retrying automatically.' : lastReadError ? 'Could not mark notifications read. Please retry.' : `${unreadCount} unread · Actual task starts and results`);
  readAllButton.disabled = actionBusy || feedError || unreadCount === 0;
  clearAllButton.disabled = actionBusy || feedError || recent.size === 0;
  if (!recent.size) drawerList.append(el('p', 'notification-empty', feedError ? 'History could not be loaded.' : 'No notifications here. Task execution history is available below.'));
  for (const event of [...recent.values()].sort((a, b) => b.event_id - a.event_id)) {
    const row = el('div', 'notification-event-row');
    const link = el('a', 'notification-event');
    link.dataset.notificationEventId = String(event.event_id);
    link.href = `/notifications.html?run=${encodeURIComponent(event.run_id)}`;
    link.addEventListener('click', async click => {
      if (click.metaKey || click.ctrlKey || click.shiftKey || click.altKey || click.button > 0) return;
      click.preventDefault();
      await markRead([event.event_id]);
      window.location.assign(link.href);
    });
    if (!event.read) link.classList.add('is-unread');
    link.append(el('strong', '', title(event)), badge(event), el('span', 'notification-muted', when(event.ended_at || event.started_at)), el('span', 'notification-muted', event.summary));
    const dismiss = button('×', async () => {
      const restoreFocus = document.activeElement === dismiss;
      await markRead([event.event_id]);
      if (recent.has(event.event_id)) return;
      for (const node of [...toasts.children]) if (Number(node.dataset.eventId) === event.event_id) node.remove();
      if (restoreFocus && drawer.open && !drawer.contains(document.activeElement)) {
        const nextLink = drawerList.firstElementChild?.children[0];
        (nextLink || historyLink).focus();
      }
    }, 'notification-close notification-dismiss');
    dismiss.setAttribute('aria-label', `Clear notification: ${title(event)}`);
    dismiss.title = 'Clear this notification. Task history is kept.';
    dismiss.dataset.notificationEventId = String(event.event_id);
    dismiss.dataset.notificationDismiss = 'true';
    dismiss.disabled = actionBusy;
    if (link.dataset.notificationEventId === focusedEventId) focusedLink = focusedDismiss ? dismiss : link;
    row.append(link, dismiss);
    drawerList.append(row);
  }
  if (focusedLink) focusedLink.focus({ preventScroll: true });
}

async function openDrawer() {
  renderDrawer();
  drawer.showModal();
  close.focus();
  await feed.tick();
}

function toast(event) {
  const node = el('div', 'notification-toast');
  node.dataset.eventId = String(event.event_id);
  const link = el('a', 'notification-toast-link');
  link.href = `/notifications.html?run=${encodeURIComponent(event.run_id)}`;
  link.append(el('strong', '', title(event)), badge(event), el('span', 'notification-muted', event.summary));
  const dismiss = button('×', () => node.remove(), 'notification-close');
  dismiss.setAttribute('aria-label', 'Dismiss notification');
  node.append(link, dismiss);
  toasts.append(node);
  while (toasts.children.length > 5) toasts.firstElementChild.remove();
}

let jobFilter;
let statusFilter;
let historyList;
let historyStatus;
let previous;
let next;
let detailPanel;

function select(label, key, entries) {
  const wrapper = el('label', 'notification-filter');
  wrapper.append(el('span', 'notification-muted', label));
  const node = el('select');
  node.id = key;
  const option = el('option', '', `All ${label.toLowerCase()}`);
  option.value = '';
  node.append(option);
  for (const entry of entries) {
    const opt = el('option', '', entry.name || entry.label);
    opt.value = entry.job_id || entry.status;
    node.append(opt);
  }
  node.addEventListener('change', () => { historyBefore = null; historyStack = []; loadHistory(); });
  wrapper.append(node);
  return [wrapper, node];
}

function setupHistory(snapshot) {
  if (!historyRoot || historyList) return;
  historyRoot.replaceChildren();
  const filters = el('div', 'notification-filters');
  const [jobLabel, jobSelect] = select('Tasks', 'notificationJobFilter', snapshot.jobs);
  const [statusLabel, statusSelect] = select('Statuses', 'notificationStatusFilter', snapshot.statuses);
  jobFilter = jobSelect;
  statusFilter = statusSelect;
  filters.append(jobLabel, statusLabel, button('Refresh', () => { feed.tick(); loadHistory(); }));
  historyStatus = el('p', 'notification-muted');
  historyStatus.setAttribute('role', 'status');
  historyList = el('div', 'notification-runs');
  const pages = el('div', 'notification-pagination');
  previous = button('← Newer', () => { historyBefore = historyStack.pop() ?? null; loadHistory(); });
  next = button('Older →', () => { historyStack.push(historyBefore); historyBefore = historyNext; loadHistory(); });
  pages.append(previous, next);
  detailPanel = el('section', 'notification-detail');
  detailPanel.hidden = true;
  detailPanel.setAttribute('aria-label', 'Execution details');
  historyRoot.append(filters, historyStatus, historyList, pages, detailPanel);
  loadHistory();
  if (currentRunId) loadDetail(currentRunId);
}

async function loadHistory() {
  if (!historyList) return;
  const version = ++historyVersion;
  const params = new URLSearchParams();
  if (jobFilter.value) params.set('job_id', jobFilter.value);
  if (statusFilter.value) params.set('status', statusFilter.value);
  if (historyBefore !== null) params.set('before', historyBefore);
  historyStatus.textContent = 'Loading execution history…';
  try {
    const payload = await request(`/api/notifications/runs?${params}`);
    if (version !== historyVersion) return;
    historyList.replaceChildren();
    if (!payload.runs.length) historyList.append(el('p', 'notification-empty', 'No matching executions. History begins with the first recorded task.'));
    for (const run of payload.runs) {
      const card = el('article', 'notification-run');
      const heading = el('div', 'notification-run-head');
      const open = button(title(run), () => {
        currentRunId = run.run_id;
        window.history.replaceState(null, '', `/notifications.html?run=${encodeURIComponent(run.run_id)}`);
        loadDetail(run.run_id, true);
      }, 'notification-run-title');
      heading.append(open, badge(run));
      const meta = el('dl', 'notification-run-meta');
      for (const [label, value] of [['Started', when(run.started_at)], ['Finished', when(run.ended_at)], ['Duration', duration(run)], ['Triggered via', run.origin_label]]) {
        const cell = el('div');
        cell.append(el('dt', '', label), el('dd', '', value));
        meta.append(cell);
      }
      card.append(heading, meta, el('p', 'notification-muted', run.summary));
      historyList.append(card);
    }
    historyNext = payload.next_cursor;
    next.disabled = !payload.has_more;
    previous.disabled = !historyStack.length;
    historyStatus.textContent = `${payload.runs.length} executions · Times shown in your local timezone`;
    await markRead(payload.displayed_event_ids);
    if (version === historyVersion && lastReadError) historyStatus.textContent += ' · Could not mark notifications read; retry with Refresh.';
  } catch {
    if (version !== historyVersion) return;
    historyList.replaceChildren(el('p', 'notification-error', 'Execution history is unavailable. Use Refresh to retry.'));
    historyStatus.textContent = 'History could not be loaded';
    next.disabled = true;
  }
}

async function loadDetail(runId, focus = false) {
  if (!detailPanel) return;
  const version = ++detailVersion;
  detailPanel.hidden = false;
  detailPanel.replaceChildren(el('p', 'notification-muted', 'Loading execution details…'));
  try {
    const run = await request(`/api/notifications/runs/${encodeURIComponent(runId)}`);
    if (version !== detailVersion) return;
    const heading = el('h2', '', title(run));
    heading.tabIndex = -1;
    detailPanel.replaceChildren(heading, badge(run), el('p', 'notification-muted', run.summary), el('p', 'notification-muted', `Last report: ${when(run.updated_at)}`));
    if (run.log_path) detailPanel.append(el('p', 'notification-muted', `Job log: ${run.log_path}`));
    if (run.job_id === 'ticker_refresh') detailPanel.append(el('p', 'notification-muted', 'Result covers the requested context refresh. Supplementary sections may retain cached data.'));
    if (!run.children.length) detailPanel.append(el('p', 'notification-muted', 'No child-task details were reported.'));
    for (const child of run.children) {
      const row = el('div', 'notification-child');
      row.append(el('strong', '', child.label || child.name), badge(child), el('span', 'notification-muted', child.summary));
      detailPanel.append(row);
    }
    if (focus) { heading.focus(); heading.scrollIntoView({ block: 'nearest' }); }
  } catch {
    if (version === detailVersion) detailPanel.replaceChildren(el('p', 'notification-error', 'Execution details are unavailable or the run was not found.'), button('Retry details', () => loadDetail(runId, true)));
  }
}

const feed = createNotificationFeed({
  request,
  onSnapshot(snapshot) {
    feedError = false;
    applyNotificationState(snapshot);
    remember(snapshot.events);
    renderDrawer();
    setupHistory(snapshot);
  },
  onEvents(events, payload) {
    const wasOffline = feedError;
    feedError = false;
    const incoming = events.filter(event => !recent.has(event.event_id));
    applyNotificationState(payload);
    for (const event of incoming) if (!event.read && event.event_id > clearedThrough && event.event_id > readThrough) toast(event);
    if (payload.inbox_events) {
      recent.clear();
      remember(payload.inbox_events);
    } else remember(events);
    renderDrawer();
    if (events.length || wasOffline) {
      loadHistory();
      if (currentRunId) loadDetail(currentRunId);
    }
  },
  onUnread(value) { setUnread(value); renderDrawer(); },
  onError() {
    feedError = true;
    bell.classList.add('notification-unavailable');
    bell.title = 'Notifications are unavailable; retrying automatically';
    renderDrawer();
    if (historyRoot && !historyList) {
      historyRoot.replaceChildren(el('p', 'notification-error', 'Notification history is unavailable.'), button('Retry', () => feed.tick()));
    }
  },
});

function refreshVisible() {
  if (document.hidden) return;
  feed.tick().then(() => {
    if (!feedError) { bell.classList.remove('notification-unavailable'); bell.title = 'Notifications'; }
  });
}

document.addEventListener('visibilitychange', refreshVisible);
window.addEventListener('online', refreshVisible);
window.setInterval(refreshVisible, 5000);
refreshVisible();
