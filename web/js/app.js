// DupeSort web app: choose folders, scan, review the groups, move duplicates (Chrome / Edge).

import {
  CATEGORIES, DUPLICATES_DIR, KEEP, chooseKeepers, duration, humanSize, mergeGroups, report,
  sameTags, similarPairs, splitByDuration, wasted,
} from './core.js';
import {
  audioDuration, canWrite, ensureWritable, exactGroups, isPhoto, listFiles, moveToDuplicates,
  photoHash, pickFolder, pool, undoMove,
} from './files.js';
import { hydrateIcons, icon, setupTheme } from './icons.js';
import { blobReader, readTags } from './tags.js';

const $ = (s) => document.querySelector(s);
const PAGE = 60; // groups drawn at a time

const state = {
  roots: [],
  category: 'music',
  opts: load('dupesort-options', { keep: 'best', byTags: true, versions: true, similar: true, tolerance: 6 }),
  files: [],
  groups: [],
  shown: PAGE,
  task: null, // {cancelled}
  undo: null, // records of the last move
};

function load(key, fallback) {
  try {
    return { ...fallback, ...JSON.parse(localStorage.getItem(key) || '{}') };
  } catch {
    return fallback;
  }
}
function save() {
  try {
    localStorage.setItem('dupesort-options', JSON.stringify(state.opts));
  } catch {}
}

