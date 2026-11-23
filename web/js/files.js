// Everything that touches the person's files: choosing folders, listing them, hashing,
// reading song lengths and photo fingerprints, and moving duplicates (with undo).
// Files are read on this device only; nothing is uploaded.

import { DUPLICATES_DIR, SKIP_DIRS, ext, phash, wanted } from './core.js';

/** Chrome / Edge can write to a folder you pick; Safari and Firefox can only read. */
export const canWrite = typeof window !== 'undefined' && 'showDirectoryPicker' in window;

/** A folder the person chose: {name, handle?, files?} (files = a webkitdirectory FileList). */
export async function pickFolder() {
  if (canWrite) {
    const handle = await window.showDirectoryPicker({ id: 'dupesort', mode: 'readwrite' });
    return { name: handle.name, handle };
  }
  return new Promise((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.webkitdirectory = true;
    input.multiple = true;
    input.addEventListener('change', () => {
      const files = [...input.files];
      if (!files.length) return reject(new DOMException('No folder chosen', 'AbortError'));
      resolve({ name: files[0].webkitRelativePath.split('/')[0], files });
    });
    input.addEventListener('cancel', () => reject(new DOMException('No folder chosen', 'AbortError')));
    input.click();
  });
}

/** Ask again for write access (browsers forget it between visits). */
export async function ensureWritable(root) {
  if (!root.handle) return false;
  const opts = { mode: 'readwrite' };
  if ((await root.handle.queryPermission(opts)) === 'granted') return true;
  return (await root.handle.requestPermission(opts)) === 'granted';
}

/**
 * Every wanted file under the chosen folders, as
 * {path, name, folder, size, mtime, file, handle?, dir?, root}. `folder` is relative to the root.
 */
export async function listFiles(roots, category, { onProgress, cancelled }) {
  const out = [];
  for (const root of roots) {
    if (root.handle) {
      const walk = async (dir, rel) => {
        for await (const entry of dir.values()) {
          if (cancelled()) return;
          if (entry.kind === 'directory') {
            if (!entry.name.startsWith('.') && !SKIP_DIRS.has(entry.name)) await walk(entry, rel ? `${rel}/${entry.name}` : entry.name);
          } else if (wanted(category, entry.name)) {
            const file = await entry.getFile();
            if (!file.size) continue;
            const folder = rel ? `${root.name}/${rel}` : root.name;
            out.push({ path: `${folder}/${file.name}`, name: file.name, folder, size: file.size, mtime: file.lastModified, file, handle: entry, dir, root });
            if (out.length % 200 === 0) onProgress(`Found ${out.length} files…`);
          }
        }
      };
      await walk(root.handle, '');
    } else {
      for (const file of root.files) {
        const parts = file.webkitRelativePath.split('/');
        if (parts.some((p, i) => i < parts.length - 1 && (p.startsWith('.') || SKIP_DIRS.has(p)))) continue;
        if (!file.size || !wanted(category, file.name)) continue;
        const folder = parts.slice(0, -1).join('/');
        out.push({ path: file.webkitRelativePath, name: file.name, folder, size: file.size, mtime: file.lastModified, file, root });
      }
    }
  }
  return out;
}

// --- identical files --------------------------------------------------------------------------

const CHUNK = 32 * 1024 * 1024;

async function sha256(blob) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()));
}

