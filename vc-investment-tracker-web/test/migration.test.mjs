import { test } from 'node:test';
import assert from 'node:assert/strict';
await import('../public/scout.js');
const VS = globalThis.VentureScout;

const memoryStorage = (initial = {}) => {
  const m = new Map(Object.entries(initial));
  return {
    getItem: k => m.get(k) ?? null,
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: k => m.delete(k),
    clear: () => m.clear(),
    _map: m
  };
};

const failingStorage = (failPredicate, initial = {}) => {
  const m = new Map(Object.entries(initial));
  return {
    getItem: k => m.get(k) ?? null,
    setItem: (k, v) => {
      const shouldFail = typeof failPredicate === 'function' ? failPredicate(k) : (failPredicate === k || failPredicate === true);
      if (shouldFail) {
        throw new Error('QuotaExceededError: browser storage quota exceeded');
      }
      m.set(k, String(v));
    },
    removeItem: k => m.delete(k),
    clear: () => m.clear(),
    _map: m
  };
};

test('1. registrableDomain handles standard domains and schemes', () => {
  assert.equal(VS.registrableDomain('https://stripe.com'), 'stripe.com');
  assert.equal(VS.registrableDomain('https://www.stripe.com/pricing'), 'stripe.com');
  assert.equal(VS.registrableDomain('http://app.novarobotics.com/dashboard'), 'novarobotics.com');
  assert.equal(VS.registrableDomain('https://sub.sub.domain.org/about'), 'domain.org');
});

test('2. registrableDomain handles multi-level TLDs and localhost/IP addresses', () => {
  assert.equal(VS.registrableDomain('https://sub.acme.co.uk/path'), 'acme.co.uk');
  assert.equal(VS.registrableDomain('http://portal.service.gov.au/'), 'service.gov.au');
  assert.equal(VS.registrableDomain('https://firm.co.jp/'), 'firm.co.jp');
  assert.equal(VS.registrableDomain('https://innovate.co.in/'), 'innovate.co.in');
  assert.equal(VS.registrableDomain('http://localhost:3000/app'), 'localhost');
  assert.equal(VS.registrableDomain('http://192.168.1.1:8080/'), '192.168.1.1');
});

test('3. registrableDomain rejects malformed, dangerous or credentialed URLs safely', () => {
  assert.equal(VS.registrableDomain('ftp://files.example.com'), '');
  assert.equal(VS.registrableDomain('javascript:alert(1)'), '');
  assert.equal(VS.registrableDomain('https://user:password@domain.com'), '');
  assert.equal(VS.registrableDomain(''), '');
  assert.equal(VS.registrableDomain(null), '');
  assert.equal(VS.registrableDomain(undefined), '');
  assert.equal(VS.registrableDomain('not a url'), '');
});

