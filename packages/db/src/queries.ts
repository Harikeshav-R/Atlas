import { eq } from 'drizzle-orm';
import type { AtlasDb } from './client.ts';
import { profiles, runs, traceEvents, approvals, costs, modelPricing, auditLog } from './schema/index.ts';

// Profiles
export function getProfile(db: AtlasDb, profileId: string) {
  return db.select().from(profiles).where(eq(profiles.profile_id, profileId)).get();
}
export function insertProfile(db: AtlasDb, profile: typeof profiles.$inferInsert) {
  db.insert(profiles).values(profile).run();
}

// Runs
export function getRun(db: AtlasDb, runId: string) {
  return db.select().from(runs).where(eq(runs.run_id, runId)).get();
}
export function insertRun(db: AtlasDb, run: typeof runs.$inferInsert) {
  db.insert(runs).values(run).run();
}
export function updateRunStatus(db: AtlasDb, runId: string, status: string, endedAt?: string, resultJson?: string) {
  db.update(runs)
    .set({ status, ended_at: endedAt, result_json: resultJson })
    .where(eq(runs.run_id, runId))
    .run();
}

// Trace Events
export function insertTraceEvent(db: AtlasDb, event: typeof traceEvents.$inferInsert) {
  db.insert(traceEvents).values(event).run();
}
export function getTraceEventsForRun(db: AtlasDb, runId: string) {
  return db.select().from(traceEvents).where(eq(traceEvents.run_id, runId)).orderBy(traceEvents.step_index).all();
}

// Approvals
export function insertApproval(db: AtlasDb, approval: typeof approvals.$inferInsert) {
  db.insert(approvals).values(approval).run();
}
export function getApproval(db: AtlasDb, approvalId: string) {
  return db.select().from(approvals).where(eq(approvals.approval_id, approvalId)).get();
}
export function updateApprovalResponse(db: AtlasDb, approvalId: string, status: string, responseJson: string, respondedAt: string) {
  db.update(approvals)
    .set({ status, user_response_json: responseJson, responded_at: respondedAt })
    .where(eq(approvals.approval_id, approvalId))
    .run();
}

// Costs
export function insertCost(db: AtlasDb, cost: typeof costs.$inferInsert) {
  db.insert(costs).values(cost).run();
}

// Model Pricing
export function getModelPricing(db: AtlasDb, modelId: string) {
  return db.select().from(modelPricing).where(eq(modelPricing.model_id, modelId)).get();
}
export function insertModelPricing(db: AtlasDb, pricing: typeof modelPricing.$inferInsert) {
  db.insert(modelPricing).values(pricing).run();
}

// Audit Log
export function insertAuditLog(db: AtlasDb, log: typeof auditLog.$inferInsert) {
  db.insert(auditLog).values(log).run();
}
