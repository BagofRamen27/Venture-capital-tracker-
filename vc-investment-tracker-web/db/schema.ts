import { sqliteTable, text, integer, uniqueIndex } from 'drizzle-orm/sqlite-core';
export const tracked = sqliteTable('tracked_startups', {
  id: text('id').primaryKey(), owner: text('owner').notNull(), identity: text('identity').notNull(),
  record: text('record').notNull(), createdAt: text('created_at').notNull(), updatedAt: text('updated_at').notNull(),
}, t => [uniqueIndex('tracked_owner_identity').on(t.owner,t.identity)]);
export const cache = sqliteTable('discovery_cache', {
  key: text('key').primaryKey(), payload: text('payload').notNull(), fetchedAt: integer('fetched_at').notNull(),
});
