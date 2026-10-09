import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
await import('../public/scout.js');
const VS = globalThis.VentureScout;
const DIR = new URL('../public/contributors/', import.meta.url);

test('contributor entries are cleaned and unsafe values rejected', () => {
  assert.deepEqual(VS.validateContributor({ name: '  Ada  ' }), { name: 'Ada', role: 'Contributor', github: '', photo: '', joined: '', contribution: '' });
  assert.throws(() => VS.validateContributor({ name: '' }), /needs a name/);
  assert.throws(() => VS.validateContributor({ name: 'X', photo: 'https://evil.test/a.jpg' }), /file name/);
  assert.throws(() => VS.validateContributor({ name: 'X', photo: '../secret.jpg' }), /file name/);
  assert.throws(() => VS.validateContributor({ name: 'X', photo: 'me.svg' }), /file name/);
  assert.throws(() => VS.validateContributor({ name: 'X', github: 'a b' }), /GitHub username/);
  assert.throws(() => VS.validateContributor({ name: 'X', joined: 'yesterday' }), /2026-10/);
  assert.equal(VS.validateContributor({ name: 'X', contribution: 'y'.repeat(500) }).contribution.length, 200);
});

// Runs on every pull request, so a contributor's entry is checked before it can be merged.
test('the hall of contributors list is valid and every photo exists and is small', () => {
  const { contributors } = JSON.parse(fs.readFileSync(new URL('contributors.json', DIR), 'utf8'));
  assert.ok(Array.isArray(contributors) && contributors.length > 0);
  const names = new Set();
  for (const entry of contributors) {
    const c = VS.validateContributor(entry);
    assert.ok(!names.has(c.name.toLowerCase()), `${c.name} is listed twice`);
    names.add(c.name.toLowerCase());
    if (c.photo) {
      const file = new URL(c.photo, DIR);
      assert.ok(fs.existsSync(file), `${c.name}: photo ${c.photo} is missing from public/contributors/`);
      assert.ok(fs.statSync(file).size <= VS.CONTRIBUTOR_PHOTO_MAX_BYTES, `${c.name}: photo is larger than 300 KB`);
    }
  }
});