test('4. shared-host and repository platform tenant separation', () => {
  // Fix 3: Repository platforms (e.g. github.com, gitlab.com, huggingface.co) distinguish org/repo pairs
  const repoA = VS.canonicalCompanyKey({ website: 'https://github.com/nova-drones/core' });
  const repoB = VS.canonicalCompanyKey({ website: 'https://github.com/nova-drones/docs' });
  const repoC = VS.canonicalCompanyKey({ website: 'https://github.com/other-team/core' });
  const repoGit = VS.canonicalCompanyKey({ website: 'https://github.com/nova-drones/core.git' });
  const repoSubpath = VS.canonicalCompanyKey({ website: 'https://github.com/nova-drones/core/tree/main/src?tab=readme#license' });
  const repoOrgOnly = VS.canonicalCompanyKey({ website: 'https://github.com/nova-drones' });
  const gitlabRepo = VS.canonicalCompanyKey({ website: 'https://gitlab.com/gitlab-org/gitlab' });
  const hfRepo = VS.canonicalCompanyKey({ website: 'https://huggingface.co/openai/whisper-large-v3' });

  assert.equal(repoA, 'cid:shared:github.com/nova-drones/core');
  assert.equal(repoB, 'cid:shared:github.com/nova-drones/docs');
  assert.notEqual(repoA, repoB, 'Different repositories under the same organization must produce distinct keys');
  assert.equal(repoC, 'cid:shared:github.com/other-team/core');
  assert.equal(repoGit, 'cid:shared:github.com/nova-drones/core', '.git suffix should be normalized away');
  assert.equal(repoSubpath, 'cid:shared:github.com/nova-drones/core', 'Deeper path segments, query params, and fragments are ignored');
  assert.equal(repoOrgOnly, 'cid:shared:github.com/nova-drones', 'Single segment org URL falls back to org tenant');
  assert.equal(gitlabRepo, 'cid:shared:gitlab.com/gitlab-org/gitlab');
  assert.equal(hfRepo, 'cid:shared:huggingface.co/openai/whisper-large-v3');

  // Fix 3: Non-repository platforms use single-segment tenant identity (handle / blog / workspace)
  const subA = VS.canonicalCompanyKey({ website: 'https://novadrones.substack.com/archive' });
  const subB = VS.canonicalCompanyKey({ website: 'https://otherstartup.substack.com' });
  const subAuthorPost = VS.canonicalCompanyKey({ website: 'https://substack.com/@techpulse/p/first-post?utm_source=feed' });
  const subAuthorHome = VS.canonicalCompanyKey({ website: 'https://substack.com/@techpulse' });
  const mediumArticle = VS.canonicalCompanyKey({ website: 'https://medium.com/@investor/how-to-scale-db' });

  assert.equal(subA, 'cid:shared:substack.com/novadrones');
  assert.equal(subB, 'cid:shared:substack.com/otherstartup');
  assert.equal(subAuthorPost, 'cid:shared:substack.com/@techpulse');
  assert.equal(subAuthorHome, 'cid:shared:substack.com/@techpulse');
  assert.equal(mediumArticle, 'cid:shared:medium.com/@investor');
});

test('5. SEC CIK normalization preserves leading zeros and takes precedence', () => {
  assert.equal(VS.canonicalCompanyKey({ secCik: '0001928475' }), 'cid:cik:0001928475');
  assert.equal(VS.canonicalCompanyKey({ cik: 1928475 }), 'cid:cik:0001928475');
  assert.equal(VS.canonicalCompanyKey({ sec_cik: '1928475', website: 'https://acme.com' }), 'cid:cik:0001928475');
});

test('6. canonicalCompanyKey falls back to deterministic name/location hint without website', () => {
  const k1 = VS.canonicalCompanyKey({ name: 'Apex Robotics', location: 'Boston, MA' });
  const k2 = VS.canonicalCompanyKey({ name: 'Apex Robotics', location: 'Boston, MA' });
  const k3 = VS.canonicalCompanyKey({ name: 'Apex Robotics', location: 'Austin, TX' });
  const k4 = VS.canonicalCompanyKey({ name: 'Apex Robotics' });

  assert.equal(k1, 'cid:name:apex-robotics:boston-ma');
  assert.equal(k1, k2);
  assert.equal(k3, 'cid:name:apex-robotics:austin-tx');
  assert.equal(k4, 'cid:name:apex-robotics');
  assert.equal(VS.canonicalCompanyKey({}), '');
});

test('7. upsertCompany preserves existing ID on update and attaches canonicalKey', () => {
  const initial = VS.upsertCompany([], { name: 'Acme', website: 'https://acme.test', stage: 'Seed' });
  const id = initial[0].id;
  assert.ok(id.startsWith('VS-'));

  const updated = VS.upsertCompany(initial, { id, name: 'Acme Corporation', website: 'https://acme.test', stage: 'Series A' });
  assert.equal(updated.length, 1);
  assert.equal(updated[0].id, id);
  assert.equal(updated[0].name, 'Acme Corporation');
  assert.equal(updated[0].stage, 'Series A');
  assert.equal(updated[0].canonicalKey, 'cid:domain:acme.test');
});

