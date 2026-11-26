// DupeSort web: the matching rules, shared with the desktop app (dupesort/music/organizer.py,
// dupesort/core/duplicates.py). No browser APIs here, so the tests run in Node.

export const DUPLICATES_DIR = '_Duplicates';

export const CATEGORIES = {
  music: {
    label: 'Music',
    exts: ['mp3', 'flac', 'm4a', 'aac', 'ogg', 'oga', 'opus', 'wma', 'wav', 'aiff', 'aif', 'ape', 'wv', 'alac'],
  },
  photos: {
    label: 'Photos',
    exts: ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tif', 'tiff', 'webp', 'heic', 'heif', 'avif'],
  },
  videos: {
    label: 'Videos',
    exts: ['mp4', 'm4v', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mpg', 'mpeg', '3gp', 'ts', 'mts', 'm2ts'],
  },
  documents: {
    label: 'Documents',
    exts: ['pdf', 'doc', 'docx', 'odt', 'rtf', 'txt', 'md', 'xls', 'xlsx', 'ods', 'csv', 'ppt', 'pptx', 'odp', 'epub', 'pages', 'numbers', 'key', 'dwg', 'dxf'],
  },
  all: { label: 'Any file', exts: null },
};

export const LOSSLESS = new Set(['flac', 'wav', 'aiff', 'aif', 'ape', 'wv', 'alac']);
export const SKIP_DIRS = new Set([DUPLICATES_DIR, 'node_modules', '__pycache__', '$RECYCLE.BIN', 'System Volume Information']);

export function ext(name) {
  const i = name.lastIndexOf('.');
  return i > 0 ? name.slice(i + 1).toLowerCase() : '';
}

export function stem(name) {
  const i = name.lastIndexOf('.');
  return i > 0 ? name.slice(0, i) : name;
}

export function wanted(category, name) {
  if (name.startsWith('.')) return false;
  const exts = CATEGORIES[category]?.exts;
  return !exts || exts.includes(ext(name));
}

// --- text helpers -----------------------------------------------------------------------------

/** ASCII, lower case, with accents removed. */
export function ascii(text) {
  return (text || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^\x00-\x7f]/g, '').toLowerCase();
}

/** Same as the desktop `lookup.normalize`: drops bracketed extras and "feat." credits. */
export function normalize(text) {
  let t = ascii(text);
  t = t.replace(/[([].*?[)\]]/g, ' ');
  t = t.replace(/\b(feat|ft|featuring)\b.*/g, ' ');
  t = t.replace(/&/g, ' and ');
  return t.replace(/[^a-z0-9]+/g, ' ').trim();
}

function plain(text) {
  return ascii(text).replace(/[^a-z0-9]+/g, ' ').trim();
}

const TRACK_PREFIX = /^\s*(?:\d{1,3}|[A-D]\d{1,2})\s*[-._)\]]?\s+/;

/** Best-effort artist/title from names like "03 - Artist - Title.mp3". */
export function guessFromFilename(name) {
  let s = stem(name).replace(TRACK_PREFIX, '');
  s = s.replace(/[[(](?:official.*?|lyrics?|audio|hq|hd|\d{3,4}p)[\])]/gi, '');
  s = s.replace(/_/g, ' ').trim();
  const parts = s.split(/\s+[-–—]\s+/).map((p) => p.trim()).filter(Boolean);
  if (parts.length >= 2) return { artist: parts[0], title: parts.slice(1).join(' - ') };
  return s ? { title: s } : {};
}

// --- song versions ----------------------------------------------------------------------------

// Words that mark a different recording or arrangement. Same list as the desktop app.
const VERSION_WORDS = {
  acoustic: 'acoustic|akustik|acustic[oa]|acoustique',
  unplugged: 'unplugged',
  live: 'live|en vivo|ao vivo|en directo|in concert|concert|en concierto|live at|tour',
  demo: 'demo',
  remix: 'remix|rmx|re ?mix|club mix|dub mix|extended mix|extended|bootleg|mash ?up|vip mix',
  instrumental: 'instrumental|karaoke|backing track|minus one|off vocal',
  'a cappella': 'a ?cappella|acapella|vocals? only',
  orchestral: 'orchestral|symphonic|orchestra|philharmonic',
  piano: 'piano version|piano',
  stripped: 'stripped|session|sessions',
  cover: 'cover',
  'sped up': 'sped up|slowed|nightcore|reverb',
  're-recorded': 're ?recorded|taylor s version|new version|\\d{4} version',
};
const VERSION_RE = Object.entries(VERSION_WORDS).map(([label, words]) => [label, new RegExp(`\\b(?:${words})\\b`)]);
const NEUTRAL = /\b(?:remaster(?:ed)?|explicit|clean|mono|stereo|deluxe|bonus|album version|original version|original mix|single version|radio edit|official|audio|lyrics?|video|hq|hd|feat|ft|featuring)\b/;

function titleExtras(title) {
  const t = title || '';
  const extras = [...t.matchAll(/[([]([^)\]]*)[)\]]/g)].map((m) => m[1]);
  const parts = t.replace(/[([][^)\]]*[)\]]/g, ' ').split(/\s+[-–—]\s+/);
  return extras.concat(parts.slice(1));
}

