import { sqliteTable, text, integer, index, real } from 'drizzle-orm/sqlite-core';

export const runs = sqliteTable('runs', {
  run_id: text('run_id').primaryKey(),
  parent_run_id: text('parent_run_id').references((): any => runs.run_id, { onDelete: 'set null' }),
  agent_name: text('agent_name').notNull(),
  mode: text('mode').notNull(), // normal | dry-run | eval
  input_hash: text('input_hash'),
  input_json: text('input_json'),
  model_id: text('model_id'),
  fallback_used: integer('fallback_used').default(0), // boolean
  started_at: text('started_at').notNull(),
  ended_at: text('ended_at'),
  status: text('status').notNull(), // queued | running | succeeded | failed | killed | budget_exhausted | timeout
  result_json: text('result_json'),
  total_cost_usd: real('total_cost_usd'),
  total_tokens: integer('total_tokens'),
  iterations_used: integer('iterations_used'),
  eval_suite_id: text('eval_suite_id'),
}, (table) => ({
  agentNameIdx: index('runs_agent_name_idx').on(table.agent_name),
  statusIdx: index('runs_status_idx').on(table.status),
  startedAtIdx: index('runs_started_at_idx').on(table.started_at),
}));