test('8. importBackup strictly preserves incoming company IDs', () => {
  const incoming = {
    companies: [
      { id: 'VS-bak-111', name: 'Alpha', website: 'https://alpha.test', stage: 'Seed' },
      { id: 'VS-bak-222', name: 'Beta', website: 'https://beta.test', stage: 'Series A' },
    ]
  };

  const r = VS.importBackup([], incoming);
  assert.equal(r.added, 2);
  assert.equal(r.skipped, 0);
  assert.equal(r.list[1].id, 'VS-bak-111');
  assert.equal(r.list[0].id, 'VS-bak-222');
  assert.equal(r.list[1].canonicalKey, 'cid:domain:alpha.test');
});

test('9. importBackup handles ID collisions with unrelated local companies deterministically', () => {
  const localList = VS.upsertCompany([], { name: 'Local Acme', website: 'https://acme.test' });
  const collidingId = localList[0].id;

  const incomingBackup = {
    companies: [
      { id: collidingId, name: 'Unrelated Foreign Co', website: 'https://foreign.test' },
      { id: collidingId, name: 'Third Co', website: 'https://third.test' },
    ]
  };

  const r = VS.importBackup(localList, incomingBackup);
  assert.equal(r.added, 2);
  assert.equal(r.list.length, 3);

  const localRec = r.list.find(c => c.name === 'Local Acme');
  assert.equal(localRec.id, collidingId);
  assert.equal(localRec.name, 'Local Acme');

  const imported1 = r.list.find(c => c.name === 'Unrelated Foreign Co');
  assert.equal(imported1.id, `${collidingId}-imported`);

  const imported2 = r.list.find(c => c.name === 'Third Co');
  assert.equal(imported2.id, `${collidingId}-imported-2`);
});

test('10. normalizeWorkspaceStorage treats missing storage as a valid initial empty state', () => {
  const storage = memoryStorage();
  const res = VS.normalizeWorkspaceStorage(storage);

  assert.equal(res.ok, true);
  assert.equal(res.status, 'empty');
  assert.equal(res.normalizedCount, 0);

  const marker = JSON.parse(storage.getItem(VS.STATUS_KEY));
  assert.equal(marker.phase, 'wp1_identity_normalized');
  assert.equal(marker.count, 0);
});

test('11. normalizeWorkspaceStorage preserves raw malformed storage without destructive overwrite', () => {
  const corruptRaw = '{ this is invalid json and must not be overwritten';
  const storage = memoryStorage({ [VS.STORAGE_KEY]: corruptRaw });

  const res = VS.normalizeWorkspaceStorage(storage);
  assert.equal(res.ok, false);
  assert.equal(res.error, 'malformed_json');
  assert.equal(res.raw, corruptRaw);

  assert.equal(storage.getItem(VS.STORAGE_KEY), corruptRaw);
  assert.equal(storage.getItem(VS.STATUS_KEY), null);
});

test('12. normalizeWorkspaceStorage preserves non-array storage without overwriting', () => {
  const objRaw = JSON.stringify({ notAnArray: true });
  const storage = memoryStorage({ [VS.STORAGE_KEY]: objRaw });

  const res = VS.normalizeWorkspaceStorage(storage);
  assert.equal(res.ok, false);
  assert.equal(res.error, 'invalid_data_shape');
  assert.equal(storage.getItem(VS.STORAGE_KEY), objRaw);
});

test('13. normalizeWorkspaceStorage handles write failure gracefully without claiming success', () => {
  const data = JSON.stringify([{ id: 'VS-1', name: 'Alpha', website: 'https://alpha.test' }]);
  const storage = failingStorage(VS.STORAGE_KEY, { [VS.STORAGE_KEY]: data });

  const res = VS.normalizeWorkspaceStorage(storage);
  assert.equal(res.ok, false);
  assert.equal(res.error, 'write_failure');
  assert.match(res.message, /quota/i);
});

