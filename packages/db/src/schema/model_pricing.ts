import { sqliteTable, text, real } from 'drizzle-orm/sqlite-core';

export const modelPricing = sqliteTable('model_pricing', {
  model_id: text('model_id').primaryKey(),
  prompt_token_cost_usd_per_million: real('prompt_token_cost_usd_per_million').notNull(),
  output_token_cost_usd_per_million: real('output_token_cost_usd_per_million').notNull(),
  effective_from: text('effective_from'),
  effective_to: text('effective_to'),
});
