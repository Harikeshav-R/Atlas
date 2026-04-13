import { eq, desc, and, sql } from 'drizzle-orm';
import type { AtlasDb } from './client.ts';
import {
  profiles, runs, traceEvents, approvals, costs, modelPricing, auditLog,
  listings, listingSnapshots, evaluations, scorecards, preferences,
} from './schema/index.ts';

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

// Listings
export function getListing(db: AtlasDb, listingId: string) {
  return db.select().from(listings).where(eq(listings.listing_id, listingId)).get();
}

export function getListingByUrl(db: AtlasDb, canonicalUrl: string) {
  return db.select().from(listings).where(eq(listings.canonical_url, canonicalUrl)).get();
}

export function insertListing(db: AtlasDb, listing: typeof listings.$inferInsert) {
  db.insert(listings).values(listing).run();
}

export function updateListing(db: AtlasDb, listingId: string, data: Partial<typeof listings.$inferInsert>) {
  db.update(listings).set(data).where(eq(listings.listing_id, listingId)).run();
}

export function listListings(db: AtlasDb, opts: { status?: string; limit?: number; offset?: number } = {}) {
  const { status, limit = 20, offset = 0 } = opts;
  let query = db.select().from(listings);
  if (status) {
    query = query.where(eq(listings.status, status)) as typeof query;
  }
  return query.orderBy(desc(listings.first_seen_at)).limit(limit).offset(offset).all();
}

// Listing Snapshots
export function insertListingSnapshot(db: AtlasDb, snapshot: typeof listingSnapshots.$inferInsert) {
  db.insert(listingSnapshots).values(snapshot).run();
}

export function getSnapshotsForListing(db: AtlasDb, listingId: string) {
  return db.select().from(listingSnapshots)
    .where(eq(listingSnapshots.listing_id, listingId))
    .orderBy(desc(listingSnapshots.captured_at))
    .all();
}

// Evaluations
export function getEvaluation(db: AtlasDb, evaluationId: string) {
  return db.select().from(evaluations).where(eq(evaluations.evaluation_id, evaluationId)).get();
}

export function getEvaluationForListing(db: AtlasDb, listingId: string, profileVersion?: number) {
  if (profileVersion !== undefined) {
    return db.select().from(evaluations)
      .where(and(eq(evaluations.listing_id, listingId), eq(evaluations.profile_version, profileVersion)))
      .get();
  }
  return db.select().from(evaluations)
    .where(eq(evaluations.listing_id, listingId))
    .orderBy(desc(evaluations.created_at))
    .get();
}

export function insertEvaluation(db: AtlasDb, evaluation: typeof evaluations.$inferInsert) {
  db.insert(evaluations).values(evaluation).run();
}

// Scorecards
export function getScorecard(db: AtlasDb, evaluationId: string) {
  return db.select().from(scorecards).where(eq(scorecards.evaluation_id, evaluationId)).get();
}

export function insertScorecard(db: AtlasDb, scorecard: typeof scorecards.$inferInsert) {
  db.insert(scorecards).values(scorecard).run();
}

// Preferences
export function getPreferences(db: AtlasDb, profileId: string) {
  return db.select().from(preferences).where(eq(preferences.profile_id, profileId)).get();
}

export function upsertPreferences(db: AtlasDb, pref: typeof preferences.$inferInsert) {
  db.insert(preferences).values(pref)
    .onConflictDoUpdate({
      target: preferences.preferences_id,
      set: {
        scoring_weights_json: pref.scoring_weights_json,
        grade_thresholds_json: pref.grade_thresholds_json,
        model_routing_json: pref.model_routing_json,
        budgets_json: pref.budgets_json,
        notification_prefs_json: pref.notification_prefs_json,
        updated_at: pref.updated_at,
      },
    })
    .run();
}