function hex(bytes) {
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** A fingerprint of the whole file: SHA-256 of each 32 MB chunk, then of those digests. */
export async function fullHash(file) {
  if (file.size <= CHUNK) return hex(await sha256(file));
  const parts = [];
  for (let o = 0; o < file.size; o += CHUNK) parts.push(await sha256(file.slice(o, o + CHUNK)));
  const all = new Uint8Array(parts.length * 32);
  parts.forEach((p, i) => all.set(p, i * 32));
  return hex(new Uint8Array(await crypto.subtle.digest('SHA-256', all)));
}

/** First and last 64 KB, to rule out most same-size files without reading them in full. */
async function quickHash(file) {
  const k = 64 * 1024;
  if (file.size <= 2 * k) return hex(await sha256(file)); // small files: the whole file
  return hex(await sha256(new Blob([file.slice(0, k), file.slice(file.size - k)])));
}

/** Groups of byte-for-byte identical files. */
export async function exactGroups(files, { onProgress, cancelled }) {
  const bySize = new Map();
  for (const f of files) {
    if (!bySize.has(f.size)) bySize.set(f.size, []);
    bySize.get(f.size).push(f);
  }
  const groups = [];
  const candidates = [...bySize.values()].filter((g) => g.length > 1);
  const total = candidates.reduce((n, g) => n + g.length, 0);
  let done = 0;
  for (const sameSize of candidates) {
    const byQuick = new Map();
    for (const f of sameSize) {
      if (cancelled()) return groups;
      const q = await quickHash(f.file);
      if (!byQuick.has(q)) byQuick.set(q, []);
      byQuick.get(q).push(f);
      onProgress(++done, total, `Comparing ${f.name}`);
    }
    for (const same of byQuick.values()) {
      if (same.length < 2) continue;
      const byFull = new Map();
      for (const f of same) {
        if (cancelled()) return groups;
        const h = f.size <= 128 * 1024 ? 'small' : await fullHash(f.file);
        if (!byFull.has(h)) byFull.set(h, []);
        byFull.get(h).push(f);
      }
      for (const g of byFull.values()) if (g.length > 1) groups.push(g);
    }
  }
  return groups;
}

// --- media details ----------------------------------------------------------------------------

/** Length of a song in seconds, from the browser's own decoder (0 if it can't play it). */
export function audioDuration(file) {
  return new Promise((resolve) => {
    const audio = new Audio();
    const url = URL.createObjectURL(file);
    const done = (value) => {
      clearTimeout(timer);
      URL.revokeObjectURL(url);
      audio.removeAttribute('src');
      resolve(Number.isFinite(value) ? value : 0);
    };
    const timer = setTimeout(() => done(0), 15000);
    audio.preload = 'metadata';
    audio.addEventListener('loadedmetadata', () => done(audio.duration));
    audio.addEventListener('error', () => done(0));
    audio.src = url;
  });
}

/**
 * Size and 64-bit perceptual hash of a photo (see `phash` in core.js). Resized or re-saved
 * copies give near-equal hashes.
 */
export async function photoHash(file) {
  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    return null; // a format this browser can't decode (e.g. HEIC outside Safari)
  }
  const { width, height } = bitmap;
  const canvas = new OffscreenCanvas(32, 32);
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(bitmap, 0, 0, 32, 32);
  bitmap.close();
  const px = ctx.getImageData(0, 0, 32, 32).data;
  const grey = new Float64Array(1024);
  for (let i = 0; i < 1024; i++) grey[i] = px[i * 4] * 0.299 + px[i * 4 + 1] * 0.587 + px[i * 4 + 2] * 0.114;
  return { width, height, phash: phash(grey) };
}

/** Run `fn` over `items`, `limit` at a time. */
export async function pool(items, limit, fn, cancelled = () => false) {
  let next = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length && !cancelled()) await fn(items[next++]);
  });
  await Promise.all(workers);
}

// --- moving duplicates (Chrome / Edge) --------------------------------------------------------

async function dirAt(rootHandle, parts) {
  let dir = rootHandle;
  for (const p of parts) dir = await dir.getDirectoryHandle(p, { create: true });
  return dir;
}

async function freeName(dir, name) {
  const dot = name.lastIndexOf('.');
  const base = dot > 0 ? name.slice(0, dot) : name, suffix = dot > 0 ? name.slice(dot) : '';
  for (let n = 1; ; n++) {
    const candidate = n === 1 ? name : `${base} (${n})${suffix}`;
    try {
      await dir.getFileHandle(candidate);
    } catch {
      return candidate;
    }
  }
}

/** Move one file handle from `fromDir` into `toDir`; returns the new handle. */
async function moveHandle(handle, fromDir, toDir) {
  const name = await freeName(toDir, handle.name);
  if (typeof handle.move === 'function') {
    try {
      await handle.move(toDir, name);
      return await toDir.getFileHandle(name);
    } catch {
      // fall back to copy + delete below
    }
  }
  const file = await handle.getFile();
  const target = await toDir.getFileHandle(name, { create: true });
  const out = await target.createWritable();
  await out.write(file);
  await out.close();
  await fromDir.removeEntry(handle.name);
  return target;
}

/**
 * Move `f` into "<chosen folder>/_Duplicates/<its sub-folder>/". Returns an undo record.
 */
export async function moveToDuplicates(f) {
  const rel = f.folder.split('/').slice(1);
  const toDir = await dirAt(f.root.handle, [DUPLICATES_DIR, ...rel]);
  const moved = await moveHandle(f.handle, f.dir, toDir);
  return { file: f, movedHandle: moved, movedDir: toDir };
}

export async function undoMove(record) {
  const back = await moveHandle(record.movedHandle, record.movedDir, record.file.dir);
  record.file.handle = back;
}

export function isPhoto(name) {
  return ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'avif'].includes(ext(name));
}