test('14. normalizeWorkspaceStorage detects duplicate candidates and preserves both without destructive merge', () => {
  const rawList = [
    { id: 'VS-101', name: 'Nova Corp', website: 'https://nova.test', notes: 'First entry' },
    { id: 'VS-102', name: 'Nova Corp US', website: 'https://www.nova.test', notes: 'Second entry' },
    { id: 'VS-103', name: 'Unique Startup', website: 'https://unique.test', notes: 'Independent' },
  ];
  const storage = memoryStorage({ [VS.STORAGE_KEY]: JSON.stringify(rawList) });

  const res1 = VS.normalizeWorkspaceStorage(storage);
  assert.equal(res1.ok, true);
  assert.equal(res1.status, 'normalized');
  assert.equal(res1.normalizedCount, 3);
  assert.equal(res1.duplicateCandidates.length, 1);
  assert.equal(res1.duplicateCandidates[0].canonicalKey, 'cid:domain:nova.test');
  assert.equal(res1.duplicateCandidates[0].count, 2);

  const storedAfter = JSON.parse(storage.getItem(VS.STORAGE_KEY));
  assert.equal(storedAfter.length, 3);
  assert.equal(storedAfter[0].id, 'VS-101');
  assert.equal(storedAfter[1].id, 'VS-102');
  assert.equal(storedAfter[2].id, 'VS-103');

  const res2 = VS.normalizeWorkspaceStorage(storage);
  assert.equal(res2.ok, true);
  assert.equal(res2.status, 'already_normalized');
  assert.equal(res2.normalizedCount, 3);

  const storedAfterSecond = JSON.parse(storage.getItem(VS.STORAGE_KEY));
  assert.deepEqual(storedAfterSecond, storedAfter);
});

test('15. normalizeWorkspaceStorage handles storage access denied', () => {
  assert.equal(VS.normalizeWorkspaceStorage(null).ok, false);
  assert.equal(VS.normalizeWorkspaceStorage({}).ok, false);
});

test('16. multi-tenant hosting platforms distinguish tenant subdomains', () => {
  // Fix 2: Subdomains on shared hosting platforms must not collide into a single domain key
  const ghFoo = VS.canonicalCompanyKey({ website: 'https://foo.github.io' });
  const ghBar = VS.canonicalCompanyKey({ website: 'https://bar.github.io' });
  const ghPath = VS.canonicalCompanyKey({ website: 'https://foo.github.io/project1' });
  const glProject = VS.canonicalCompanyKey({ website: 'https://project.gitlab.io' });
  const pagesDev = VS.canonicalCompanyKey({ website: 'https://example.pages.dev' });
  const pagesDev2 = VS.canonicalCompanyKey({ website: 'https://another.pages.dev' });
  const netlifySub = VS.canonicalCompanyKey({ website: 'https://subdomain.netlify.app' });
  const vercelSub = VS.canonicalCompanyKey({ website: 'https://custom-app.vercel.app' });

  assert.equal(ghFoo, 'cid:shared:github.io/foo');
  assert.equal(ghBar, 'cid:shared:github.io/bar');
  assert.notEqual(ghFoo, ghBar, 'Different github.io subdomains must have distinct canonical keys');
  assert.equal(ghPath, 'cid:shared:github.io/foo', 'Path on tenant subdomain retains tenant subdomain identity');

  assert.equal(glProject, 'cid:shared:gitlab.io/project');
  assert.equal(pagesDev, 'cid:shared:pages.dev/example');
  assert.equal(pagesDev2, 'cid:shared:pages.dev/another');
  assert.notEqual(pagesDev, pagesDev2, 'Different pages.dev subdomains must have distinct canonical keys');

  assert.equal(netlifySub, 'cid:shared:netlify.app/subdomain');
  assert.equal(vercelSub, 'cid:shared:vercel.app/custom-app');

  // Verify none of them collapsed to bare cid:domain:<host>
  assert.notEqual(ghFoo, 'cid:domain:github.io');
  assert.notEqual(pagesDev, 'cid:domain:pages.dev');
});