function plural(n, word) {
  return n === 1 ? word : `${word}s`;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

// --- folders ----------------------------------------------------------------------------------

async function addFolder() {
  try {
    const root = await pickFolder();
    for (const r of state.roots) if (r.handle && root.handle && (await r.handle.isSameEntry(root.handle))) return;
    state.roots.push(root);
    renderChips();
  } catch (e) {
    if (e.name !== 'AbortError') alert(`Couldn't open that folder: ${e.message}`);
  }
}

function renderChips() {
  const chips = $('#chips');
  chips.querySelectorAll('.chip:not(.add)').forEach((c) => c.remove());
  const names = state.roots.map((r) => r.name);
  state.roots.forEach((root, i) => {
    const chip = document.createElement('span');
    chip.className = 'chip';
    const dupe = names.filter((n) => n === root.name).length > 1;
    chip.innerHTML = `<span title="${esc(root.name)}">${esc(root.name)}${dupe ? ` <span class="muted">(${i + 1})</span>` : ''}</span>
      <button type="button" aria-label="Remove ${esc(root.name)}">${icon('close')}</button>`;
    chip.querySelector('button').addEventListener('click', () => {
      state.roots.splice(i, 1);
      renderChips();
    });
    chips.insertBefore(chip, $('#add'));
  });
  $('#scan').disabled = !state.roots.length || !!state.task;
  $('#hero-add').hidden = state.roots.length > 0;
}

// --- categories and options -------------------------------------------------------------------

function renderCategories() {
  const box = $('#categories');
  box.innerHTML = Object.entries(CATEGORIES)
    .map(([key, c]) => `<button type="button" data-cat="${key}" aria-pressed="${key === state.category}">${icon(key)}${c.label}</button>`)
    .join('');
  box.querySelectorAll('button').forEach((b) =>
    b.addEventListener('click', () => {
      if (state.task) return;
      state.category = b.dataset.cat;
      clearResults();
      renderCategories();
      renderOptions();
    })
  );
}

function renderOptions() {
  const o = state.opts;
  const keep = `<label><span class="field-label">Keep</span><select id="o-keep">${Object.entries(KEEP)
    .map(([k, v]) => `<option value="${k}" ${k === o.keep ? 'selected' : ''}>${v}</option>`)
    .join('')}</select></label>`;
  let extra = '';
  if (state.category === 'music') {
    extra = `<span class="field-label">Match</span>
      <label title="Same artist and title, and a length within 3 seconds"><input type="checkbox" id="o-tags" ${o.byTags ? 'checked' : ''}>Same artist &amp; title</label>
      <label title="Live, acoustic, unplugged, remix, demo, instrumental and other versions of a song are not duplicates of each other. Read from the title, file name, album, genre and folder name."><input type="checkbox" id="o-versions" ${o.versions ? 'checked' : ''}>Keep versions apart</label>`;
  } else if (state.category === 'photos') {
    extra = `<span class="field-label">Match</span>
      <label><input type="checkbox" id="o-similar" ${o.similar ? 'checked' : ''}>Similar photos</label>
      <label title="0 = only near-identical. 4–8 catches resized or re-saved copies. Higher values may group different shots.">Tolerance
        <input type="range" id="o-tol" min="0" max="12" value="${o.tolerance}"><span id="o-tol-v">${o.tolerance}</span></label>`;
  } else {
    extra = `<span class="muted small">Finds identical files. Re-encoded videos and a document's PDF copy need the <a href="download.html">desktop app</a>.</span>`;
  }
  $('#options').innerHTML = keep + extra;
  const bind = (id, key, get = (el) => el.checked) => {
    const el = $(id);
    if (el) el.addEventListener('change', () => {
      o[key] = get(el);
      save();
      if (key === 'keep' && state.groups.length) {
        chooseKeepers(state.groups, o.keep, state.category);
        renderResults();
      }
    });
  };
  bind('#o-keep', 'keep', (el) => el.value);
  bind('#o-tags', 'byTags');
  bind('#o-versions', 'versions');
  bind('#o-similar', 'similar');
  const tol = $('#o-tol');
  if (tol) tol.addEventListener('input', () => {
    o.tolerance = +tol.value;
    $('#o-tol-v').textContent = tol.value;
    save();
  });
}

// --- progress ---------------------------------------------------------------------------------

function progress(done, total, text) {
  const box = $('#progress');
  box.hidden = false;
  const bar = box.querySelector('.bar');
  bar.classList.toggle('indeterminate', !total);
  bar.querySelector('i').style.width = total ? `${Math.round((done / total) * 100)}%` : '';
  if (text) box.querySelector('.text').textContent = text;
}

function startTask() {
  const task = { cancel: false, cancelled: () => task.cancel };
  state.task = task;
  $('#scan').disabled = true;
  $('#add').disabled = true;
  $('#move').disabled = true;
  progress(0, 0, 'Starting…');
  return task;
}

function endTask() {
  state.task = null;
  $('#progress').hidden = true;
  $('#add').disabled = false;
  renderChips();
  updateBar();
}

// --- scanning ---------------------------------------------------------------------------------

async function scan() {
  if (!state.roots.length || state.task) return;
  clearResults();
  const task = startTask();
  const { cancelled } = task;
  const category = state.category, o = state.opts;
  try {
    const files = await listFiles(state.roots, category, { onProgress: (t) => progress(0, 0, t), cancelled });
    state.files = files;
    progress(0, files.length, `Comparing ${files.length} files…`);
    const found = [['Identical file', await exactGroups(files, { onProgress: progress, cancelled })]];

    if (category === 'music' && o.byTags && !cancelled()) {
      let n = 0;
      await pool(files, 8, async (f) => {
        f.tags = await readTags(blobReader(f.file), f.size);
        if (++n % 25 === 0) progress(n, files.length, `Reading tags: ${f.name}`);
      }, cancelled);
      const buckets = sameTags(files, o.versions);
      const need = buckets.flat();
      let d = 0;
      await pool(need, 6, async (f) => {
        f.duration = await audioDuration(f.file);
        progress(++d, need.length, `Reading song lengths: ${f.name}`);
      }, cancelled);
      found.push(['Same artist & title', buckets.flatMap((b) => splitByDuration(b, 3))]);
    }
    if (category === 'photos' && o.similar && !cancelled()) {
      let n = 0;
      await pool(files, 4, async (f) => {
        Object.assign(f, (await photoHash(f.file)) || {});
        progress(++n, files.length, `Looking at photos: ${f.name}`);
      }, cancelled);
      found.push(['Similar photo', similarPairs(files, o.tolerance)]);
    }

    const groups = mergeGroups(found);
    if (category === 'music') {
      // Bitrate (for "best quality") needs the length of every song in a group.
      const need = groups.flatMap((g) => g.files).filter((f) => f.duration === undefined);
      await pool(need, 6, async (f) => {
        f.duration = await audioDuration(f.file);
      }, cancelled);
    }
    if (category === 'photos') {
      const need = groups.flatMap((g) => g.files).filter((f) => f.width === undefined);
      await pool(need, 4, async (f) => Object.assign(f, (await photoHash(f.file)) || {}), cancelled);
    }
    chooseKeepers(groups, o.keep, category);
    state.groups = groups;
    state.shown = PAGE;
    renderResults(cancelled());
  } catch (e) {
    console.error(e);
    alert(`The scan stopped: ${e.message}`);
  } finally {
    endTask();
  }
}

// --- results ----------------------------------------------------------------------------------

function clearResults() {
  state.files = [];
  state.groups = [];
  $('#results').hidden = true;
  $('#hero').hidden = false;
  $('#actionbar').hidden = true;
  document.body.classList.remove('has-actionbar');
  hideToast();
}

function details(f) {
  const bits = [humanSize(f.size)];
  if (f.width) bits.push(`${f.width}×${f.height}`);
  if (f.duration) {
    bits.push(duration(f.duration));
    bits.push(`${Math.round((f.size * 8) / f.duration / 1000)} kbps`);
  }
  if (f.mtime) bits.push(new Date(f.mtime).toLocaleDateString());
  return bits.join(' · ');
}

let thumbObserver;
function lazyThumbs(root) {
  thumbObserver ??= new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      const img = e.target;
      thumbObserver.unobserve(img);
      img.src = URL.createObjectURL(img._file);
      img.onload = () => URL.revokeObjectURL(img.src);
    }
  }, { rootMargin: '300px' });
  root.querySelectorAll('img.thumb[data-lazy]').forEach((img) => thumbObserver.observe(img));
}

