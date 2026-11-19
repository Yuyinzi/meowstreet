function el(document, tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function when(value, timezone = 'Asia/Shanghai') {
  if (!value) return 'Not available';
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? 'Not available' : new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: timezone, timeZoneName: 'short' }).format(parsed);
}

function period(value, basis) {
  if (!value) return 'Not available';
  const normalized = basis === 'month' && value.length === 7 ? `${value}-01` : value;
  const parsed = new Date(`${normalized}T00:00:00Z`);
  if (Number.isNaN(parsed.valueOf())) return value;
  if (basis === 'quarter') return `Q${Math.floor(parsed.getUTCMonth() / 3) + 1} ${parsed.getUTCFullYear()}`;
  return new Intl.DateTimeFormat('en-US', { month: 'short', ...(basis === 'month' ? {} : { day: 'numeric' }), year: 'numeric', timeZone: 'UTC' }).format(parsed);
}

function releaseLabel(release) {
  if (!release) return 'Not confirmed';
  if (release.precision === 'exact') return when(release.at);
  const start = period(release.at, 'date');
  return release.precision === 'window' ? `${start} – ${period(release.window_end, 'date')} (window)` : `${start} (date only)`;
}

function safeLink(document, label, href, internal = false) {
  let valid = false;
  if (internal) valid = typeof href === 'string' && /^\/notifications\.html\?run=[A-Za-z0-9%_.~-]+$/.test(href);
  else {
    try { const url = new URL(href); valid = ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password; } catch {}
  }
  if (!valid) return el(document, 'span', '', label);
  const link = el(document, 'a', '', label);
  link.href = href;
  if (!internal) { link.target = '_blank'; link.rel = 'noopener noreferrer'; }
  return link;
}

