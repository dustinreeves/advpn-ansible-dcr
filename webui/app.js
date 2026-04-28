const state = { hosts: [], roleByHost: {}, templatesByRole: {}, globalVars: {}, hostVars: {}, flat: [] };
const sectionsEl = document.getElementById('sections');
const hostSelect = document.getElementById('hostSelect');
const statusText = document.getElementById('statusText');

function flatten(obj, prefix = '') {
  const out = [];
  Object.entries(obj || {}).forEach(([k, v]) => {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) out.push(...flatten(v, path));
    else out.push({ path, value: v, type: Array.isArray(v) ? 'json' : typeof v });
  });
  return out;
}
function setByPath(obj, path, value) {
  const parts = path.split('.'); let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) { if (!cur[parts[i]] || typeof cur[parts[i]] !== 'object') cur[parts[i]] = {}; cur = cur[parts[i]]; }
  cur[parts[parts.length - 1]] = value;
}
function classify(path) {
  if (/^site_|^fgt_|^device_role/.test(path)) return 'General Settings';
  if (/^lan\.|^wan\.|^lo_/.test(path)) return 'Network Configuration';
  if (/^advpn\.phase|^advpn\.tunnels|^interhub|^interhub_ipsec/.test(path)) return 'VPN / Tunnel Configuration';
  if (/^bgp\.|^advpn\.bgp|route_map/.test(path)) return 'BGP Configuration';
  if (/^advpn\.sdwan|^sdwan_/.test(path)) return 'SD-WAN Configuration';
  if (/policy|firewall/.test(path)) return 'Firewall Policies';
  return 'General Settings';
}
function fieldHTML(item, idx) {
  if (item.type === 'boolean') return `<div class="field"><label>${item.path}</label><input data-idx="${idx}" type="checkbox" ${item.value ? 'checked' : ''}></div>`;
  if (item.type === 'number') return `<div class="field"><label>${item.path}</label><input data-idx="${idx}" type="number" value="${item.value}"></div>`;
  if (item.type === 'json' || item.type === 'object') return `<div class="field"><label>${item.path}</label><textarea data-idx="${idx}">${JSON.stringify(item.value ?? null, null, 2)}</textarea></div>`;
  return `<div class="field"><label>${item.path}</label><input data-idx="${idx}" type="text" value="${String(item.value ?? '').replaceAll('"','&quot;')}"></div>`;
}
function renderSections() {
  const grouped = {};
  state.flat.forEach((item, idx) => {
    const section = classify(item.path);
    if (!grouped[section]) grouped[section] = [];
    grouped[section].push({ ...item, idx });
  });
  sectionsEl.innerHTML = '';

  Object.entries(grouped).forEach(([name, items], sectionIndex) => {
    const isNetwork = name === 'Network Configuration';
    const card = document.createElement('section');
    card.className = 'section card';
    card.innerHTML = `<div class="section-head"><h3>${name}</h3><button data-collapse="${sectionIndex}">Toggle</button></div><div class="section-body" id="body-${sectionIndex}"></div>`;
    sectionsEl.appendChild(card);
    const body = card.querySelector(`#body-${sectionIndex}`);

    if (isNetwork) {
      const tabs = document.createElement('div');
      tabs.className = 'net-tabs';
      tabs.innerHTML = `<button class="net-tab active" data-tab="interfaces">Interfaces</button><button class="net-tab" data-tab="tunnels">Tunnels</button><button class="net-tab" data-tab="loopbacks">Loopbacks</button><button class="net-tab" data-tab="management">Management</button>`;
      body.before(tabs);
      const map = {
        interfaces: items.filter(i => /^wan\.|^lan\./.test(i.path)),
        tunnels: state.flat.filter(i => /^advpn\.tunnels|^interhub/.test(i.path)),
        loopbacks: items.filter(i => /^lo_/.test(i.path)),
        management: state.flat.filter(i => /^site_|^fgt_/.test(i.path)),
      };
      const paint = (key) => { body.innerHTML = map[key].map((x) => fieldHTML(x, x.idx)).join(''); };
      paint('interfaces');
      tabs.querySelectorAll('.net-tab').forEach(btn => btn.addEventListener('click', () => {
        tabs.querySelectorAll('.net-tab').forEach(x => x.classList.remove('active')); btn.classList.add('active'); paint(btn.dataset.tab);
      }));
    } else {
      body.innerHTML = items.map(x => fieldHTML(x, x.idx)).join('');
    }
  });

  document.querySelectorAll('[data-collapse]').forEach(btn => btn.addEventListener('click', () => {
    const body = document.getElementById(`body-${btn.dataset.collapse}`);
    body.classList.toggle('hidden');
  }));
}
function collectVars() {
  const merged = {};
  state.flat.forEach((item, idx) => {
    const el = document.querySelector(`[data-idx="${idx}"]`);
    if (!el) return;
    let v;
    if (item.type === 'boolean') v = el.checked;
    else if (item.type === 'number') v = Number(el.value);
    else if (item.type === 'json' || item.type === 'object') v = JSON.parse(el.value || 'null');
    else v = el.value;
    setByPath(merged, item.path, v);
  });
  return merged;
}

