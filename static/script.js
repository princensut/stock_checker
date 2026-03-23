const $ = id => document.getElementById(id);

/* ── Symbol chips ── */
function fill(sym) {
  $('stockInput').value = sym;
  $('stockInput').focus();
}

/* ── Workflow badges ── */
const wfIds = ['wf1','wf2','wf3','wf4','wf5','wf6'];

function resetWF() {
  wfIds.forEach(id => { $(id).className = 'wf-badge'; });
}

function setWF(idx, state) {
  wfIds.forEach((id, i) => {
    const el = $(id);
    el.classList.remove('active','done','error');
    if (i < idx - 1)  el.classList.add('done');
    if (i === idx - 1) el.classList.add(state || 'active');
  });
}

/* ── Pipeline steps ── */
function resetPipe() {
  for (let i = 1; i <= 6; i++) {
    const el = $('p' + i);
    el.className = 'pipe-step';
    el.querySelector('.pipe-dot').textContent = i;
  }
  $('pipeStatus').textContent = '—';
}

function activePipe(n) {
  return new Promise(resolve => {
    const el = $('p' + n);
    el.classList.add('active');
    el.querySelector('.pipe-dot').textContent = '•';
    setTimeout(resolve, 500);
  });
}

function donePipe(n) {
  const el = $('p' + n);
  el.classList.remove('active');
  el.classList.add('done');
  el.querySelector('.pipe-dot').textContent = '✓';
}

function errPipe(n) {
  const el = $('p' + n);
  el.classList.remove('active');
  el.classList.add('error');
  el.querySelector('.pipe-dot').textContent = '✗';
}

/* ── Status messages ── */
function showStatus(type, msg) {
  ['stLoading','stError','stOk'].forEach(id => $(id).classList.remove('show'));
  if (type === 'loading') { $('stLoading').classList.add('show'); $('stMsg').textContent = msg; }
  if (type === 'error')   { $('stError').classList.add('show');   $('stErr').textContent = msg; }
  if (type === 'success') { $('stOk').classList.add('show');      $('stOkMsg').textContent = msg; }
}

/* ── Top pill ── */
function setPill(txt, bg, color) {
  const p = $('topPill');
  p.textContent = txt;
  p.style.background  = bg;
  p.style.color       = color;
  p.style.borderColor = 'rgba(255,255,255,0.25)';
}

/* ── Tab switcher ── */
function switchTab(btn, type) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  // Tab switching is visual only — re-request with different options if needed
}

/* ── Main pipeline runner ── */
async function run() {
  const sym = $('stockInput').value.trim().toUpperCase();
  if (!sym) { $('stockInput').focus(); return; }

  const btn = $('analyzeBtn');
  btn.disabled = true;

  // Reset UI
  showStatus(null);
  $('chartCard').classList.remove('show');
  $('emptyState').style.display = 'none';
  $('pipeCard').classList.add('show');
  setPill('● Running…', 'rgba(255,255,255,0.15)', '#fff');
  resetWF();
  resetPipe();

  // Step 1 — POST request
  showStatus('loading', 'Sending POST /analyze…');
  setWF(1);
  await activePipe(1);
  donePipe(1);

  // Step 2 — Fetch
  showStatus('loading', `Fetching market data for $${sym}…`);
  setWF(2);
  await activePipe(2);

  // ── Real Flask API call ──────────────────────────────────────────────────
  let data;
  try {
    const response = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol:     sym,
        moving_avg: $('optMA').checked,
        volume:     $('optVol').checked,
        dark_export: $('optDark').checked
      })
    });
    data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Request failed');
    }
  } catch (err) {
    donePipe(2);

    // Step 3 — Validate fails
    showStatus('loading', 'Validating symbol…');
    setWF(3);
    await activePipe(3);
    await new Promise(r => setTimeout(r, 300));

    errPipe(3);
    setWF(3, 'error');
    showStatus('error', err.message || `"${sym}" is not a valid ticker.`);
    setPill('● Error', 'rgba(255,255,255,0.15)', '#fca5a5');
    $('pipeStatus').textContent = 'failed';
    $('emptyState').style.display = '';
    btn.disabled = false;
    return;
  }
  // ────────────────────────────────────────────────────────────────────────

  donePipe(2);

  // Step 3 — Validate
  showStatus('loading', 'Validating data…');
  setWF(3);
  await activePipe(3);
  await new Promise(r => setTimeout(r, 300));
  donePipe(3);

  // Step 4 — Process
  showStatus('loading', 'Processing with pandas…');
  setWF(4);
  await activePipe(4);
  await new Promise(r => setTimeout(r, 400));
  donePipe(4);

  // Step 5 — Plot
  showStatus('loading', 'Generating Matplotlib chart…');
  setWF(5);
  await activePipe(5);
  await new Promise(r => setTimeout(r, 400));
  donePipe(5);

  // Step 6 — Serve
  showStatus('loading', 'Serving PNG to frontend…');
  setWF(6);
  await activePipe(6);
  await new Promise(r => setTimeout(r, 200));
  donePipe(6);
  setWF(6, 'done');

  // ── Populate results from Flask response ─────────────────────────────────
  const stats = data.stats;

  $('symName').textContent  = stats.symbol;
  $('symFull').textContent  = stats.symbol + ' — via Yahoo Finance';
  $('sPrice').textContent   = stats.latest_price;
  $('sChange').textContent  = stats.pct_change;
  $('sHigh').textContent    = stats.high;
  $('sLow').textContent     = stats.low;

  // Change card color based on up/down
  const scCard = $('scChange');
  scCard.className = 'stat-card stat-card-change' + (stats.up ? '' : ' neg');

  // Inject the Flask-generated chart image
  $('chartArea').innerHTML = `
    <img src="${data.image_path}" alt="Stock chart for ${stats.symbol}"
         style="width:100%;display:block;border-radius:8px;"/>
  `;
  // ────────────────────────────────────────────────────────────────────────

  showStatus('success', `Chart ready — ${stats.symbol}: ${stats.latest_price}`);
  setPill('● Ready', 'rgba(255,255,255,0.15)', '#86efac');
  $('pipeStatus').textContent = 'complete';
  $('chartCard').classList.add('show');
  btn.disabled = false;
}

/* ── Enter key support ── */
$('stockInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') run();
});
