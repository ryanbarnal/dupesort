import assert from 'node:assert/strict';
import test from 'node:test';

import {
  chooseKeepers, guessFromFilename, hamming, mergeGroups, normalize, phash, report, sameTags, similarPairs,
  splitByDuration, versionOf, wanted,
} from '../../web/js/core.js';

const song = (name, tags = {}, folder = 'Music', extra = {}) => ({ name, folder, path: `${folder}/${name}`, tags, size: 1000, ...extra });

test('normalize matches the desktop app', () => {
  assert.equal(normalize('Beyoncé feat. Jay-Z'), 'beyonce');
  assert.equal(normalize('Song (Remastered 2011)'), 'song');
  assert.equal(normalize('Simon & Garfunkel'), 'simon and garfunkel');
});

test('guessFromFilename', () => {
  assert.deepEqual(guessFromFilename('03 - Daft Punk - One More Time.mp3'), { artist: 'Daft Punk', title: 'One More Time' });
  assert.deepEqual(guessFromFilename('Adele - Hello (Official Video).mp3'), { artist: 'Adele', title: 'Hello' });
  assert.deepEqual(guessFromFilename('track.mp3'), { title: 'track' });
});

test('versionOf reads title, file name, album, genre and folder', () => {
  assert.deepEqual(versionOf(song('Oasis - Live Forever.mp3')), []);
  assert.deepEqual(versionOf(song('x.mp3', { title: 'Song (Acoustic)' })), ['acoustic']);
  assert.deepEqual(versionOf(song('x.mp3', { title: 'Song' }, 'Music/MTV Unplugged')), ['unplugged']);
  assert.deepEqual(versionOf(song('x.mp3', { title: 'Song', genre: 'Live' })), ['live']);
  assert.deepEqual(versionOf(song('x.mp3', { title: 'Song (Remastered 2011)' })), []);
  assert.deepEqual(versionOf(song('x.mp3', { title: 'Song (Radio Edit)' })), []);
  assert.deepEqual(versionOf(song("x.mp3", { title: "Love Story (Taylor's Version)" })), ['re-recorded']);
  assert.deepEqual(versionOf(song('Artist - Song - Live at Wembley.mp3')), ['live']);
  assert.deepEqual(versionOf(song('x.mp3', { title: 'Song (Kygo Remix)' })), ['remix']);
});

test('live, acoustic and unplugged takes are not duplicates of the studio one', () => {
  const files = [
    song('studio.mp3', { artist: 'Band', title: 'Song', album: 'Debut' }, 'M/Debut', { duration: 200 }),
    song('studio copy.mp3', { artist: 'Band', title: 'Song', album: 'Debut' }, 'M/Copies', { duration: 201 }),
    song('remaster.mp3', { artist: 'Band', title: 'Song (Remastered 2011)' }, 'M/z', { duration: 199 }),
    song('acoustic.mp3', { artist: 'Band', title: 'Song (Acoustic)' }, 'M/Singles', { duration: 200 }),
    song('unplugged.mp3', { artist: 'Band', title: 'Song', album: 'MTV Unplugged' }, 'M/x', { duration: 200 }),
    song('concert.mp3', { artist: 'Band', title: 'Song' }, 'M/Live in Concert 2004', { duration: 200 }),
    song('genre.mp3', { artist: 'Band', title: 'Song', genre: 'Live' }, 'M/y', { duration: 200 }),
  ];
  const names = (groups) => groups.map((g) => g.map((f) => f.name).sort()).sort();
  const groups = sameTags(files, true).flatMap((b) => splitByDuration(b));
  assert.deepEqual(names(groups), [['concert.mp3', 'genre.mp3'], ['remaster.mp3', 'studio copy.mp3', 'studio.mp3']]);
  assert.equal(sameTags(files, false)[0].length, 7);
});

test('songs more than 3 seconds apart are different', () => {
  const a = song('a.mp3', { artist: 'B', title: 'S' }, 'M', { duration: 120 });
  const b = song('b.mp3', { artist: 'B', title: 'S' }, 'M', { duration: 122.5 });
  const c = song('c.mp3', { artist: 'B', title: 'S' }, 'M', { duration: 300 });
  assert.deepEqual(splitByDuration([a, b, c]).map((g) => g.map((f) => f.name)), [['a.mp3', 'b.mp3']]);
});

test('mergeGroups joins overlapping groups and lists every reason', () => {
  const [a, b, c, d] = ['a', 'b', 'c', 'd'].map((n) => ({ path: n, name: n, size: 10 }));
  const groups = mergeGroups([['Identical file', [[a, b]]], ['Same artist & title', [[b, c]]], ['x', [[d]]]]);
  assert.equal(groups.length, 1);
  assert.deepEqual(groups[0].files.map((f) => f.path), ['a', 'b', 'c']);
  assert.equal(groups[0].reason, 'Identical file + Same artist & title');
});