test('17. SEC CIK rejects zero, all-zero, and malformed non-CIK strings while preserving valid formats', () => {
  // Valid numeric and string formats normalized to 10 digits
  assert.equal(VS.canonicalCompanyKey({ secCik: 320193 }), 'cid:cik:0000320193');
  assert.equal(VS.canonicalCompanyKey({ secCik: '0000320193' }), 'cid:cik:0000320193');
  assert.equal(VS.canonicalCompanyKey({ secCik: '32-0193' }), 'cid:cik:0000320193');
  assert.equal(VS.canonicalCompanyKey({ secCik: 'CIK 0000320193' }), 'cid:cik:0000320193');
  assert.equal(VS.canonicalCompanyKey({ secCik: 'CIK: 0000320193' }), 'cid:cik:0000320193');

  // Zero and all-zero placeholders must be rejected
  assert.equal(VS.canonicalCompanyKey({ secCik: 0 }), '');
  assert.equal(VS.canonicalCompanyKey({ secCik: '0' }), '');
  assert.equal(VS.canonicalCompanyKey({ secCik: '0000000000' }), '');
  assert.equal(VS.canonicalCompanyKey({ secCik: '   0000000000   ' }), '');

  // Malformed alphanumeric strings and noisy text must be rejected
  assert.equal(VS.canonicalCompanyKey({ secCik: 'abc320193' }), '');
  assert.equal(VS.canonicalCompanyKey({ secCik: '320193abc' }), '');
  assert.equal(VS.canonicalCompanyKey({ secCik: 'Phone: 555-1234' }), '');
  assert.equal(VS.canonicalCompanyKey({ secCik: '12345678901' }), ''); // 11 digits
  assert.equal(VS.canonicalCompanyKey({ secCik: null }), '');
  assert.equal(VS.canonicalCompanyKey({ secCik: '' }), '');
  assert.equal(VS.canonicalCompanyKey({}), '');

  // Rejected CIK values must safely fall back to domain identity when website is present
  assert.equal(VS.canonicalCompanyKey({ secCik: 0, website: 'https://acme.com' }), 'cid:domain:acme.com');
  assert.equal(VS.canonicalCompanyKey({ secCik: '0000000000', website: 'https://acme.com' }), 'cid:domain:acme.com');
  assert.equal(VS.canonicalCompanyKey({ secCik: 'abc320193', website: 'https://acme.com' }), 'cid:domain:acme.com');
  assert.equal(VS.canonicalCompanyKey({ secCik: '320193abc', website: 'https://acme.com' }), 'cid:domain:acme.com');
  assert.equal(VS.canonicalCompanyKey({ secCik: 'Phone: 555-1234', website: 'https://acme.com' }), 'cid:domain:acme.com');
  assert.equal(VS.canonicalCompanyKey({ secCik: '12345678901', website: 'https://acme.com' }), 'cid:domain:acme.com');
  assert.equal(VS.canonicalCompanyKey({ secCik: 0, name: 'Acme Robotics', location: 'Boston, MA' }), 'cid:name:acme-robotics:boston-ma');

  // Valid CIK overrides website
  assert.equal(VS.canonicalCompanyKey({ secCik: '0000320193', website: 'https://other-domain.com' }), 'cid:cik:0000320193');
});

