// The Key Maker page's signing code (packaging/DupeSort Key Maker.html), run in Node.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const html = readFileSync(new URL('../../packaging/DupeSort Key Maker.html', import.meta.url), 'utf8');
const core = html.match(/<script id="core">([\s\S]*?)<\/script>/)[1];
const ctx = { crypto: globalThis.crypto, TextEncoder, TextDecoder, Uint8Array, BigInt, Number, String, JSON, Date, Error, btoa, atob };
ctx.globalThis = ctx;
vm.runInNewContext(core, ctx);
const K = ctx.DupeKeys;

test('Ed25519 matches RFC 8032 test vectors', async () => {
  const vectors = [
    ['9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60', 'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
      'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'],
    ['4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb', '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
      '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00'],
  ];
  for (const [sk, pk, msg, sig] of vectors) {
    const secret = K.unhex(sk), message = msg ? K.unhex(msg) : new Uint8Array();
    assert.equal(K.hex(await K.publicKeyOf(secret)), pk);
    assert.equal(K.hex(await K.sign(secret, message)), sig);
    assert.ok(await K.verify(K.unhex(pk), message, K.unhex(sig)));
    assert.ok(!(await K.verify(K.unhex(pk), new Uint8Array([1, 2]), K.unhex(sig))));
  }
});

test('keys round-trip and fakes are rejected', async () => {
  const secret = new Uint8Array(32).map((_, i) => i);
  const pub = await K.publicKeyOf(secret);
  const key = await K.makeKey(secret, 'José Rizal', '2026-11-25');
  assert.match(key, /^DUPESORT-[A-Z2-7]{5}(-[A-Z2-7]{1,5})+$/);
  assert.deepEqual({ ...(await K.readKey(key.toLowerCase().replace(/-/g, ' '), pub)) }, { name: 'José Rizal', issued: '2026-11-25' });
  const other = await K.makeKey(new Uint8Array(32), 'José Rizal');
  assert.equal(await K.readKey(other, pub), null);
  // Change a character in the middle (the last one may only hold padding bits).
  const i = Math.floor(key.length / 2) + (key[Math.floor(key.length / 2)] === '-' ? 1 : 0);
  const tampered = key.slice(0, i) + (key[i] === 'A' ? 'B' : 'A') + key.slice(i + 1);
  assert.equal(await K.readKey(tampered, pub), null);
  assert.equal(await K.readKey('DUPESORT-HELLO', pub), null);
});

test('signing key files: plain hex or locked with a password', async () => {
  const secret = new Uint8Array(32).map((_, i) => 255 - i);
  const plain = await K.keyFileText(secret);
  assert.equal(plain.trim(), K.hex(secret));
  assert.ok(!K.isLocked(plain));
  assert.deepEqual([...(await K.secretFromFile(plain))], [...secret]);

  await assert.rejects(K.keyFileText(secret, 'short'), /at least 10/);
  const locked = await K.keyFileText(secret, 'correct horse battery');
  assert.ok(K.isLocked(locked) && !locked.includes(K.hex(secret)));
  assert.notEqual(locked, await K.keyFileText(secret, 'correct horse battery')); // fresh salt each time
  await assert.rejects(K.secretFromFile(locked), /password needed/);
  await assert.rejects(K.secretFromFile(locked, 'wrong password!!'), /wrong password/);
  assert.deepEqual([...(await K.secretFromFile(locked, 'correct horse battery'))], [...secret]);
  await assert.rejects(K.secretFromFile('hello'), /isn't a DupeSort signing key/);
});
