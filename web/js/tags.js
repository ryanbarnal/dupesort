// Reads title / artist / album / genre from music files: ID3v2 + ID3v1 (MP3, AIFF, WAV),
// FLAC and Ogg/Opus Vorbis comments, and MP4/M4A atoms. Only the bytes needed are read.
// `read(offset, length)` returns a Promise<Uint8Array>; `size` is the file size.

const FIELDS = ['title', 'artist', 'album', 'genre'];

function latin1(b) {
  let s = '';
  for (const c of b) s += String.fromCharCode(c);
  return s;
}

function decode(bytes, encoding) {
  try {
    return new TextDecoder(encoding).decode(bytes);
  } catch {
    return latin1(bytes);
  }
}

function clean(s) {
  return (s || '').replace(/\u0000+$/g, '').replace(/\u0000/g, ' / ').trim();
}

function synchsafe(b, o) {
  return ((b[o] & 0x7f) << 21) | ((b[o + 1] & 0x7f) << 14) | ((b[o + 2] & 0x7f) << 7) | (b[o + 3] & 0x7f);
}

function be32(b, o) {
  return ((b[o] << 24) >>> 0) + (b[o + 1] << 16) + (b[o + 2] << 8) + b[o + 3];
}

function le32(b, o) {
  return (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0;
}

// ID3v1 genres 0-79 (the common ones; others are written as text anyway).
const GENRES = ['Blues', 'Classic Rock', 'Country', 'Dance', 'Disco', 'Funk', 'Grunge', 'Hip-Hop', 'Jazz', 'Metal',
  'New Age', 'Oldies', 'Other', 'Pop', 'R&B', 'Rap', 'Reggae', 'Rock', 'Techno', 'Industrial', 'Alternative', 'Ska',
  'Death Metal', 'Pranks', 'Soundtrack', 'Euro-Techno', 'Ambient', 'Trip-Hop', 'Vocal', 'Jazz+Funk', 'Fusion', 'Trance',
  'Classical', 'Instrumental', 'Acid', 'House', 'Game', 'Sound Clip', 'Gospel', 'Noise', 'AlternRock', 'Bass', 'Soul',
  'Punk', 'Space', 'Meditative', 'Instrumental Pop', 'Instrumental Rock', 'Ethnic', 'Gothic', 'Darkwave',
  'Techno-Industrial', 'Electronic', 'Pop-Folk', 'Eurodance', 'Dream', 'Southern Rock', 'Comedy', 'Cult', 'Gangsta',
  'Top 40', 'Christian Rap', 'Pop/Funk', 'Jungle', 'Native American', 'Cabaret', 'New Wave', 'Psychadelic', 'Rave',
  'Showtunes', 'Trailer', 'Lo-Fi', 'Tribal', 'Acid Punk', 'Acid Jazz', 'Polka', 'Retro', 'Musical', 'Rock & Roll',
  'Hard Rock'];

function genreName(g) {
  const m = /^\((\d+)\)(.*)$/.exec(g || '') || /^(\d+)$/.exec(g || '');
  if (!m) return g;
  return (m[2] && m[2].trim()) || GENRES[+m[1]] || g;
}

function id3Text(frame) {
  const enc = frame[0];
  const body = frame.subarray(1);
  if (enc === 1 || enc === 2) {
    // UTF-16 with or without BOM.
    if (body[0] === 0xff && body[1] === 0xfe) return decode(body.subarray(2), 'utf-16le');
    if (body[0] === 0xfe && body[1] === 0xff) return decode(body.subarray(2), 'utf-16be');
    return decode(body, enc === 2 ? 'utf-16be' : 'utf-16le');
  }
  if (enc === 3) return decode(body, 'utf-8');
  return latin1(body);
}

async function readId3v2(read, size) {
  const head = await read(0, 10);
  if (latin1(head.subarray(0, 3)) !== 'ID3') return null;
  const version = head[3];
  const flags = head[5];
  const length = synchsafe(head, 6);
  const b = await read(10, Math.min(length, size - 10, 4 * 1024 * 1024));
  const ids = version === 2
    ? { TT2: 'title', TP1: 'artist', TAL: 'album', TCO: 'genre' }
    : { TIT2: 'title', TPE1: 'artist', TALB: 'album', TCON: 'genre' };
  const tags = {};
  let o = 0;
  if (version >= 3 && flags & 0x40) o += version === 4 ? synchsafe(b, 0) : be32(b, 0) + 4; // extended header
  const idLen = version === 2 ? 3 : 4, headLen = version === 2 ? 6 : 10;
  while (o + headLen <= b.length) {
    const id = latin1(b.subarray(o, o + idLen));
    if (!/^[A-Z0-9]+$/.test(id)) break;
    const len = version === 2 ? (b[o + 3] << 16) | (b[o + 4] << 8) | b[o + 5]
      : version === 4 ? synchsafe(b, o + 4) : be32(b, o + 4);
    if (len <= 0 || o + headLen + len > b.length) break;
    const field = ids[id];
    if (field && !tags[field]) {
      const text = clean(id3Text(b.subarray(o + headLen, o + headLen + len)));
      if (text) tags[field] = field === 'genre' ? genreName(text) : text;
    }
    o += headLen + len;
  }
  return tags;
}

async function readId3v1(read, size) {
  if (size < 128) return null;
  const b = await read(size - 128, 128);
  if (latin1(b.subarray(0, 3)) !== 'TAG') return null;
  const field = (from, to) => clean(latin1(b.subarray(from, to)));
  const tags = { title: field(3, 33), artist: field(33, 63), album: field(63, 93) };
  if (b[127] < GENRES.length) tags.genre = GENRES[b[127]];
  for (const k of Object.keys(tags)) if (!tags[k]) delete tags[k];
  return tags;
}

function vorbisComments(b, o) {
  const tags = {};
  const vendor = le32(b, o);
  o += 4 + vendor;
  const count = le32(b, o);
  o += 4;
  const map = { TITLE: 'title', ARTIST: 'artist', ALBUM: 'album', GENRE: 'genre' };
  for (let i = 0; i < count && o + 4 <= b.length; i++) {
    const len = le32(b, o);
    o += 4;
    const text = decode(b.subarray(o, o + len), 'utf-8');
    o += len;
    const eq = text.indexOf('=');
    const field = map[text.slice(0, eq).toUpperCase()];
    if (field && !tags[field]) tags[field] = clean(text.slice(eq + 1));
  }
  return tags;
}

async function readFlac(read, size) {
  const sig = await read(0, 4);
  if (latin1(sig) !== 'fLaC') return null;
  let o = 4;
  while (o + 4 <= size) {
    const h = await read(o, 4);
    const last = h[0] & 0x80, type = h[0] & 0x7f, len = (h[1] << 16) | (h[2] << 8) | h[3];
    if (type === 4) return vorbisComments(await read(o + 4, len), 0);
    if (last) break;
    o += 4 + len;
  }
  return {};
}

async function readOgg(read, size) {
  const b = await read(0, Math.min(size, 256 * 1024));
  if (latin1(b.subarray(0, 4)) !== 'OggS') return null;
  const s = latin1(b);
  for (const [marker, skip] of [['\x03vorbis', 7], ['OpusTags', 8]]) {
    const i = s.indexOf(marker);
    if (i >= 0) return vorbisComments(b, i + skip);
  }
  return {};
}

async function readMp4(read, size) {
  const map = { '©nam': 'title', '©ART': 'artist', '©alb': 'album', '©gen': 'genre' };
  const tags = {};
  async function walk(start, end, path) {
    let o = start;
    while (o + 8 <= end) {
      const h = await read(o, 16);
      let len = be32(h, 0);
      const type = latin1(h.subarray(4, 8));
      let head = 8;
      if (len === 1) {
        len = be32(h, 8) * 2 ** 32 + be32(h, 12);
        head = 16;
      } else if (len === 0) len = end - o;
      if (len < head) return;
      if (path === '' && o === 0 && type !== 'ftyp') return;
      if (['moov', 'udta', 'ilst'].includes(type)) await walk(o + head, o + len, path + '/' + type);
      else if (type === 'meta') await walk(o + head + 4, o + len, path + '/meta'); // meta has 4 flag bytes
      else if (path.endsWith('/ilst') && (map[type] || type === 'gnre')) {
        const b = await read(o + head, Math.min(len - head, 64 * 1024));
        // child "data" atom: size(4) "data"(4) type(4) locale(4) value
        if (latin1(b.subarray(4, 8)) === 'data') {
          const value = b.subarray(16, be32(b, 0));
          if (type === 'gnre') {
            const n = (value[0] << 8) | value[1];
            if (!tags.genre && GENRES[n - 1]) tags.genre = GENRES[n - 1];
          } else if (!tags[map[type]]) tags[map[type]] = clean(decode(value, 'utf-8'));
        }
      }
      o += len;
    }
  }
  await walk(0, size, '');
  return tags;
}

/** Tags of a music file, or {} when it has none (or can't be read). */
export async function readTags(read, size) {
  try {
    const head = latin1(await read(0, 12));
    let tags = null;
    if (head.startsWith('ID3')) tags = await readId3v2(read, size);
    else if (head.startsWith('fLaC')) tags = await readFlac(read, size);
    else if (head.startsWith('OggS')) tags = await readOgg(read, size);
    else if (head.slice(4, 8) === 'ftyp') tags = await readMp4(read, size);
    if (!tags || !FIELDS.some((f) => tags[f])) {
      const v1 = await readId3v1(read, size);
      if (v1) tags = { ...v1, ...(tags || {}) };
    }
    return tags || {};
  } catch {
    return {};
  }
}

/** A `read` function for a browser File / Blob. */
export function blobReader(blob) {
  return async (offset, length) => new Uint8Array(await blob.slice(offset, offset + length).arrayBuffer());
}