function renderResults(partial = false) {
  const groups = state.groups;
  $('#hero').hidden = true;
  $('#results').hidden = false;
  const dupes = groups.reduce((n, g) => n + g.files.length - g.keep.size, 0);
  const free = groups.reduce((n, g) => n + wasted(g), 0);
  $('#summary').innerHTML = groups.length
    ? `<span><b style="color:var(--fg)">${groups.length}</b> ${plural(groups.length, 'group')} · <b style="color:var(--fg)">${dupes}</b> ${plural(dupes, 'duplicate')} · ${humanSize(free)} can be freed${partial ? ' · scan cancelled, partial results' : ''}</span>
       <span class="small">Ticked files are kept. Click a file to change which one.</span>`
    : `<span>No duplicates found in ${state.files.length} files${partial ? ' (scan cancelled)' : ''}.</span>`;

  const list = $('#groups');
  list.innerHTML = '';
  const showPhotos = state.category === 'photos' || state.category === 'all';
  groups.slice(0, state.shown).forEach((g, gi) => {
    const card = document.createElement('div');
    card.className = 'group';
    card.innerHTML = `<div class="group-head"><h3>Group ${gi + 1}</h3><span class="pill">${esc(g.reason)}</span>
      <span class="free">${g.files.length} files · ${humanSize(wasted(g))} can be freed</span></div>`;
    g.files.forEach((f, i) => {
      const kept = g.keep.has(i);
      const row = document.createElement('div');
      row.className = `file${kept ? '' : ' dupe'}`;
      const thumb = showPhotos && isPhoto(f.name);
      row.innerHTML = `<label><input type="checkbox" ${kept ? 'checked' : ''} aria-label="Keep ${esc(f.name)}">
        <img class="thumb${thumb ? '' : ' none'}" ${thumb ? 'data-lazy' : ''} alt="">
        <span class="grow-col"><span class="name">${esc(f.name)}</span><span class="tag ${kept ? 'keep' : 'dupe'}">${kept ? 'Keep' : 'Duplicate'}</span><br><span class="where">${esc(f.folder)}</span></span>
        <span class="meta">${esc(details(f))}</span></label>`;
      if (thumb) row.querySelector('img')._file = f.file;
      row.querySelector('input').addEventListener('change', (e) => {
        if (e.target.checked) g.keep.add(i);
        else if (g.keep.size > 1) g.keep.delete(i);
        else e.target.checked = true; // every group keeps at least one file
        renderResults();
      });
      card.appendChild(row);
    });
    list.appendChild(card);
  });
  lazyThumbs(list);
  $('#more').hidden = groups.length <= state.shown;
  $('#actionbar').hidden = !groups.length;
  document.body.classList.toggle('has-actionbar', groups.length > 0);
  updateBar();
}

