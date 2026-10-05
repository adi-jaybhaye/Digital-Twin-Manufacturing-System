/**
 * app.js — Digital Twin Manufacturing System Frontend
 * 
 * This file handles:
 *  - Page navigation (sidebar)
 *  - API polling every 2 seconds for real-time updates
 *  - WebSocket connection for live data
 *  - Chart rendering and updates (Chart.js)
 *  - Machine card rendering
 *  - Production flow visualization
 *  - Bottleneck detection display
 *  - OEE display
 *  - What-If analysis UI
 *  - Event log streaming
 *  - Simulation controls
 */

// ─── API Configuration ─────────────────────────────────────────────
const API_BASE = window.location.origin.includes('http') ? window.location.origin : "http://localhost:8000";
let pollInterval = null;
let wsConnection  = null;
let lastData      = null;

// ─── Charts ────────────────────────────────────────────────────────
let utilizationChart   = null;
let throughputChart    = null;
let oeeChart           = null;
let stateDistChart     = null;
let workloadChart      = null;
let whatifChart        = null;
let throughputHistory  = [];   // [{label, value}] for throughput chart
let bottleneckHistory  = [];   // For historical tracking

// ─── State ────────────────────────────────────────────────────────
let baselineSnapshot  = null;
let whatifData        = null;
let currentPage       = 'dashboard';
let simRunning        = false;
let simPaused         = false;

// ─────────────────────────────────────────────────────────────────
// NAVIGATION
// ─────────────────────────────────────────────────────────────────

function showPage(pageId) {
  document.querySelectorAll('.page-section').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const page = document.getElementById(`page-${pageId}`);
  if (page) page.classList.add('active');

  const navItem = document.querySelector(`[data-page="${pageId}"]`);
  if (navItem) navItem.classList.add('active');

  currentPage = pageId;

  // Lazy-init charts when their page becomes visible
  if (pageId === 'dashboard'   && !utilizationChart) initDashboardCharts();
  if (pageId === 'bottleneck'  && !stateDistChart)   initBottleneckCharts();
  if (pageId === 'oee'         && !oeeChart)         initOEEChart();
  if (pageId === 'whatif'      && !whatifChart)      initWhatIfChart();
  if (pageId === 'history')    { loadHistory(); loadWhatIfHistory(); }
}

// ─────────────────────────────────────────────────────────────────
// API HELPERS
// ─────────────────────────────────────────────────────────────────

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

async function apiPost(path, body = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API POST ${path} → ${res.status}`);
  return res.json();
}

// ─────────────────────────────────────────────────────────────────
// WEBSOCKET (real-time)
// ─────────────────────────────────────────────────────────────────

function connectWebSocket() {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsHost = window.location.host || 'localhost:8000';
  wsConnection = new WebSocket(`${wsProtocol}//${wsHost}/ws/live`);

  wsConnection.onopen = () => {
    stopPolling();
  };

  wsConnection.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateDashboard(data);
  };

  wsConnection.onerror = () => {
    // Fall back to polling
    wsConnection = null;
    startPolling();
  };

  wsConnection.onclose = () => {
    wsConnection = null;
    startPolling();
    setTimeout(connectWebSocket, 2000);
  };
}

function startPolling() {
  if (pollInterval) return;
  pollInterval = setInterval(async () => {
    try {
      const data = await apiGet('/api/dashboard');
      updateDashboard(data);
    } catch (e) {
      console.warn('Poll error:', e.message);
    }
  }, 1000);
}

function stopPolling() {
  if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
}

// ─────────────────────────────────────────────────────────────────
// MAIN DASHBOARD UPDATE
// ─────────────────────────────────────────────────────────────────

function updateDashboard(data) {
  lastData = data;
  const { status, machines, throughput, bottleneck, oee, workload, products, event_log } = data;

  // Update simulation status
  simRunning = status.is_running;
  simPaused  = status.is_paused;
  updateSimStatusUI(status);

  // Summary stats
  updateSummaryStats(status, throughput, bottleneck, oee, machines);

  // Machine cards
  updateMachineCards(machines);

  // Production flow
  updateFlowVisualization(machines);

  // Charts (only update if chart exists)
  if (utilizationChart) updateUtilizationChart(machines);
  if (throughput)       updateThroughputHistory(throughput);
  if (stateDistChart)   updateStateDistChart(machines);
  if (workloadChart)    updateWorkloadChart(workload);
  if (oeeChart)         updateOEEChart(oee);

  // Bottleneck page
  updateBottleneckDisplay(bottleneck, machines);

  // OEE display
  updateOEEDisplay(oee);

  // Workload bars
  updateWorkloadBars(workload);

  // Products table
  updateProductsTable(products);

  // Event log
  updateEventLog(event_log);

  // What-if page
  if (currentPage === 'whatif') refreshWhatIfDisplay();

  // Controls state
  updateControlButtons(status);
}

// ─────────────────────────────────────────────────────────────────
// SIMULATION STATUS UI
// ─────────────────────────────────────────────────────────────────

function updateSimStatusUI(status) {
  // Header status
  const dot    = document.getElementById('status-dot');
  const label  = document.getElementById('status-label');
  const simTime = document.getElementById('header-sim-time');

  if (!status.is_running) {
    dot.className = 'status-dot stopped';
    label.textContent = 'STOPPED';
  } else if (status.is_paused) {
    dot.className = 'status-dot paused';
    label.textContent = 'PAUSED';
  } else {
    dot.className = 'status-dot running';
    label.textContent = 'RUNNING';
  }

  if (simTime) simTime.textContent = status.sim_time_str || '00:00:00';

  // Parallel drilling badge
  const drillBadge = document.getElementById('parallel-drill-badge');
  if (drillBadge) {
    drillBadge.style.display = status.parallel_drilling ? 'inline-flex' : 'none';
  }
}

