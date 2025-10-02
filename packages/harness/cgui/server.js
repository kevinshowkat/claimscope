const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = process.env.PORT ? Number(process.env.PORT) : 3000;
const BASE = '/cgui';

function send(res, status, body, contentType = 'text/html; charset=utf-8') {
  res.writeHead(status, { 'Content-Type': contentType });
  res.end(body);
}

function layout(title, bodyHtml, description) {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${title}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 2rem; }
    main { max-width: 720px; }
    ul { list-style: none; padding-left: 0; }
    li { margin: 0.5rem 0; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ddd; padding: 8px; }
    th { background: #f8f8f8; text-align: left; }
    button { margin: 0.25rem 0.25rem 1rem 0; }
    .status { float: right; color: #555; }
  </style>
</head>
<body>
  <main>
    <h1>cGUI Scenarios</h1>
    ${description ? `<p>${description}</p>` : ''}
    ${bodyHtml}
  </main>
</body>
</html>`;
}

function indexPage() {
  const desc = 'These mini-apps back the deterministic Playwright suite.';
  const body = `
    <ul>
      <li><a href="${BASE}/form">Mission Intake Form</a></li>
      <li><a href="${BASE}/table">Telemetry Table</a></li>
      <li><a href="${BASE}/files">Document Download</a></li>
      <li><a href="${BASE}/flow">Checklist Flow</a></li>
    </ul>
  `;
  return layout('cGUI Scenarios', body, desc);
}

function formPage() {
  const body = `
    <form id="mission-form">
      <div>
        <label for="callsign">Callsign</label>
        <input id="callsign" name="callsign" value="Aurora" />
      </div>
      <div>
        <label for="crew">Crew</label>
        <input id="crew" name="crew" type="number" value="4" />
      </div>
      <div>
        <label for="window">Window</label>
        <input id="window" name="window" type="datetime-local" value="2035-04-18T13:30" />
      </div>
      <div>
        <label for="notes">Notes</label>
        <textarea id="notes" name="notes"></textarea>
      </div>
      <button type="submit">Submit</button>
    </form>
    <script>
      const form = document.getElementById('mission-form');
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const data = new FormData(form);
        const callsign = data.get('callsign');
        const crew = data.get('crew');
        const windowVal = data.get('window');
        const notes = data.get('notes');
        const container = document.querySelector('main');
        const receiptHtml = [
          '<h1>cGUI Scenarios</h1>',
          '<section>',
          '  <h2>Submission Receipt</h2>',
          '  <p><strong>' + callsign + '</strong></p>',
          '  <p>' + crew + '</p>',
          '  <p>' + windowVal + '</p>',
          '  <p>' + notes + '</p>',
          '</section>'
        ].join('');
        container.innerHTML = receiptHtml;
      });
    </script>
  `;
  return layout('Mission Intake Form', body);
}

function flowPage() {
  const body = `
    <ul id="steps">
      <li>Authenticate <span class="status">In progress</span></li>
      <li>Review data <span class="status">Pending</span></li>
      <li>Execution <span class="status">Pending</span></li>
    </ul>
    <button id="advance">Mark step complete</button>
    <div id="complete"></div>
    <script>
      let index = 0;
      const steps = Array.from(document.querySelectorAll('#steps li'));
      const btn = document.getElementById('advance');
      function setStatus(i, text){
        const span = steps[i].querySelector('.status');
        span.textContent = text;
      }
      btn.addEventListener('click', () => {
        if (index < steps.length) {
          setStatus(index, 'Completed');
          index++;
          if (index < steps.length) setStatus(index, 'In progress');
        }
        if (index >= steps.length) {
          document.getElementById('complete').innerHTML = '<p>Checklist complete</p>' +
            '<p>Handover logged at 18:00 UTC</p>';
        }
      });
    </script>
  `;
  return layout('Checklist Flow', body);
}

function tablePage() {
  const body = `
    <div>
      <button id="sort-latency">Sort by p95 latency</button>
      <button id="sort-success">Sort by success rate</button>
    </div>
    <table>
      <thead>
        <tr><th>Service</th><th>p95 latency (ms)</th><th>Success</th></tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
    <script>
      const data = [
        { name: 'Intake', latency: 120, success: 0.960 },
        { name: 'Review', latency: 200, success: 0.920 },
        { name: 'Handover', latency: 300, success: 0.940 },
        { name: 'Execution', latency: 350, success: 0.880 },
      ];
      const tbody = document.getElementById('tbody');
      function render(rows) {
        tbody.innerHTML = rows.map(function(r){
          return '<tr>' +
                 '<td>' + r.name + '</td>' +
                 '<td>' + r.latency + '</td>' +
                 '<td>' + (r.success*100).toFixed(1) + '%</td>' +
                 '</tr>';
        }).join('');
      }
      let latencyAsc = true;
      let successAsc = true;
      document.getElementById('sort-latency').addEventListener('click', function() {
        const rows = data.slice().sort(function(a,b){ return latencyAsc ? a.latency - b.latency : b.latency - a.latency; });
        latencyAsc = !latencyAsc;
        render(rows);
      });
      document.getElementById('sort-success').addEventListener('click', function() {
        const rows = data.slice().sort(function(a,b){ return successAsc ? a.success - b.success : b.success - a.success; });
        successAsc = !successAsc;
        render(rows);
      });
      render(data);
    </script>
  `;
  return layout('Telemetry Table', body);
}

function filesPage() {
  const body = `
    <ul>
      <li><a href="${BASE}/static/mission-brief.txt">Mission brief</a></li>
      <li><a href="${BASE}/static/ops-checklist.csv">Ops checklist</a></li>
    </ul>
  `;
  return layout('Document Download', body);
}

function serveStatic(req, res, pathname) {
  const rel = pathname.replace(`${BASE}/static/`, '');
  const filePath = path.join(__dirname, 'static', rel);
  if (!filePath.startsWith(path.join(__dirname, 'static'))) {
    return send(res, 403, 'Forbidden', 'text/plain');
  }
  fs.readFile(filePath, (err, data) => {
    if (err) return send(res, 404, 'Not found', 'text/plain');
    const ext = path.extname(filePath).toLowerCase();
    const type = ext === '.txt' ? 'text/plain; charset=utf-8'
      : ext === '.csv' ? 'text/csv; charset=utf-8'
      : 'application/octet-stream';
    send(res, 200, data, type);
  });
}

const ROUTES = [
  { path: '/', handler: indexPage },
  { path: '/form', handler: formPage },
  { path: '/flow', handler: flowPage },
  { path: '/table', handler: tablePage },
  { path: '/files', handler: filesPage },
];

function normalizePath(value) {
  if (!value) return '/';
  if (value.length > 1 && value.endsWith('/')) {
    return value.replace(/\/+/g, '/').replace(/\/$/, '');
  }
  return value.replace(/\/+/g, '/');
}

function matchesRoute(pathname, routePath) {
  const normalized = normalizePath(pathname);
  if (routePath === '/') {
    return normalized === '/' || normalized === BASE;
  }
  return normalized === routePath || normalized === `${BASE}${routePath}`;
}

const server = http.createServer((req, res) => {
  const { pathname } = url.parse(req.url || '/');
  if (!pathname) return send(res, 400, 'Bad request', 'text/plain');

  for (const route of ROUTES) {
    if (matchesRoute(pathname, route.path)) {
      return send(res, 200, route.handler());
    }
  }

  const normalized = normalizePath(pathname);
  if (normalized.startsWith(`${BASE}/static/`)) {
    return serveStatic(req, res, normalized);
  }

  return send(res, 404, 'Not found', 'text/plain');
});

server.listen(PORT, () => {
  console.log(`cGUI server listening on http://localhost:${PORT} serving / and ${BASE}`);
});