/**
 * Which kind of recording a song is: live, acoustic, remix… (an empty list is the normal one).
 * Reads notes in the title and file name, and the album, genre and folder name.
 * @param {{name: string, folder?: string, tags?: object}} f
 */
export function versionOf(f) {
  const tags = f.tags || {};
  const notes = titleExtras(tags.title).concat(titleExtras(guessFromFilename(f.name).title || ''));
  const whole = [tags.album, tags.genre, f.folder ? f.folder.split('/').pop() : ''];
  const found = new Set();
  for (const text of notes.concat(whole)) {
    const p = plain(text);
    if (!p) continue;
    let hit = false;
    for (const [label, re] of VERSION_RE) {
      if (re.test(p)) {
        found.add(label);
        hit = true;
      }
    }
    // Any other "... version" / "... mix" note in the title is a version of its own.
    if (!hit && notes.includes(text) && /\b(?:version|mix|edit|take)\b/.test(p) && !NEUTRAL.test(p)) found.add(p);
  }
  return [...found].sort();
}

// --- grouping ---------------------------------------------------------------------------------

/** Join overlapping groups from several detectors. `labelled` is [[reason, [[file…]…]]…]. */
export function mergeGroups(labelled) {
  const parent = new Map();
  const find = (x) => {
    if (!parent.has(x)) parent.set(x, x);
    while (parent.get(x) !== x) {
      parent.set(x, parent.get(parent.get(x)));
      x = parent.get(x);
    }
    return x;
  };
  const files = new Map();
  const reasons = new Map();
  for (const [reason, groups] of labelled) {
    for (const group of groups) {
      for (const f of group) {
        files.set(f.path, f);
        const a = find(group[0].path), b = find(f.path);
        if (a !== b) parent.set(b, a);
      }
      const list = reasons.get(group[0].path) || [];
      list.push(reason);
      reasons.set(group[0].path, list);
    }
  }
  const clusters = new Map();
  for (const key of files.keys()) {
    const root = find(key);
    if (!clusters.has(root)) clusters.set(root, []);
    clusters.get(root).push(files.get(key));
  }
  const clusterReasons = new Map();
  for (const [first, rs] of reasons) {
    const root = find(first);
    const list = clusterReasons.get(root) || [];
    for (const r of rs) if (!list.includes(r)) list.push(r);
    clusterReasons.set(root, list);
  }
  const out = [];
  for (const [root, list] of clusters) {
    if (list.length < 2) continue;
    list.sort((a, b) => (a.path < b.path ? -1 : 1));
    out.push({ files: list, reason: (clusterReasons.get(root) || ['Duplicate']).join(' + '), keep: new Set([0]) });
  }
  out.sort((a, b) => wasted(b) - wasted(a));
  return out;
}

export function wasted(group) {
  return group.files.reduce((sum, f, i) => sum + (group.keep.has(i) ? 0 : f.size), 0);
}

/** Songs with the same artist + title (+ version) and lengths within 3 seconds. */
export function sameTags(files, separateVersions = true) {
  const buckets = new Map();
  for (const f of files) {
    const t = f.tags && (f.tags.title || f.tags.artist) ? f.tags : guessFromFilename(f.name);
    const artist = normalize(t.artist), title = normalize(t.title);
    if (!artist || !title) continue;
    const key = [artist, title, separateVersions ? versionOf(f).join('|') : ''].join('\u0000');
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(f);
  }
  return [...buckets.values()].filter((b) => b.length > 1);
}

/** Split a bucket wherever consecutive lengths differ by more than `seconds`. */
export function splitByDuration(bucket, seconds = 3) {
  const sorted = [...bucket].sort((a, b) => (a.duration || 0) - (b.duration || 0));
  const groups = [];
  let current = [sorted[0]];
  for (const f of sorted.slice(1)) {
    if ((f.duration || 0) - (current[current.length - 1].duration || 0) <= seconds) current.push(f);
    else {
      if (current.length > 1) groups.push(current);
      current = [f];
    }
  }
  if (current.length > 1) groups.push(current);
  return groups;
}

// --- similar photos ---------------------------------------------------------------------------

const DCT_N = 32;
let dctTable;
function dctCos() {
  if (dctTable) return dctTable;
  dctTable = new Float64Array(DCT_N * DCT_N);
  for (let k = 0; k < DCT_N; k++)
    for (let n = 0; n < DCT_N; n++) dctTable[k * DCT_N + n] = Math.cos((Math.PI / DCT_N) * (n + 0.5) * k);
  return dctTable;
}

/**
 * 64-bit perceptual hash (the same method as the desktop app's imagehash.phash): the low
 * frequencies of a 32×32 grey thumbnail, each compared with their median. `grey` holds 1024
 * brightness values, row by row. Returns [hi, lo] 32-bit numbers.
 */
