import assert from 'node:assert/strict';
import test from 'node:test';

import { readTags } from '../../web/js/tags.js';

const bytes = (...parts) => {
  const arrays = parts.map((p) => (typeof p === 'string' ? Buffer.from(p, 'latin1') : Buffer.from(p)));
  return new Uint8Array(Buffer.concat(arrays));
};
const reader = (b) => async (o, n) => b.subarray(o, o + n);
const be32 = (n) => [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255];
const le32 = (n) => [n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255];
const syncsafe = (n) => [(n >> 21) & 127, (n >> 14) & 127, (n >> 7) & 127, n & 127];

function id3v24(frames) {
  const body = Buffer.concat(frames.map(([id, text, enc = 3]) => {
    const data = enc === 1 ? Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from(text, 'utf16le')]) : Buffer.from(text, 'utf8');
    return Buffer.concat([Buffer.from(id, 'latin1'), Buffer.from(syncsafe(data.length + 1)), Buffer.from([0, 0, enc]), data]);
  }));
  return bytes('ID3', [4, 0, 0], syncsafe(body.length), body, [0xff, 0xfb, 0x90, 0]);
}

test('ID3v2.4 (UTF-8 and UTF-16)', async () => {
  const b = id3v24([['TIT2', 'Café (Live)'], ['TPE1', 'Björk', 1], ['TALB', 'Debut'], ['TCON', '(17)']]);
  assert.deepEqual(await readTags(reader(b), b.length), { title: 'Café (Live)', artist: 'Björk', album: 'Debut', genre: 'Rock' });
});

test('ID3v1 at the end of the file', async () => {
  const pad = (s, n) => Buffer.concat([Buffer.from(s, 'latin1'), Buffer.alloc(n - s.length)]);
  const b = bytes([0xff, 0xfb, 0x90, 0], 'xxxx', 'TAG', pad('Song', 30), pad('Band', 30), pad('Album', 30), pad('', 34), [13]);
  assert.deepEqual(await readTags(reader(b), b.length), { title: 'Song', artist: 'Band', album: 'Album', genre: 'Pop' });
});

test('FLAC Vorbis comments', async () => {
  const comments = ['TITLE=Song (Acoustic)', 'ARTIST=Band', 'GENRE=Folk'].map((c) => Buffer.from(c, 'utf8'));
  const vc = Buffer.concat([Buffer.from(le32(3)), Buffer.from('lib'), Buffer.from(le32(comments.length)),
    ...comments.flatMap((c) => [Buffer.from(le32(c.length)), c])]);
  const streaminfo = Buffer.alloc(34);
  const b = bytes('fLaC', [0, 0, 0, 34], streaminfo, [0x84, (vc.length >> 16) & 255, (vc.length >> 8) & 255, vc.length & 255], vc);
  assert.deepEqual(await readTags(reader(b), b.length), { title: 'Song (Acoustic)', artist: 'Band', genre: 'Folk' });
});

test('MP4 / M4A atoms', async () => {
  const atom = (type, ...children) => {
    const body = Buffer.concat(children.map((c) => Buffer.from(c)));
    return Buffer.concat([Buffer.from(be32(body.length + 8)), Buffer.from(type, 'latin1'), body]);
  };
  const text = (type, value) => atom(type, atom('data', Buffer.concat([Buffer.from([0, 0, 0, 1, 0, 0, 0, 0]), Buffer.from(value, 'utf8')])));
  const ilst = atom('ilst', text('©nam', 'Song'), text('©ART', 'Band'), text('©alb', 'MTV Unplugged'));
  const meta = atom('meta', Buffer.alloc(4), atom('hdlr', Buffer.alloc(25)), ilst);
  const b = new Uint8Array(Buffer.concat([atom('ftyp', Buffer.from('M4A \0\0\0\0')), atom('mdat', Buffer.alloc(100)), atom('moov', atom('udta', meta))]));
  assert.deepEqual(await readTags(reader(b), b.length), { title: 'Song', artist: 'Band', album: 'MTV Unplugged' });
});

test('files without tags give {}', async () => {
  const b = bytes('RIFF', [0, 0, 0, 0], 'WAVEfmt ');
  assert.deepEqual(await readTags(reader(b), b.length), {});
  assert.deepEqual(await readTags(async () => { throw new Error('io'); }, 10), {});
});