export function createFreshnessPage({ document, request }) {
  const ids = ['App', 'AsOf', 'Stats', 'Search', 'Category', 'Reset', 'Count', 'Rows', 'Message', 'Schedules', 'Reload'];
  const nodes = Object.fromEntries(ids.map(id => [id, document.getElementById(`freshness${id}`)]));
  let payload = null;
  let selected = '';
  const opened = new Set();
  const openCategories = new Set();
  const collapsedMatches = new Set();
  let activeFilter = null;
  let generation = 0;
  const e = (tag, className, text) => el(document, tag, className, text);

  function cell(text, secondary, tag = 'td') {
    const node = e(tag);
    if (tag === 'th') node.setAttribute('scope', 'row');
    node.append(e('div', '', text));
    if (secondary) node.append(e('div', 'freshness-muted', secondary));
    return node;
  }

  function definition(root, label, value) {
    root.append(e('dt', '', label), e('dd', '', value || 'Not available'));
  }

  function task(root, label, record) {
    root.append(e('h2', '', label));
    if (!record) { root.append(e('p', '', 'No recorded result')); return; }
    const line = e('p');
    line.append(safeLink(document, record.status_label || 'Unknown', record.href, true));
    root.append(line, e('p', 'freshness-muted', `${when(record.at)}${record.origin ? ` · ${record.origin === 'command_line' ? 'Command line' : record.origin === 'manual' ? 'Manual' : 'Background'}` : ''}`));
  }

  function details(row) {
    const panel = e('div', 'freshness-detail');
    const reason = e('section');
    reason.append(e('h2', '', 'Status evidence'), e('p', '', row.reason));
    const dates = e('dl');
    definition(dates, 'Current source period', row.current_period);
    definition(dates, 'Stored date / label', row.stored_period || row.current_period);
    if (row.source_observation_date) definition(dates, 'Source observation date', row.source_observation_date);
    if (row.lineage_basis) definition(dates, 'Source date verification', {captured_at_import: 'Recorded during import', reconstructed_from_cached_source: 'Verified against cached source', conflicting: 'Conflicting source evidence'}[row.lineage_basis]);
    definition(dates, 'Comparison basis', row.comparison_basis || (row.expected_release ? 'Verified publication calendar' : 'Not established'));
    if (Number.isFinite(row.source_age_days)) definition(dates, 'Source age', `${row.source_age_days} calendar days`);
    if (row.max_age_days) definition(dates, 'Allowed age', `${row.max_age_days} calendar days`);
    if (row.expected_period) definition(dates, 'Expected completed session', row.expected_period);
    if (row.policy_timezone) definition(dates, 'Monitoring timezone', row.policy_timezone);
    if (row.freshness_deadline) definition(dates, 'Monitoring deadline', row.freshness_deadline.length === 10 ? period(row.freshness_deadline, 'date') : when(row.freshness_deadline));
    definition(dates, 'Publication date', row.release_date);
    definition(dates, 'Release version', row.version);
    definition(dates, 'Source frequency', row.frequency);
    definition(dates, 'Local storage frequency', row.storage_frequency);
    definition(dates, 'Retrieved', row.retrieved_at ? when(row.retrieved_at) : null);
    reason.append(dates, safeLink(document, 'Data source ↗', row.source_url));
    const history = e('section');
    task(history, 'Last successful collection check', row.history?.last_successful_check);
    task(history, 'Latest attempt', row.history?.last_attempt);
    task(history, 'Latest import / processing result', row.history?.last_processing);
    const calendar = e('section');
    calendar.append(e('h2', '', 'Publication schedule'), e('p', '', row.schedule?.note || 'No verified publication schedule'));
    const schedule = e('dl');
    definition(schedule, 'Latest expected period', row.expected_release?.period);
    definition(schedule, 'Expected release', row.expected_release ? releaseLabel(row.expected_release) : null);
    definition(schedule, 'Next release / window', row.next_release ? releaseLabel(row.next_release) : null);
    definition(schedule, 'Source timezone', row.schedule?.timezone);
    definition(schedule, 'Verified coverage', row.schedule?.coverage_start && row.schedule?.coverage_end ? `${row.schedule.coverage_start} – ${row.schedule.coverage_end}` : null);
    definition(schedule, 'Schedule verified', row.schedule?.verified_at);
    calendar.append(schedule);
    const sources = [...new Set([row.schedule?.source_url, ...(row.schedule?.source_urls || []), row.policy_source_url].filter(Boolean))];
    if (!sources.length) calendar.append(e('p', 'freshness-muted', 'Schedule source not confirmed'));
    sources.forEach((href, index) => { const line = e('p'); line.append(safeLink(document, sources.length === 1 ? 'Schedule source ↗' : `Schedule source ${index + 1} ↗`, href)); calendar.append(line); });
    panel.append(reason, history, calendar);
    return panel;
  }

  function renderTable(rows, category) {
    const wrap = e('div', 'freshness-table-wrap');
    wrap.tabIndex = 0;
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', `${category} dataset freshness table, scroll horizontally for more columns`);
    const table = e('table', 'freshness-table');
    const head = e('thead');
    const headings = e('tr');
    for (const label of ['Dataset / source', 'Current period', 'Release frequency', 'Next release / window', 'Status', 'Last successful check', 'Details']) {
      const heading = e('th');
      heading.append(e('span', label === 'Details' ? 'freshness-sr-only' : '', label));
      heading.setAttribute('scope', 'col');
      headings.append(heading);
    }
    head.append(headings);
    const body = e('tbody');
    for (const row of rows) {
      const tr = e('tr');
      const name = cell(row.name, row.source, 'th');
      name.children[0].className = 'freshness-name';
      const badge = e('span', 'freshness-badge', row.status_label);
      badge.dataset.status = row.status;
      const badgeCell = e('td'); badgeCell.append(badge);
      const check = row.history?.last_successful_check;
      const detailRow = e('tr');
      detailRow.id = `freshness-detail-${row.id.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
      detailRow.hidden = !opened.has(row.id);
      const detailCell = e('td', 'freshness-detail-cell');
      detailCell.colSpan = 7; detailCell.append(details(row)); detailRow.append(detailCell);
      const toggle = e('button', 'freshness-expand', opened.has(row.id) ? 'Less −' : 'Details +');
      toggle.type = 'button';
      toggle.setAttribute('aria-expanded', String(!detailRow.hidden));
      toggle.setAttribute('aria-controls', detailRow.id);
      toggle.setAttribute('aria-label', `Details for ${row.name}`);
      toggle.addEventListener('click', () => {
        detailRow.hidden = !detailRow.hidden;
        if (detailRow.hidden) opened.delete(row.id); else opened.add(row.id);
        toggle.setAttribute('aria-expanded', String(!detailRow.hidden));
        toggle.textContent = detailRow.hidden ? 'Details +' : 'Less −';
      });
      const actions = e('td'); actions.append(toggle);
      tr.append(name, cell(period(row.current_period, row.period_basis), row.stored_period ? `Stored label: ${period(row.stored_period, 'date')}` : row.period_basis === 'weekly_resample' ? 'Weekly label' : ''), cell(row.frequency, row.storage_frequency !== row.frequency ? `Stored: ${row.storage_frequency}` : ''), cell(releaseLabel(row.next_release), row.next_release?.precision === 'exact' ? 'Asia/Shanghai' : row.next_release?.timezone || ''), badgeCell, cell(check ? when(check.at) : 'No recorded check'), actions);
      body.append(tr, detailRow);
    }
    table.append(head, body);
    wrap.append(table);
    return wrap;
  }

  function renderRows() {
    if (!payload) return;
    const query = nodes.Search.value.trim().toLowerCase();
    const rows = payload.datasets.filter(row => (!selected || row.status === selected) && (!nodes.Category.value || row.category === nodes.Category.value) && (!query || `${row.name} ${row.source}`.toLowerCase().includes(query)));
    const filter = JSON.stringify([selected, nodes.Category.value, query]);
    const filtering = Boolean(selected || nodes.Category.value || query);
    if (filter !== activeFilter) { collapsedMatches.clear(); activeFilter = filter; }
    const categories = [...new Set(rows.map(row => row.category))].sort((a, b) => a.localeCompare(b));
    nodes.Count.textContent = `Showing ${rows.length} of ${payload.datasets.length} datasets · ${categories.length} categories`;
    nodes.Rows.replaceChildren();
    for (const category of categories) {
      const matching = rows.filter(row => row.category === category);
      const total = payload.datasets.filter(row => row.category === category).length;
      const group = e('details', 'freshness-group');
      group.dataset.category = category;
      group.open = filtering ? !collapsedMatches.has(category) : openCategories.has(category);
      const summary = e('summary', 'freshness-group-summary');
      const heading = e('span', 'freshness-group-heading');
      const count = matching.length === total ? `${total} dataset${total === 1 ? '' : 's'}` : `${matching.length} of ${total} datasets`;
      heading.append(e('span', 'freshness-group-title', category), e('span', 'freshness-muted', count));
      const badges = e('span', 'freshness-group-badges');
      for (const status of payload.statuses) {
        const count = matching.filter(row => row.status === status.code).length;
        if (!count) continue;
        const badge = e('span', 'freshness-badge', `${status.label} ${count}`);
        badge.dataset.status = status.code;
        badges.append(badge);
      }
      summary.append(heading, badges);
      group.append(summary, renderTable(matching, category));
      group.addEventListener('toggle', () => {
        if (activeFilter !== filter) return;
        if (filtering) {
          if (group.open) collapsedMatches.delete(category); else collapsedMatches.add(category);
        } else if (group.open) openCategories.add(category); else openCategories.delete(category);
      });
      nodes.Rows.append(group);
    }
    if (!rows.length) nodes.Rows.append(e('p', 'freshness-empty', 'No matching datasets. Try another search or reset filters.'));
    for (const card of nodes.Stats.children) card.setAttribute('aria-pressed', String(selected === card.dataset.status));
  }

  function renderSnapshot() {
    nodes.AsOf.textContent = `As of ${when(payload.as_of)}`;
    nodes.Stats.replaceChildren();
    for (const status of payload.statuses) {
      const card = e('button', 'freshness-stat'); card.type = 'button'; card.dataset.status = status.code;
      card.append(e('span', 'freshness-stat-label', status.label), e('strong', '', String(payload.counts[status.code])));
      card.setAttribute('aria-pressed', String(selected === status.code));
      card.addEventListener('click', () => { selected = selected === status.code ? '' : status.code; renderRows(); });
      nodes.Stats.append(card);
    }
    const category = nodes.Category.value;
    const all = e('option', '', 'All categories'); all.value = '';
    nodes.Category.replaceChildren(all);
    for (const value of payload.categories) { const option = e('option', '', value); option.value = value; nodes.Category.append(option); }
    nodes.Category.value = payload.categories.includes(category) ? category : '';
    nodes.Schedules.replaceChildren();
    for (const schedule of payload.collection_schedules) nodes.Schedules.append(e('p', '', `${schedule.label}: ${schedule.cadence} · ${schedule.timezone}. Schedule verified ${schedule.verified_at}.`));
    renderRows();
  }

  async function reload() {
    const current = ++generation;
    nodes.App.setAttribute('aria-busy', 'true'); nodes.Reload.disabled = true;
    nodes.Message.className = ''; nodes.Message.hidden = false; nodes.Message.textContent = 'Loading data freshness…';
    try {
      const next = await request('/api/macro-data-freshness');
      if (current !== generation) return;
      if (!Array.isArray(next.datasets) || !next.datasets.length || !Array.isArray(next.statuses) || !next.counts) throw Error('Invalid inventory');
      payload = next;
      renderSnapshot();
      const messages = [];
      if (payload.unavailable_datasets) messages.push(`${payload.unavailable_datasets} dataset${payload.unavailable_datasets === 1 ? '' : 's'} could not be read. Their status is Unknown.`);
      if (!payload.history_available) messages.push('Task history is unavailable. Collection times cannot be confirmed.');
      nodes.Message.textContent = messages.join(' '); nodes.Message.hidden = !messages.length; nodes.Message.className = 'freshness-warning';
    } catch {
      if (current !== generation) return;
      nodes.Message.className = 'freshness-error'; nodes.Message.hidden = false;
      nodes.Message.textContent = `Data freshness is unavailable; retry with Reload status.${payload ? ' The previous snapshot remains visible.' : ''}`;
    } finally {
      if (current === generation) { nodes.App.setAttribute('aria-busy', 'false'); nodes.Reload.disabled = false; }
    }
  }

  nodes.Search.addEventListener('input', renderRows);
  nodes.Category.addEventListener('change', renderRows);
  nodes.Reset.addEventListener('click', () => { selected = ''; nodes.Search.value = ''; nodes.Category.value = ''; renderRows(); });
  nodes.Reload.addEventListener('click', reload);
  return { ready: reload(), reload };
}

if (typeof document !== 'undefined' && document.getElementById('freshnessApp')) {
  createFreshnessPage({ document, request: async url => {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw Error('Data freshness is unavailable');
    return response.json();
  } });
}