async function api(path, opts = {}) { const r = await fetch(path, opts); const d = await r.json(); if (!r.ok) throw new Error(d.error || 'request failed'); return d; }
async function init() {
  const hosts = await api('/api/hosts');
  const templates = await api('/api/templates');
  state.hosts = hosts.hosts; state.roleByHost = hosts.role_by_host || {}; state.templatesByRole = templates.templates_by_role || {};
  hostSelect.innerHTML = state.hosts.map(h => `<option value="${h}">${h}</option>`).join('');
  await loadHost();
}
async function loadHost() {
  const host = hostSelect.value;
  const data = await api(`/api/vars?host=${encodeURIComponent(host)}`);
  state.globalVars = data.global_vars || {};
  state.hostVars = data.host_vars || {};
  state.flat = [...flatten(state.globalVars), ...flatten(state.hostVars)];
  renderSections();
  updateJsonPreview();
  statusText.textContent = `Loaded ${host} (${data.device_role || 'unknown'})`;
}
function updateJsonPreview() { document.getElementById('jsonPreview').textContent = JSON.stringify(collectVars(), null, 2); }

async function previewConfiguration() {
  try {
    updateJsonPreview();
    const payload = { host: hostSelect.value, global_vars: state.globalVars, host_vars: collectVars() };
    const mode = document.getElementById('renderMode').value;
    let out;
    if (mode === 'ansible') {
      out = await api('/api/render', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    } else {
      const role = state.roleByHost[payload.host] || 'branch';
      const templates = state.templatesByRole[role] || [];
      const merged = payload.host_vars;
      const chunks = [];
      templates.forEach(t => {
        const ctx = { ...merged, ...(t.context || {}) };
        chunks.push(`# --- ${t.name} ---\n${nunjucks.renderString(t.content, ctx)}`);
      });
      out = { rendered_config: chunks.join('\n\n') };
    }
    document.getElementById('cliPreview').value = out.rendered_config || '';
    statusText.textContent = 'Preview generated.';
  } catch (err) { statusText.textContent = err.message; }
}

function saveTemplate() {
  const name = document.getElementById('templateName').value.trim() || 'default-template';
  localStorage.setItem(`advpn:${name}`, JSON.stringify({ host: hostSelect.value, vars: collectVars() }));
  statusText.textContent = `Saved template ${name}`;
}
function copyPreview() { navigator.clipboard.writeText(document.getElementById('cliPreview').value || ''); statusText.textContent = 'Copied preview.'; }
function downloadPreview() {
  const name = (document.getElementById('templateName').value || 'advpn-config') + '.conf';
  const blob = new Blob([document.getElementById('cliPreview').value || ''], { type: 'text/plain' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click();
}

hostSelect.addEventListener('change', loadHost);
document.getElementById('loadBtn').addEventListener('click', loadHost);
document.getElementById('saveBtn').addEventListener('click', saveTemplate);
document.getElementById('previewBtn').addEventListener('click', previewConfiguration);
document.getElementById('copyBtn').addEventListener('click', copyPreview);
document.getElementById('downloadBtn').addEventListener('click', downloadPreview);
document.getElementById('themeToggle').addEventListener('change', (e) => document.body.className = e.target.checked ? 'theme-dark' : '');
document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active')); btn.classList.add('active');
  const cli = btn.dataset.view === 'cli';
  document.getElementById('jsonPreview').classList.toggle('hidden', cli);
  document.getElementById('cliPreview').classList.toggle('hidden', !cli);
}));

setInterval(updateJsonPreview, 1200);
init().catch(err => statusText.textContent = err.message);