function updateControlButtons(status) {
  const btnStart  = document.getElementById('btn-start');
  const btnPause  = document.getElementById('btn-pause');
  const btnResume = document.getElementById('btn-resume');
  const btnStop   = document.getElementById('btn-stop');
  const btnReset  = document.getElementById('btn-reset');

  if (!btnStart) return;

  const running = status.is_running;
  const paused  = status.is_paused;

  btnStart.disabled  = running && !paused;
  btnPause.disabled  = !running || paused;
  btnResume.disabled = !paused;
  btnStop.disabled   = !running;
  btnReset.disabled  = running && !paused;
}

// ─────────────────────────────────────────────────────────────────
// SUMMARY STATS
// ─────────────────────────────────────────────────────────────────

function updateSummaryStats(status, throughput, bottleneck, oee, machines) {
  setText('stat-total-production', throughput?.total_completed ?? 0);
  setText('stat-throughput',       `${throughput?.per_hour_sim?.toFixed(0) ?? 0} /hr`);
  setText('stat-oee',              `${oee?.system_oee?.toFixed(1) ?? 0}%`);
  setText('stat-bottleneck',       bottleneck?.machine_name ?? 'None (System Idle)');
  setText('stat-in-progress',      status?.in_progress ?? 0);
  setText('stat-in-progress-2',    status?.in_progress ?? 0);
  setText('stat-rejected',         throughput?.total_rejected ?? 0);
  setText('stat-rejected-2',       throughput?.total_rejected ?? 0);
  setText('stat-breakdowns',       machines?.reduce((s, m) => s + (m.breakdown_count || 0), 0) ?? 0);

  // Avg utilization
  const avgUtil = machines?.length
    ? (machines.reduce((s, m) => s + (m.utilization || 0), 0) / machines.length).toFixed(1)
    : '0.0';
  setText('stat-avg-util', `${avgUtil}%`);

  // Sim time
  setText('stat-sim-time', status?.sim_time_str ?? '00:00:00');
  setText('stat-completed', throughput?.total_completed ?? 0);

  // Last update timestamp in UI header
  const lu = document.getElementById('last-update-time');
  if (lu) lu.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;

  // Sync bottleneck card on bottleneck page
  const card2 = document.getElementById('bottleneck-summary-card-2');
  if (card2 && bottleneck?.bottleneck) {
    card2.innerHTML = document.getElementById('bottleneck-summary-card')?.innerHTML || '';
  }
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ─────────────────────────────────────────────────────────────────
// MACHINE CARDS
// ─────────────────────────────────────────────────────────────────

const MACHINE_ICONS = {
  cutting:    '<i class="ri-scissors-2-line"></i>',
  turning:    '<i class="ri-disc-line"></i>',
  drilling:   '<i class="ri-tools-line"></i>',
  inspection: '<i class="ri-microscope-line"></i>',
  packaging:  '<i class="ri-inbox-archive-line"></i>',
};

function updateMachineCards(machines) {
  if (!machines?.length) return;

  // Get bottleneck machine code
  const bottleneckCode = lastData?.bottleneck?.bottleneck;

  ['digital-twin', 'machines'].forEach(section => {
    const container = document.getElementById(`${section}-machine-cards`);
    if (!container) return;

    container.innerHTML = machines.map(m => renderMachineCard(m, bottleneckCode)).join('');
  });
}

function renderMachineCard(m, bottleneckCode) {
  const isBottleneck = m.machine_code === bottleneckCode;
  const icon = MACHINE_ICONS[m.station] || '<i class="ri-cpu-line"></i>';
  const stateColors = { BUSY: '#00bcd4', IDLE: '#94a3b8', BLOCKED: '#069494', BREAKDOWN: '#FF69B4' };
  const fillColor = stateColors[m.state] || '#94a3b8';

  return `
    <div class="machine-card${isBottleneck ? ' bottleneck' : ''}">
      <div class="machine-card-header">
        <div class="machine-icon">${icon}</div>
        <div class="machine-info">
          <div class="machine-name">${m.machine_name}</div>
          <div class="machine-station">${m.station.toUpperCase()} · Order ${m.station_order}</div>
          ${m.is_parallel ? '<span class="badge badge-blue" style="margin-top:4px;font-size:9px;">PARALLEL</span>' : ''}
        </div>
        <span class="state-badge ${m.state}">${m.state}</span>
      </div>

      ${isBottleneck ? '<div class="bottleneck-tag"><i class="ri-alert-line"></i> BOTTLENECK</div>' : ''}

      <div class="util-bar-wrap">
        <div class="util-bar-label">
          <span>Utilization</span>
          <span class="fw-700" style="color:${fillColor}">${m.utilization?.toFixed(1)}%</span>
        </div>
        <div class="util-bar-track">
          <div class="util-bar-fill" style="width:${m.utilization}%;background:${fillColor}"></div>
        </div>
      </div>

      <div class="machine-stats">
        <div class="machine-stat-item">
          <div class="label">Busy</div>
          <div class="value text-cyan">${m.busy_pct?.toFixed(1)}%</div>
        </div>
        <div class="machine-stat-item">
          <div class="label">Idle</div>
          <div class="value text-muted">${m.idle_pct?.toFixed(1)}%</div>
        </div>
        <div class="machine-stat-item">
          <div class="label">Blocked</div>
          <div class="value text-teal">${m.blocked_pct?.toFixed(1)}%</div>
        </div>
        <div class="machine-stat-item">
          <div class="label">Breakdown</div>
          <div class="value text-pink">${m.breakdown_pct?.toFixed(1)}%</div>
        </div>
      </div>

      <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border-subtle)">
        <div style="display:flex;justify-content:space-between;font-size:12px;">
          <span class="text-muted">Units Processed:</span>
          <span class="fw-700 text-white">${m.units_processed}</span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:4px;">
          <span class="text-muted">Breakdowns:</span>
          <span class="fw-700 text-pink">${m.breakdown_count}</span>
        </div>
        ${m.current_product ? `
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:4px;">
          <span class="text-muted">Current Job:</span>
          <span class="fw-700 text-mono text-cyan">${m.current_product}</span>
        </div>` : ''}
      </div>
    </div>
  `;
}

// ─────────────────────────────────────────────────────────────────
// PRODUCTION FLOW VISUALIZATION
// ─────────────────────────────────────────────────────────────────

const FLOW_STATIONS = [
  { key: 'raw',        label: 'Raw Material', icon: '<i class="ri-stack-line"></i>',          machine: null },
  { key: 'cutting',    label: 'Cutting',      icon: '<i class="ri-scissors-2-line"></i>',    machine: 'M_CUT' },
  { key: 'turning',    label: 'Turning',      icon: '<i class="ri-disc-line"></i>',          machine: 'M_TURN' },
  { key: 'drilling',   label: 'Drilling',     icon: '<i class="ri-tools-line"></i>',         machine: 'M_DRILL_1' },
  { key: 'inspection', label: 'Inspection',   icon: '<i class="ri-microscope-line"></i>',    machine: 'M_INSP' },
  { key: 'packaging',  label: 'Packaging',    icon: '<i class="ri-inbox-archive-line"></i>', machine: 'M_PACK' },
  { key: 'finished',   label: 'Finished',     icon: '<i class="ri-checkbox-circle-line"></i>', machine: null },
];

function updateFlowVisualization(machines) {
  const machineMap = {};
  machines?.forEach(m => { machineMap[m.machine_code] = m; });

  let html = '';
  FLOW_STATIONS.forEach((station, i) => {
    const m = station.machine ? machineMap[station.machine] : null;
    const state = m ? m.state : 'IDLE';
    const util = m ? m.utilization?.toFixed(0) : '—';
    const product = m ? m.current_product : null;

    html += `
      <div class="flow-node">
        <div class="flow-node-box ${state}" title="${station.label}: ${state}">
          <span class="flow-node-icon">${station.icon}</span>
          ${product ? `<div style="font-size:9px;font-family:var(--font-mono);color:var(--accent-cyan);position:absolute;bottom:4px;">${product}</div>` : ''}
        </div>
        <div class="flow-node-name">${station.label}</div>
        ${m ? `<div class="flow-node-util" style="color:${state==='BUSY'?'var(--pop-cyan)':state==='BREAKDOWN'?'var(--pop-pink)':state==='BLOCKED'?'var(--pop-teal)':'var(--text-muted)'}">${util}%</div>` : ''}
      </div>
    `;

    if (i < FLOW_STATIONS.length - 1) {
      html += `<div class="flow-arrow"><i class="ri-arrow-right-s-line"></i></div>`;
    }
  });

  // Update BOTH flow containers — Dashboard page and Digital Twin View page
  const dashFlow = document.getElementById('production-flow');
  if (dashFlow) dashFlow.innerHTML = html;

  const dtFlow = document.getElementById('digital-twin-flow');
  if (dtFlow) dtFlow.innerHTML = html;
}

// ─────────────────────────────────────────────────────────────────
// BOTTLENECK DISPLAY
// ─────────────────────────────────────────────────────────────────

function updateBottleneckDisplay(bottleneck, machines) {
  // Summary card in dashboard
  const summaryEl = document.getElementById('bottleneck-summary-card');
  if (summaryEl && bottleneck?.bottleneck) {
    summaryEl.innerHTML = `
      <div class="bottleneck-card">
        <div class="bottleneck-icon"><i class="ri-alarm-warning-line"></i></div>
        <div class="bottleneck-info">
          <h3>BOTTLENECK DETECTED: ${bottleneck.machine_name}</h3>
          <p>Station: ${bottleneck.station?.toUpperCase()} · State: ${bottleneck.state}</p>
          <p style="margin-top:4px;font-size:11px;color:var(--text-muted)">Highest utilization machine = production constraint</p>
        </div>
        <div class="bottleneck-util">
          <div class="value">${bottleneck.utilization?.toFixed(1)}%</div>
          <div class="label">Busy Utilization</div>
        </div>
      </div>
    `;
  }

  // Bottleneck analysis page
  const pageEl = document.getElementById('bottleneck-detail');
  if (pageEl && bottleneck) {
    pageEl.innerHTML = `
      <div style="margin-bottom:20px;">
        <div style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
          <strong style="color:var(--text-primary)">Detection Method:</strong>
          Utilization = Busy Time / Total Available Time × 100<br>
          The machine with the highest utilization percentage is the primary bottleneck
          (consistent with the research paper approach).
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;">
          ${machines?.map(m => `
            <div style="background:var(--bg-panel);border-radius:8px;padding:14px;border:1px solid ${m.machine_code === bottleneck.bottleneck ? 'rgba(255,105,180,0.6)' : 'var(--border-subtle)'};">
              <div style="font-weight:700;color:${m.machine_code === bottleneck.bottleneck ? 'var(--pop-pink)' : 'var(--text-primary)'}">
                ${m.machine_name}
                ${m.machine_code === bottleneck.bottleneck ? ' <i class="ri-alert-fill" style="color:var(--pop-pink);font-size:14px;vertical-align:-1px;"></i>' : ''}
              </div>
              <div style="font-size:28px;font-weight:800;font-family:var(--font-mono);margin:8px 0;color:${m.machine_code === bottleneck.bottleneck ? 'var(--pop-pink)' : 'var(--pop-teal)'}">
                ${m.utilization?.toFixed(1)}%
              </div>
              <div class="util-bar-track">
                <div class="util-bar-fill" style="width:${m.utilization}%;background:${m.machine_code === bottleneck.bottleneck ? 'var(--pop-pink)' : 'linear-gradient(90deg, var(--pop-teal), var(--pop-cyan))'}"></div>
              </div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:6px;">
                Busy: ${m.busy_pct?.toFixed(1)}% · Idle: ${m.idle_pct?.toFixed(1)}%
              </div>
            </div>
          `).join('') ?? ''}
        </div>
      </div>
    `;
  }
}

// ─────────────────────────────────────────────────────────────────
// OEE DISPLAY
// ─────────────────────────────────────────────────────────────────

function updateOEEDisplay(oee) {
  if (!oee) return;

  const container = document.getElementById('oee-machines-grid');
  if (!container) return;

  const entries = Object.entries(oee.machines || {});
  container.innerHTML = entries.map(([code, data]) => {
    const colour = data.oee >= 65 ? '#00F0FF' : data.oee >= 40 ? '#069494' : '#FF69B4';
    const circumference = 2 * Math.PI * 42;
    const dash = circumference - (data.oee / 100) * circumference;

    return `
      <div class="oee-card">
        <div class="oee-machine-name">${code.replace('M_', '').replace('_', ' ')}</div>
        <div class="oee-ring-container">
          <svg class="oee-svg" width="100" height="100" viewBox="0 0 100 100">
            <circle class="oee-track" cx="50" cy="50" r="42"/>
            <circle class="oee-fill" cx="50" cy="50" r="42"
              stroke="${colour}"
              stroke-dasharray="${circumference}"
              stroke-dashoffset="${dash}"/>
          </svg>
          <div class="oee-value">${data.oee?.toFixed(0)}%</div>
        </div>
        <div class="oee-components">
          <div class="oee-component">
            <div class="comp-val">${data.availability?.toFixed(0)}%</div>
            <div>Avail</div>
          </div>
          <div class="oee-component">
            <div class="comp-val">${data.performance?.toFixed(0)}%</div>
            <div>Perf</div>
          </div>
          <div class="oee-component">
            <div class="comp-val">${data.quality?.toFixed(0)}%</div>
            <div>Qual</div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  setText('system-oee-value', `${oee.system_oee?.toFixed(1)}%`);
}

// ─────────────────────────────────────────────────────────────────
// WORKLOAD BARS
// ─────────────────────────────────────────────────────────────────

const WORKLOAD_COLOURS = ['#FF69B4', '#00F0FF', '#069494', '#FFFFFF', '#ff85c8', '#00c4d4'];

function updateWorkloadBars(workload) {
  const container = document.getElementById('workload-bars');
  if (!container || !workload) return;

  container.innerHTML = workload.map((w, i) => `
    <div class="workload-bar-item">
      <div class="workload-machine">${w.machine_name}</div>
      <div class="workload-track">
        <div class="workload-fill" style="width:${w.workload_pct}%;background:${WORKLOAD_COLOURS[i % WORKLOAD_COLOURS.length]}"></div>
      </div>
      <div class="workload-pct">${w.workload_pct?.toFixed(1)}%</div>
    </div>
  `).join('');
}

// ─────────────────────────────────────────────────────────────────
// PRODUCTS TABLE
// ─────────────────────────────────────────────────────────────────

function updateProductsTable(products) {
  const tbody = document.getElementById('products-tbody');
  if (!tbody) return;

  if (!products?.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:30px;">No active products — start the simulation</td></tr>';
    return;
  }

  tbody.innerHTML = products.slice(0, 20).map(p => `
    <tr>
      <td><span class="product-code">${p.product_code}</span></td>
      <td>${p.current_station?.toUpperCase()}</td>
      <td><span class="state-badge ${p.status === 'in_progress' ? 'BUSY' : 'IDLE'}">${p.status}</span></td>
      <td>${p.total_processing?.toFixed(1)}s</td>
      <td>${p.assigned_machine || '—'}</td>
      <td><span class="badge badge-${p.quality_status === 'good' ? 'green' : p.quality_status === 'defective' ? 'red' : 'gray'}">${p.quality_status}</span></td>
    </tr>
  `).join('');
}

// ─────────────────────────────────────────────────────────────────
// EVENT LOG
// ─────────────────────────────────────────────────────────────────

function updateEventLog(events) {
  if (!events) return;
  const itemsHtml = events.slice(0, 60).map(e => `
    <div class="event-item ${e.severity || 'info'}">
      <span class="event-time">${e.time}</span>
      <span class="event-msg">${e.message}</span>
    </div>
  `).join('');

  const container1 = document.getElementById('event-log');
  if (container1) container1.innerHTML = itemsHtml;

  const container2 = document.getElementById('event-log-2');
  if (container2) container2.innerHTML = itemsHtml;
}

// ─────────────────────────────────────────────────────────────────
// CHARTS (Chart.js)
// ─────────────────────────────────────────────────────────────────

const CHART_DEFAULTS = {
  plugins: {
    legend: { labels: { color: '#334155', font: { family: 'Plus Jakarta Sans', size: 11, weight: '600' } } },
    tooltip: {
      backgroundColor: '#0F172A',
      borderColor: '#E2E8F0',
      borderWidth: 1,
      titleColor: '#FFFFFF',
      bodyColor: '#E2E8F0',
      padding: 10,
      cornerRadius: 8,
    }
  },
  scales: {
    x: {
      ticks: { color: '#64748B', font: { family: 'Plus Jakarta Sans', size: 11 } },
      grid: { color: '#F1F5F9' },
    },
    y: {
      ticks: { color: '#64748B', font: { family: 'Plus Jakarta Sans', size: 11 } },
      grid: { color: '#F1F5F9' },
    }
  }
};

function initDashboardCharts() {
  // Utilization Bar Chart
  const ctx1 = document.getElementById('chart-utilization');
  if (ctx1) {
    utilizationChart = new Chart(ctx1, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [{
          label: 'Utilization (%)',
          data: [],
          backgroundColor: ['#86373E', '#B4432D', '#F1BD78', '#A2434B', '#17222B'],
          borderRadius: 6,
          borderSkipped: false,
        }]
      },
      options: {
        ...CHART_DEFAULTS,
        plugins: { ...CHART_DEFAULTS.plugins, legend: { display: false } },
        scales: {
          ...CHART_DEFAULTS.scales,
          y: { ...CHART_DEFAULTS.scales.y, max: 100, title: { display: true, text: 'Utilization %', color: '#86373E' } }
        }
      }
    });
  }

  // Throughput Line Chart
  const ctx2 = document.getElementById('chart-throughput');
  if (ctx2) {
    throughputChart = new Chart(ctx2, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Completed Products',
          data: [],
          borderColor: '#86373E',
          backgroundColor: 'rgba(134, 55, 62, 0.08)',
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: '#B4432D',
          pointBorderColor: '#FFFFFF',
          pointBorderWidth: 1.5,
        }]
      },
      options: {
        ...CHART_DEFAULTS,
        plugins: { ...CHART_DEFAULTS.plugins },
        scales: {
          ...CHART_DEFAULTS.scales,
          y: { ...CHART_DEFAULTS.scales.y, title: { display: true, text: 'Units', color: '#86373E' } }
        }
      }
    });
  }
}

function initBottleneckCharts() {
  // State distribution Doughnut
  const ctx = document.getElementById('chart-state-dist');
  if (ctx) {
    stateDistChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['BUSY', 'IDLE', 'BLOCKED', 'BREAKDOWN'],
        datasets: [{
          data: [0, 0, 0, 0],
          backgroundColor: ['#B4432D', '#7A8690', '#F1BD78', '#86373E'],
          borderWidth: 0,
          hoverOffset: 6,
        }]
      },
      options: {
        cutout: '65%',
        plugins: { legend: { labels: { color: '#17222B', font: { family: 'Plus Jakarta Sans', size: 11, weight: '600' } } } }
      }
    });
  }

  // Workload bar chart on bottleneck page
  const ctx2 = document.getElementById('chart-workload');
  if (ctx2) {
    workloadChart = new Chart(ctx2, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [{
          label: 'Units Processed',
          data: [],
          backgroundColor: ['#86373E', '#B4432D', '#F1BD78', '#A2434B', '#17222B'],
          borderRadius: 6,
        }]
      },
      options: { ...CHART_DEFAULTS, plugins: { ...CHART_DEFAULTS.plugins, legend: { display: false } } }
    });
  }
}

function initOEEChart() {
  const ctx = document.getElementById('chart-oee-bar');
  if (ctx) {
    oeeChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [
          { label: 'Availability', data: [], backgroundColor: '#B4432D', borderRadius: 4 },
          { label: 'Performance',  data: [], backgroundColor: '#F1BD78', borderRadius: 4 },
          { label: 'Quality',      data: [], backgroundColor: '#86373E', borderRadius: 4 },
          { label: 'OEE',          data: [], backgroundColor: '#17222B', borderRadius: 4 },
        ]
      },
      options: {
        ...CHART_DEFAULTS,
        scales: {
          ...CHART_DEFAULTS.scales,
          y: { ...CHART_DEFAULTS.scales.y, max: 100, title: { display: true, text: '%', color: '#86373E' } }
        }
      }
    });
  }
}

function initWhatIfChart() {
  const ctx = document.getElementById('chart-whatif-comparison');
  if (ctx) {
    whatifChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Throughput /hr', 'Drilling Util %', 'System OEE %'],
        datasets: [
          { label: 'Baseline',  data: [0, 0, 0], backgroundColor: 'rgba(241, 189, 120, 0.85)', borderRadius: 6 },
          { label: 'Modified',  data: [0, 0, 0], backgroundColor: 'rgba(134, 55, 62, 0.90)', borderRadius: 6 },
        ]
      },
      options: { ...CHART_DEFAULTS }
    });
  }
}

function updateUtilizationChart(machines) {
  if (!utilizationChart) return;
  utilizationChart.data.labels   = machines.map(m => m.machine_name.replace(' Machine', '').replace(' Station', ''));
  utilizationChart.data.datasets[0].data = machines.map(m => m.utilization?.toFixed(1));
  utilizationChart.update('none');
}

function updateThroughputHistory(throughput) {
  if (!throughputChart) return;
  const now = new Date().toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  throughputHistory.push({ label: now, value: throughput.total_completed });
  if (throughputHistory.length > 30) throughputHistory.shift();

  throughputChart.data.labels   = throughputHistory.map(d => d.label);
  throughputChart.data.datasets[0].data = throughputHistory.map(d => d.value);
  throughputChart.update('none');
}

function updateStateDistChart(machines) {
  if (!stateDistChart) return;
  let busy = 0, idle = 0, blocked = 0, breakdown = 0, count = machines.length || 1;
  machines.forEach(m => {
    busy      += m.busy_pct || 0;
    idle      += m.idle_pct || 0;
    blocked   += m.blocked_pct || 0;
    breakdown += m.breakdown_pct || 0;
  });
  stateDistChart.data.datasets[0].data = [
    (busy / count).toFixed(1),
    (idle / count).toFixed(1),
    (blocked / count).toFixed(1),
    (breakdown / count).toFixed(1),
  ];
  stateDistChart.update('none');
}

function updateWorkloadChart(workload) {
  if (!workloadChart) return;
  workloadChart.data.labels   = workload.map(w => w.machine_name.replace(' Machine', '').replace(' Station', ''));
  workloadChart.data.datasets[0].data = workload.map(w => w.units);
  workloadChart.update('none');
}

function updateOEEChart(oee) {
  if (!oeeChart) return;
  const entries = Object.entries(oee.machines || {});
  oeeChart.data.labels               = entries.map(([k]) => k.replace('M_', ''));
  oeeChart.data.datasets[0].data     = entries.map(([, v]) => v.availability?.toFixed(1));
  oeeChart.data.datasets[1].data     = entries.map(([, v]) => v.performance?.toFixed(1));
  oeeChart.data.datasets[2].data     = entries.map(([, v]) => v.quality?.toFixed(1));
  oeeChart.data.datasets[3].data     = entries.map(([, v]) => v.oee?.toFixed(1));
  oeeChart.update('none');
}

// ─────────────────────────────────────────────────────────────────
// WHAT-IF ANALYSIS
// ─────────────────────────────────────────────────────────────────

async function addParallelDrillingMachine() {
  const btn = document.getElementById('btn-add-parallel');
  if (btn) btn.disabled = true;

  showToast('Adding parallel drilling machine...', 'info');

  try {
    const result = await apiPost('/api/what-if/add-drilling-machine');
    if (result.success) {
      baselineSnapshot = result.data?.baseline_snapshot;
      showToast('Parallel Drilling Machine 2 added! Load balancing active.', 'success');
      setTimeout(refreshWhatIfDisplay, 1000);
    } else {
      showToast(result.message, 'warning');
      if (btn) btn.disabled = false;
    }
  } catch (e) {
    showToast('Error adding machine: ' + e.message, 'error');
    if (btn) btn.disabled = false;
  }
}

async function removeParallelDrillingMachine() {
  try {
    const result = await apiPost('/api/what-if/remove-drilling-machine');
    showToast(result.message, result.success ? 'warning' : 'error');

    const btnAdd = document.getElementById('btn-add-parallel');
    const btnRem = document.getElementById('btn-remove-parallel');
    if (btnAdd) btnAdd.disabled = false;
    if (btnRem) btnRem.disabled = true;
    baselineSnapshot = null;
    setTimeout(refreshWhatIfDisplay, 500);
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

async function refreshWhatIfDisplay() {
  try {
    const data = await apiGet('/api/what-if/snapshot');
    whatifData = data;
    renderWhatIfComparison(data);
  } catch (e) {
    console.warn('What-if refresh error:', e);
  }
}

function renderWhatIfComparison(data) {
  const container = document.getElementById('whatif-comparison');
  if (!container) return;

  const current = data.current;
  const baseline = data.baseline;

  if (!baseline) {
    if (whatifChart) {
      whatifChart.data.datasets[0].data = [0, 0, 0];
      whatifChart.data.datasets[1].data = [
        current?.throughput_hr ? current.throughput_hr.toFixed(1) : 0,
        current?.drilling_util ? current.drilling_util.toFixed(1) : 0,
        current?.system_oee ? current.system_oee.toFixed(1) : 0,
      ];
      whatifChart.update();
    }
    container.innerHTML = `
      <div style="text-align:center;padding:40px;color:var(--text-muted)">
        <div style="font-size:38px;margin-bottom:12px;color:var(--spice-wine)"><i class="ri-git-merge-line"></i></div>
        <p>Start the simulation, let it run for a few seconds,<br>then click <strong style="color:var(--spice-rust)">ADD PARALLEL DRILLING MACHINE</strong> to see the comparison.</p>
      </div>
    `;
    return;
  }

  const tpImpr = data.throughput_improvement || 0;
  const oeeImpr = data.oee_improvement || 0;

  // Update what-if chart
  if (whatifChart) {
    whatifChart.data.datasets[0].data = [
      baseline.throughput_hr?.toFixed(1),
      baseline.drilling_util?.toFixed(1),
      baseline.system_oee?.toFixed(1),
    ];
    whatifChart.data.datasets[1].data = [
      current.throughput_hr?.toFixed(1),
      current.drilling_util?.toFixed(1),
      current.system_oee?.toFixed(1),
    ];
    whatifChart.update();
  }

  container.innerHTML = `
    <div style="margin-bottom:20px;padding:18px;background:var(--bg-panel);border:1px solid var(--border-subtle);border-radius:12px;display:flex;gap:24px;flex-wrap:wrap;">
      <div style="text-align:center">
        <div style="font-size:32px;font-weight:800;color:${tpImpr >= 0 ? 'var(--spice-wine)' : '#A82E37'};text-shadow:0 0 12px ${tpImpr >= 0 ? 'rgba(134,55,62,0.25)' : 'rgba(168,46,55,0.25)'}">
          ${tpImpr >= 0 ? '+' : ''}${tpImpr.toFixed(1)}%
        </div>
        <div style="font-size:12px;color:var(--text-muted)">Throughput Change</div>
      </div>
      <div style="text-align:center">
        <div style="font-size:32px;font-weight:800;color:${oeeImpr >= 0 ? 'var(--spice-wine)' : '#A82E37'};text-shadow:0 0 12px ${oeeImpr >= 0 ? 'rgba(134,55,62,0.25)' : 'rgba(168,46,55,0.25)'}">
          ${oeeImpr >= 0 ? '+' : ''}${oeeImpr.toFixed(1)}%
        </div>
        <div style="font-size:12px;color:var(--text-muted)">OEE Change</div>
      </div>
      <div style="text-align:center">
        <div style="font-size:32px;font-weight:800;color:var(--text-primary)">
          ${current.completed}
        </div>
        <div style="font-size:12px;color:var(--text-muted)">Total Completed</div>
      </div>
      <div style="text-align:center">
        <div style="font-size:32px;font-weight:800;color:var(--spice-rust);text-shadow:0 0 12px rgba(180,67,45,0.3)">
          ${current.parallel_active ? '2' : '1'}
        </div>
        <div style="font-size:12px;color:var(--text-muted)">Drilling Machines</div>
      </div>
    </div>

    <div class="table-wrap">
      <table class="comparison-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th class="baseline-col">Baseline (1 Drill)</th>
            <th class="modified-col">Modified (${current.parallel_active ? '2 Drills' : '1 Drill'})</th>
            <th>Change</th>
          </tr>
        </thead>
        <tbody>
          ${compRow('Throughput (units/hr)', baseline.throughput_hr, current.throughput_hr, true)}
          ${compRow('Drilling Util (%)',     baseline.drilling_util, current.drilling_util, false)}
          ${compRow('System OEE (%)',        baseline.system_oee,   current.system_oee,   true)}
          ${compRow('Completed Products',   baseline.completed,    current.completed,    true)}
        </tbody>
      </table>
    </div>
  `;
}

function compRow(label, base, curr, higherIsBetter) {
  const baseVal = parseFloat(base) || 0;
  const currVal = parseFloat(curr) || 0;
  const diff    = currVal - baseVal;
  const pct     = baseVal !== 0 ? ((diff / baseVal) * 100).toFixed(1) : '—';
  const positive = higherIsBetter ? diff > 0 : diff < 0;
  const sign     = diff > 0 ? '+' : '';
  const cls      = positive ? 'improvement-cell' : (diff < 0 ? 'degradation-cell' : '');

  return `
    <tr>
      <td style="font-weight:600;color:var(--text-primary)">${label}</td>
      <td class="baseline-col">${typeof baseVal === 'number' ? baseVal.toFixed(1) : baseVal}</td>
      <td class="modified-col" style="font-weight:700">${typeof currVal === 'number' ? currVal.toFixed(1) : currVal}</td>
      <td class="${cls}">${sign}${typeof diff === 'number' ? diff.toFixed(1) : diff} (${sign}${pct}%)</td>
    </tr>
  `;
}

async function saveWhatIfComparison() {
  try {
    const result = await apiPost('/api/what-if/save-comparison');
    showToast(result.message, result.success ? 'success' : 'error');
  } catch (e) {
    showToast('Save failed: ' + e.message, 'error');
  }
}

// ─────────────────────────────────────────────────────────────────
// SIMULATION CONTROLS
// ─────────────────────────────────────────────────────────────────

async function simControl(action) {
  try {
    const result = await apiPost(`/api/simulation/${action}`);
    showToast(result.message, result.success ? 'success' : 'warning');

    if (action === 'reset') {
      throughputHistory = [];
      baselineSnapshot = null;
    }

    // Immediately fetch and render fresh data after any control action
    // so the UI reflects the new state without waiting for the next WS push
    try {
      const data = await apiGet('/api/dashboard');
      updateDashboard(data);
    } catch (_) { /* WS will pick it up */ }

  } catch (e) {
    showToast(`Error: ${e.message}`, 'error');
  }
}

async function updateSpeedConfig(speed) {
  try {
    await apiPost('/api/simulation/config', { speed_multiplier: speed });
    document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.speed-btn[data-speed="${speed}"]`)?.classList.add('active');
    showToast(`Speed set to ${speed}×`, 'info');
  } catch (e) {
    showToast('Speed update failed', 'error');
  }
}

// ─────────────────────────────────────────────────────────────────
// SETTINGS
// ─────────────────────────────────────────────────────────────────

async function applySettings() {
  const config = {};

  const speed = parseFloat(document.getElementById('cfg-speed')?.value);
  if (!isNaN(speed)) config.speed_multiplier = speed;

  const arrival = parseFloat(document.getElementById('cfg-arrival')?.value);
  if (!isNaN(arrival)) config.arrival_rate = arrival;

  const breakdown = document.getElementById('cfg-breakdown')?.checked;
  if (breakdown !== undefined) config.breakdown_enabled = breakdown;

  try {
    await apiPost('/api/simulation/config', config);
    showToast('Global settings applied!', 'success');
  } catch (e) {
    showToast('Settings update failed: ' + e.message, 'error');
  }
}

async function applyMachineConfig(code) {
  const cfg = {};
  ['processing_time_min','processing_time_max','breakdown_prob','defect_rate'].forEach(key => {
    const val = parseFloat(document.getElementById(`cfg-${code}-${key}`)?.value);
    if (!isNaN(val)) cfg[key] = val;
  });

  try {
    await apiPost(`/api/simulation/machine/${code}/config`, cfg);
    showToast(`${code} config updated!`, 'success');
  } catch (e) {
    showToast('Machine config update failed', 'error');
  }
}

// ─────────────────────────────────────────────────────────────────
// HISTORY
// ─────────────────────────────────────────────────────────────────

async function loadHistory() {
  try {
    const runs = await apiGet('/api/history/runs');
    const tbody = document.getElementById('history-tbody');
    if (!tbody) return;

    if (!runs.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:30px;">No simulation runs yet</td></tr>';
      return;
    }

    tbody.innerHTML = runs.map(r => `
      <tr>
        <td>${r.id}</td>
        <td>${r.run_name}</td>
        <td><span class="badge badge-${r.status === 'running' ? 'green' : 'gray'}">${r.status}</span></td>
        <td>${r.total_products}</td>
        <td>${r.parallel_drilling ? '<span class="badge badge-green"><i class="ri-check-line"></i> Active</span>' : '<span class="badge badge-gray"><i class="ri-close-line"></i> Inactive</span>'}</td>
        <td>${r.speed_multiplier}×</td>
        <td>${r.start_time ? new Date(r.start_time).toLocaleString() : '—'}</td>
      </tr>
    `).join('');
  } catch (e) {
    console.warn('History load error:', e);
  }
}

// ─────────────────────────────────────────────────────────────────
// TOAST NOTIFICATIONS
// ─────────────────────────────────────────────────────────────────

function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const icons = {
    success: '<i class="ri-checkbox-circle-fill" style="color:var(--spice-wine);font-size:18px;"></i>',
    warning: '<i class="ri-alert-fill" style="color:var(--spice-gold-text);font-size:18px;"></i>',
    error:   '<i class="ri-close-circle-fill" style="color:#A82E37;font-size:18px;"></i>',
    info:    '<i class="ri-information-fill" style="color:var(--spice-rust);font-size:18px;"></i>'
  };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${icons[type] || ''}</span><span>${message}</span>`;
  container.prepend(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(30px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 350);
  }, duration);
}

// ─────────────────────────────────────────────────────────────────
// MACHINE CONFIG PANELS & WHAT-IF HISTORY
// ─────────────────────────────────────────────────────────────────

function renderMachineConfigPanels() {
  const machines = [
    { code: 'M_CUT',    name: 'Cutting Machine',    minT: 4,  maxT: 8,  breakProb: 0.02, defect: 0.02 },
    { code: 'M_TURN',   name: 'Turning Machine',    minT: 5,  maxT: 9,  breakProb: 0.02, defect: 0.02 },
    { code: 'M_DRILL_1',name: 'Drilling Machine 1', minT: 7,  maxT: 12, breakProb: 0.03, defect: 0.03 },
    { code: 'M_INSP',   name: 'Inspection Station', minT: 3,  maxT: 6,  breakProb: 0.01, defect: 0.00 },
    { code: 'M_PACK',   name: 'Packaging Machine',  minT: 2,  maxT: 5,  breakProb: 0.01, defect: 0.01 },
  ];

  return machines.map(m => `
    <div style="background:var(--bg-panel);border-radius:8px;padding:16px;margin-bottom:12px;">
      <div style="font-weight:700;color:var(--text-primary);margin-bottom:12px;">${m.name} (${m.code})</div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;">
        <div class="form-group">
          <label class="form-label">Min Process Time (s)</label>
          <input type="number" id="cfg-${m.code}-processing_time_min" class="form-input" value="${m.minT}" min="1" max="120" step="0.5">
        </div>
        <div class="form-group">
          <label class="form-label">Max Process Time (s)</label>
          <input type="number" id="cfg-${m.code}-processing_time_max" class="form-input" value="${m.maxT}" min="1" max="120" step="0.5">
        </div>
        <div class="form-group">
          <label class="form-label">Breakdown Prob</label>
          <input type="number" id="cfg-${m.code}-breakdown_prob" class="form-input" value="${m.breakProb}" min="0" max="1" step="0.01">
        </div>
        <div class="form-group">
          <label class="form-label">Defect Rate</label>
          <input type="number" id="cfg-${m.code}-defect_rate" class="form-input" value="${m.defect}" min="0" max="1" step="0.01">
        </div>
      </div>
      <button class="btn btn-secondary" style="margin-top:4px;font-size:12px;padding:6px 14px;" onclick="applyMachineConfig('${m.code}')">Apply</button>
    </div>
  `).join('');
}

async function loadWhatIfHistory() {
  try {
    const results = await apiGet('/api/history/what-if');
    const tbody = document.getElementById('whatif-history-tbody');
    if (!tbody) return;
    if (!results.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:20px;">No saved results</td></tr>';
      return;
    }
    tbody.innerHTML = results.map(r => `
      <tr>
        <td>${r.id}</td>
        <td>${r.analysis_time ? new Date(r.analysis_time).toLocaleString() : '—'}</td>
        <td>${r.baseline_throughput?.toFixed(1)}</td>
        <td>${r.modified_throughput?.toFixed(1)}</td>
        <td class="${r.throughput_improvement >= 0 ? 'text-green' : 'text-red'} fw-700">
          ${r.throughput_improvement >= 0 ? '+' : ''}${r.throughput_improvement?.toFixed(1)}%
        </td>
        <td>${r.baseline_oee?.toFixed(1)}%</td>
        <td>${r.modified_oee?.toFixed(1)}%</td>
      </tr>
    `).join('');
  } catch (e) {
    console.warn('What-if history load error:', e);
  }
}

// ─────────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Set up nav clicks
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => showPage(item.dataset.page));
  });

  // Render machine configuration panels on Settings page
  const cfgPanels = document.getElementById('machine-config-panels');
  if (cfgPanels) cfgPanels.innerHTML = renderMachineConfigPanels();

  // Show dashboard first
  showPage('dashboard');
  initDashboardCharts();

  // Start real-time updates (try WS first, fall back to polling)
  try {
    connectWebSocket();
    // Start polling as backup if WS isn't ready in 1s
    setTimeout(() => {
      if (!wsConnection || wsConnection.readyState !== WebSocket.OPEN) {
        startPolling();
      }
    }, 1000);
  } catch {
    startPolling();
  }

  // Set default speed button
  document.querySelector('.speed-btn[data-speed="5"]')?.classList.add('active');

  console.log('[Digital Twin] Manufacturing System — Frontend ready');
});