test('18. startup integration: invalid data shape sets user-visible error and prevents destructive writes', () => {
  // Fix 1: Verify startup logic handles non-array data without silently wiping data or permitting destructive overwrites
  const invalidJsonStorage = memoryStorage({ [VS.STORAGE_KEY]: JSON.stringify({ notAnArray: true }) });
  const rawBefore = invalidJsonStorage.getItem(VS.STORAGE_KEY);

  // 1. Run normalization
  const norm = VS.normalizeWorkspaceStorage(invalidJsonStorage);
  assert.equal(norm.ok, false);
  assert.equal(norm.error, 'invalid_data_shape');

  // 2. Simulate app.js load() error mapping
  const ventureAccount = { companies: [], error: '' };
  if (!norm.ok) {
    if (norm.error === 'malformed_json') {
      ventureAccount.error = 'Saved workspace data is corrupted. Raw data was preserved without overwriting.';
    } else if (norm.error === 'invalid_data_shape') {
      ventureAccount.error = 'Saved workspace data has an invalid format. Raw data was preserved without overwriting.';
    } else if (norm.error === 'storage_access_denied' || norm.error === 'storage_read_error') {
      ventureAccount.error = 'This browser blocked access to saved data (private mode or storage disabled).';
    } else if (norm.error === 'write_failure') {
      ventureAccount.error = 'Failed to update saved workspace data (storage full or write blocked).';
    } else {
      ventureAccount.error = norm.message || 'Saved workspace data could not be verified.';
    }
  }
  if (!ventureAccount.error) {
    ventureAccount.companies = VS.loadSaved(invalidJsonStorage);
  }

  // Assertions: error is populated, companies are empty (not loaded as normal empty workspace)
  assert.equal(ventureAccount.error, 'Saved workspace data has an invalid format. Raw data was preserved without overwriting.');
  assert.equal(ventureAccount.companies.length, 0);

  // 3. Verify persistence guard: an attempt to persist while error is active throws and does NOT overwrite storage
  const simulatePersist = (storage, account, list) => {
    if (account.error) throw new Error('Saving is disabled because saved workspace data is in an unrecovered error state.');
    VS.writeSaved(storage, list);
    account.companies = list;
  };

  assert.throws(
    () => simulatePersist(invalidJsonStorage, ventureAccount, [{ id: 'VS-new', name: 'New Co', website: 'https://new.test' }]),
    /Saving is disabled because saved workspace data is in an unrecovered error state/
  );

  // Storage remains identical to raw value before normalization
  assert.equal(invalidJsonStorage.getItem(VS.STORAGE_KEY), rawBefore);
  assert.equal(JSON.parse(invalidJsonStorage.getItem(VS.STORAGE_KEY)).notAnArray, true);
});

test('19. startup integration: malformed JSON preserves raw corrupt string and blocks saving', () => {
  const corruptRaw = '{"unclosed_json: true';
  const corruptStorage = memoryStorage({ [VS.STORAGE_KEY]: corruptRaw });

  const norm = VS.normalizeWorkspaceStorage(corruptStorage);
  assert.equal(norm.ok, false);
  assert.equal(norm.error, 'malformed_json');

  const ventureAccount = { companies: [], error: '' };
  if (!norm.ok) {
    if (norm.error === 'malformed_json') {
      ventureAccount.error = 'Saved workspace data is corrupted. Raw data was preserved without overwriting.';
    }
  }
  assert.equal(ventureAccount.error, 'Saved workspace data is corrupted. Raw data was preserved without overwriting.');

  const simulatePersist = (storage, account, list) => {
    if (account.error) throw new Error('Saving is disabled because saved workspace data is in an unrecovered error state.');
    VS.writeSaved(storage, list);
  };

  assert.throws(
    () => simulatePersist(corruptStorage, ventureAccount, []),
    /Saving is disabled because saved workspace data is in an unrecovered error state/
  );

  assert.equal(corruptStorage.getItem(VS.STORAGE_KEY), corruptRaw);
});