function updateBar() {
  const dupes = state.groups.flatMap((g) => g.files.filter((_, i) => !g.keep.has(i)));
  const free = dupes.reduce((n, f) => n + f.size, 0);
  $('#bar-text').textContent = dupes.length ? `${dupes.length} ${plural(dupes.length, 'duplicate')} · ${humanSize(free)}` : 'Nothing to move';
  const writable = state.roots.every((r) => r.handle);
  $('#move').hidden = !canWrite;
  $('#move').disabled = !dupes.length || !!state.task || !writable;
}

// --- moving -----------------------------------------------------------------------------------

async function moveDuplicates() {
  const moves = state.groups.flatMap((g) => g.files.filter((_, i) => !g.keep.has(i)));
  if (!moves.length) return;
  if (!confirm(`Move ${moves.length} duplicate files into a "${DUPLICATES_DIR}" folder inside each chosen folder?\n\nNothing is deleted, and you can undo.`)) return;
  for (const root of new Set(moves.map((f) => f.root))) {
    if (!(await ensureWritable(root))) {
      alert(`DupeSort needs permission to change "${root.name}" to move files.`);
      return;
    }
  }
  const task = startTask();
  const records = [], errors = [];
  for (const [n, f] of moves.entries()) {
    if (task.cancelled()) break;
    progress(n, moves.length, `Moving ${f.name}`);
    try {
      records.push(await moveToDuplicates(f));
    } catch (e) {
      errors.push(`${f.path}: ${e.message}`);
    }
  }
  const moved = new Set(records.map((r) => r.file));
  state.groups = state.groups.filter((g) => !g.files.some((f) => moved.has(f)));
  state.undo = { records, groups: null };
  endTask();
  renderResults();
  showToast(`Moved ${records.length} ${plural(records.length, 'file')} to ${DUPLICATES_DIR}.`);
  if (errors.length) alert(`Some files were not moved:\n\n${errors.slice(0, 20).join('\n')}`);
}

async function undo() {
  const u = state.undo;
  if (!u) return;
  hideToast();
  const task = startTask();
  let n = 0;
  for (const r of u.records.slice().reverse()) {
    if (task.cancelled()) break;
    progress(n++, u.records.length, `Putting back ${r.file.name}`);
    try {
      await undoMove(r);
    } catch (e) {
      console.warn(e);
    }
  }
  state.undo = null;
  endTask();
  showToast(`Put ${n} files back. Scan again to see the groups.`, false);
}

function showToast(text, withUndo = true) {
  const t = $('#toast');
  t.querySelector('span').textContent = text;
  $('#undo').hidden = !withUndo;
  t.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(hideToast, withUndo ? 20000 : 6000);
}
function hideToast() {
  $('#toast').hidden = true;
}

function saveReport() {
  const blob = new Blob([report(state.groups)], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `DupeSort ${CATEGORIES[state.category].label} report.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// --- start ------------------------------------------------------------------------------------

hydrateIcons();
setupTheme($('#theme'));
renderCategories();
renderOptions();
renderChips();
$('#readonly').hidden = canWrite;
$('#add').addEventListener('click', addFolder);
$('#hero-add').addEventListener('click', addFolder);
$('#scan').addEventListener('click', scan);
$('#cancel').addEventListener('click', () => state.task && (state.task.cancel = true));
$('#move').addEventListener('click', moveDuplicates);
$('#report').addEventListener('click', saveReport);
$('#undo').addEventListener('click', undo);
$('#more button').addEventListener('click', () => {
  state.shown += PAGE;
  renderResults();
});

// For automated tests: hand the app a folder (e.g. from navigator.storage.getDirectory()).
window.dupesort = {
  state,
  scan,
  addFolderHandle(handle) {
    state.roots.push({ name: handle.name || 'Folder', handle });
    renderChips();
  },
};