export function phash(grey) {
  const c = dctCos(), N = DCT_N;
  const rows = new Float64Array(N * 8); // DCT along x, keep 8 frequencies
  for (let y = 0; y < N; y++)
    for (let k = 0; k < 8; k++) {
      let sum = 0;
      for (let x = 0; x < N; x++) sum += grey[y * N + x] * c[k * N + x];
      rows[y * 8 + k] = sum;
    }
  const low = new Float64Array(64); // then along y
  for (let k = 0; k < 8; k++)
    for (let j = 0; j < 8; j++) {
      let sum = 0;
      for (let y = 0; y < N; y++) sum += rows[y * 8 + j] * c[k * N + y];
      low[k * 8 + j] = sum;
    }
  const median = [...low].sort((a, b) => a - b)[32];
  const words = [0, 0];
  for (let i = 0; i < 64; i++) if (low[i] > median) words[i >> 5] |= 1 << (i & 31);
  return [words[0] >>> 0, words[1] >>> 0];
}

function popcount32(n) {
  n -= (n >>> 1) & 0x55555555;
  n = (n & 0x33333333) + ((n >>> 2) & 0x33333333);
  return (((n + (n >>> 4)) & 0xf0f0f0f) * 0x1010101) >>> 24;
}

/** Bits that differ between two 64-bit hashes stored as [hi, lo] 32-bit numbers. */
export function hamming(a, b) {
  return popcount32((a[0] ^ b[0]) >>> 0) + popcount32((a[1] ^ b[1]) >>> 0);
}

/**
 * Pairs of photos whose 64-bit hashes differ in at most `threshold` bits. Hashes within 7 bits
 * share at least one of their 8 bytes, so only photos sharing a byte are compared.
 */
export function similarPairs(files, threshold) {
  const pairs = [];
  const withHash = files.filter((f) => f.phash);
  if (threshold > 7) {
    for (let i = 0; i < withHash.length; i++)
      for (let j = i + 1; j < withHash.length; j++)
        if (hamming(withHash[i].phash, withHash[j].phash) <= threshold) pairs.push([withHash[i], withHash[j]]);
    return pairs;
  }
  const index = new Map();
  const seen = new Set();
  withHash.forEach((f, i) => {
    for (let k = 0; k < 8; k++) {
      const word = f.phash[k < 4 ? 0 : 1];
      const byte = (word >>> ((k % 4) * 8)) & 0xff;
      const key = k * 256 + byte;
      const list = index.get(key) || [];
      for (const j of list) {
        const id = j * 1e7 + i;
        if (seen.has(id)) continue;
        seen.add(id);
        if (hamming(withHash[j].phash, f.phash) <= threshold) pairs.push([withHash[j], f]);
      }
      list.push(i);
      index.set(key, list);
    }
  });
  return pairs;
}

// --- which copy to keep -----------------------------------------------------------------------

const COPY_NAME = /(\bcopy\b|\bkopie\b|\bcopie\b|\(\d+\)\s*$)/i;

export function quality(category, f) {
  if (category === 'music') {
    const bitrate = f.duration ? (f.size * 8) / f.duration : 0;
    return [LOSSLESS.has(ext(f.name)) ? 1 : 0, Math.round(bitrate / 1000), Object.keys(f.tags || {}).length];
  }
  if (category === 'photos' || category === 'videos') return [(f.width || 0) * (f.height || 0)];
  if (category === 'documents') {
    const editable = ['docx', 'odt', 'xlsx', 'ods', 'pptx', 'odp', 'md', 'txt'].includes(ext(f.name));
    return [editable ? 1 : 0, f.mtime || 0];
  }
  return [];
}

function compare(a, b) {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i] ?? 0, y = b[i] ?? 0;
    if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

export const KEEP = { best: 'Best quality', oldest: 'Oldest file', newest: 'Newest file', shortest: 'Shortest path' };

/** Tick the single best file of each group (same order of preference as the desktop app). */
export function chooseKeepers(groups, strategy, category) {
  for (const g of groups) {
    const key = (f) => {
      let base;
      if (strategy === 'oldest') base = [-(f.mtime || 0)];
      else if (strategy === 'newest') base = [f.mtime || 0];
      else if (strategy === 'shortest') base = [-f.path.length];
      else base = quality(category, f).concat([f.size]);
      return base.concat([COPY_NAME.test(stem(f.name)) ? 0 : 1, -(f.mtime || 0)]);
    };
    let best = 0;
    g.files.forEach((f, i) => {
      if (compare(key(f), key(g.files[best])) > 0) best = i;
    });
    g.keep = new Set([best]);
  }
}

// --- formatting -------------------------------------------------------------------------------

export function humanSize(n) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return i === 0 ? `${n} B` : `${n.toFixed(1)} ${units[i]}`;
}

export function duration(seconds) {
  if (!seconds) return '';
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** A CSV report of the groups (Excel-friendly). */
export function report(groups) {
  const q = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const rows = [['Group', 'Keep', 'File', 'Folder', 'Size (bytes)', 'Reason'].map(q).join(',')];
  groups.forEach((g, gi) =>
    g.files.forEach((f, i) =>
      rows.push([gi + 1, g.keep.has(i) ? 'keep' : 'duplicate', f.name, f.folder, f.size, g.reason].map(q).join(','))
    )
  );
  return '﻿' + rows.join('\r\n') + '\r\n';
}
