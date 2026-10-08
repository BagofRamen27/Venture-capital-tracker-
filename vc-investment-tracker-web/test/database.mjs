import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
export function database(file=':memory:') {
  const db=new DatabaseSync(file);
  db.exec('CREATE TABLE IF NOT EXISTS local_migrations (name TEXT PRIMARY KEY)');
  for(const name of fs.readdirSync(new URL('../drizzle/',import.meta.url)).filter(n=>n.endsWith('.sql')).sort()){
    if(db.prepare('SELECT name FROM local_migrations WHERE name=?').get(name))continue;
    db.exec(fs.readFileSync(new URL('../drizzle/'+name,import.meta.url),'utf8'));
    db.prepare('INSERT INTO local_migrations VALUES (?)').run(name);
  }
  return {
    prepare(sql) {
      return { bind(...args) {
        return {
          async first() { return db.prepare(sql).get(...args) || null; },
          async all() { return {results: db.prepare(sql).all(...args)}; },
          async run() { return {meta: db.prepare(sql).run(...args)}; }
        };
      }};
    },
    close() { db.close(); }
  };
}