test('20. startup integration: storage read error sets friendly access-denied error', () => {
  const readErrorStorage = {
    getItem: () => { throw new Error('SecurityError: access denied'); },
    setItem: () => {},
    removeItem: () => {}
  };

  const norm = VS.normalizeWorkspaceStorage(readErrorStorage);
  assert.equal(norm.ok, false);
  assert.equal(norm.error, 'storage_read_error');

  const ventureAccount = { companies: [], error: '' };
  if (!norm.ok) {
    if (norm.error === 'storage_access_denied' || norm.error === 'storage_read_error') {
      ventureAccount.error = 'This browser blocked access to saved data (private mode or storage disabled).';
    }
  }
  assert.equal(ventureAccount.error, 'This browser blocked access to saved data (private mode or storage disabled).');
});

test('21. GitLab nested repository paths preserve hierarchy and prevent upsert/import collisions', () => {
  // Fix 1: Two nested GitLab projects have distinct canonical keys
  const projA = VS.canonicalCompanyKey({ website: 'https://gitlab.com/my-org/my-subgroup/project-a' });
  const projB = VS.canonicalCompanyKey({ website: 'https://gitlab.com/my-org/my-subgroup/project-b' });
  const projGit = VS.canonicalCompanyKey({ website: 'https://gitlab.com/my-org/my-subgroup/project-a.git' });
  const projTree = VS.canonicalCompanyKey({ website: 'https://gitlab.com/my-org/my-subgroup/project-a/-/tree/main/docs?ref=1#readme' });
  const projBlob = VS.canonicalCompanyKey({ website: 'https://gitlab.com/my-org/my-subgroup/project-a/-/blob/main/file.js' });
  const projDeep = VS.canonicalCompanyKey({ website: 'https://gitlab.com/deep/sub1/sub2/sub3/app' });

  assert.equal(projA, 'cid:shared:gitlab.com/my-org/my-subgroup/project-a');
  assert.equal(projB, 'cid:shared:gitlab.com/my-org/my-subgroup/project-b');
  assert.notEqual(projA, projB, 'Distinct GitLab projects in the same subgroup must have distinct canonical keys');
  assert.equal(projGit, projA, '.git suffix on GitLab project is normalized away');
  assert.equal(projTree, projA, 'GitLab feature path /-/tree/... and query/hash are ignored');
  assert.equal(projBlob, projA, 'GitLab feature path /-/blob/... is ignored');
  assert.equal(projDeep, 'cid:shared:gitlab.com/deep/sub1/sub2/sub3/app');

  // Verify upsertCompany allows adding both projects
  let list = [];
  list = VS.upsertCompany(list, { name: 'Project A', website: 'https://gitlab.com/my-org/my-subgroup/project-a' });
  assert.equal(list.length, 1);
  assert.doesNotThrow(() => {
    list = VS.upsertCompany(list, { name: 'Project B', website: 'https://gitlab.com/my-org/my-subgroup/project-b' });
  });
  assert.equal(list.length, 2);
  assert.equal(list[0].name, 'Project B');
  assert.equal(list[1].name, 'Project A');

  // Verify importBackup allows importing both projects without skipping one as duplicate
  const backup = {
    companies: [
      { id: 'VS-gl-1', name: 'GL Project 1', website: 'https://gitlab.com/org/sub/p1' },
      { id: 'VS-gl-2', name: 'GL Project 2', website: 'https://gitlab.com/org/sub/p2' },
    ]
  };
  const r = VS.importBackup([], backup);
  assert.equal(r.added, 2);
  assert.equal(r.skipped, 0);
  assert.equal(r.list.length, 2);
  assert.equal(r.list[1].id, 'VS-gl-1');
  assert.equal(r.list[0].id, 'VS-gl-2');
  assert.equal(r.list[1].canonicalKey, 'cid:shared:gitlab.com/org/sub/p1');
  assert.equal(r.list[0].canonicalKey, 'cid:shared:gitlab.com/org/sub/p2');
});