test('the best copy is kept: lossless, higher bitrate, not "copy"', () => {
  const g = (files) => ({ files, keep: new Set([0]) });
  const mp3 = song('Song.mp3', {}, 'M', { size: 4e6, duration: 200 });
  const flac = song('Song.flac', {}, 'M', { size: 2e7, duration: 200 });
  const groups = [g([mp3, flac]), g([song('a copy.mp3', {}, 'M', { size: 5 }), song('a.mp3', {}, 'M', { size: 5 })])];
  chooseKeepers(groups, 'best', 'music');
  assert.deepEqual([...groups[0].keep], [1]);
  assert.deepEqual([...groups[1].keep], [1]);
  const old = song('old.jpg', {}, 'P', { mtime: 1 }), recent = song('new.jpg', {}, 'P', { mtime: 2 });
  const p = [g([old, recent])];
  chooseKeepers(p, 'newest', 'photos');
  assert.deepEqual([...p[0].keep], [1]);
});

test('similar photos are found by hash distance', () => {
  const ph = (name, hi, lo) => ({ name, path: name, phash: [hi >>> 0, lo >>> 0] });
  const a = ph('a', 0xdeadbeef, 0x12345678);
  const b = ph('b', 0xdeadbeef ^ 0b101, 0x12345678); // 2 bits apart
  const c = ph('c', ~0xdeadbeef, ~0x12345678); // far away
  assert.equal(hamming(a.phash, b.phash), 2);
  const pairs = similarPairs([a, b, c], 6).map((p) => p.map((f) => f.name).join(''));
  assert.deepEqual(pairs, ['ab']);
  assert.deepEqual(similarPairs([a, b, c], 0), []);
  assert.equal(similarPairs([a, b, c], 64).length, 3);
});

test('categories filter by extension and skip hidden files', () => {
  assert.ok(wanted('music', 'x.FLAC'));
  assert.ok(!wanted('music', 'x.jpg'));
  assert.ok(!wanted('photos', '.hidden.jpg'));
  assert.ok(wanted('all', 'anything.bin'));
});

test('the report is CSV with keep/duplicate per file', () => {
  const groups = [{ files: [{ name: 'a "1".mp3', folder: 'M', size: 3 }, { name: 'b.mp3', folder: 'M', size: 3 }], keep: new Set([0]), reason: 'Identical file' }];
  const csv = report(groups);
  assert.ok(csv.includes('"1","keep","a ""1"".mp3","M","3","Identical file"'));
  assert.ok(csv.includes('"1","duplicate","b.mp3"'));
});

test('phash: same picture at another brightness matches, a different picture does not', () => {
  const img = (f) => Float64Array.from({ length: 1024 }, (_, i) => f(i % 32, Math.floor(i / 32)));
  const beach = img((x, y) => 120 + 80 * Math.sin(x / 5) * Math.cos(y / 7) + (x > 20 && y < 10 ? 60 : 0));
  const brighter = img((x, y) => 1.1 * (120 + 80 * Math.sin(x / 5) * Math.cos(y / 7) + (x > 20 && y < 10 ? 60 : 0)) + 5);
  const forest = img((x, y) => 120 + 80 * Math.cos(x / 3 + y / 4) - (y > 20 ? 50 : 0));
  assert.ok(hamming(phash(beach), phash(brighter)) <= 2);
  assert.ok(hamming(phash(beach), phash(forest)) > 16);
});

test('results sort by space, name, folder, size and date', async () => {
  const { sortGroups, fileOrder } = await import('../../web/js/core.js');
  const f = (name, folder, size, mtime) => ({ name, folder, size, mtime, path: `${folder}/${name}` });
  const g1 = { files: [f('zebra.mp3', 'B', 900, 1), f('Zebra copy.mp3', 'A', 900, 5)], keep: new Set([0]) };
  const g2 = { files: [f('apple.mp3', 'D', 10000, 2), f('apple (1).mp3', 'C', 9000, 3)], keep: new Set([0]) };
  const names = (gs, s) => gs.map((g) => fileOrder(g, s).map((i) => g.files[i].name).join('|'));
  assert.deepEqual(names(sortGroups([g1, g2], 'space'), 'space'), ['apple.mp3|apple (1).mp3', 'zebra.mp3|Zebra copy.mp3']);
  assert.deepEqual(names(sortGroups([g2, g1], 'name'), 'name'), ['apple (1).mp3|apple.mp3', 'Zebra copy.mp3|zebra.mp3']);
  assert.deepEqual(names(sortGroups([g2, g1], 'folder'), 'folder'), ['Zebra copy.mp3|zebra.mp3', 'apple (1).mp3|apple.mp3']);
  assert.deepEqual(names(sortGroups([g1, g2], 'newest'), 'newest'), ['Zebra copy.mp3|zebra.mp3', 'apple (1).mp3|apple.mp3']);
  assert.deepEqual(fileOrder(g2, 'size'), [0, 1]); // positions in the group: `keep` still matches
});
