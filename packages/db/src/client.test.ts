import { describe, it, expect, beforeEach } from 'vitest';
import { createDb, type AtlasDb } from './client.ts';
import * as queries from './queries.ts';

describe('Database Phase 0 tables', () => {
  let db: AtlasDb;

  beforeEach(() => {
    db = createDb(':memory:');
  });

  it('applies migrations and supports profiles', () => {
    queries.insertProfile(db, {
      profile_id: 'profile_01',
      yaml_blob: 'name: Hari',
      parsed_json: '{"name":"Hari"}',
      version: 1,
      schema_version: 1,
      created_at: '2026-04-12T12:00:00Z',
      updated_at: '2026-04-12T12:00:00Z',
    });

    const profile = queries.getProfile(db, 'profile_01');
    expect(profile).toBeDefined();
    expect(profile?.yaml_blob).toBe('name: Hari');
  });

  it('supports runs and trace events', () => {
    queries.insertRun(db, {
      run_id: 'run_01',
      agent_name: 'test-agent',
      mode: 'normal',
      started_at: '2026-04-12T12:00:00Z',
      status: 'running',
    });

    const run = queries.getRun(db, 'run_01');
    expect(run?.agent_name).toBe('test-agent');

    queries.insertTraceEvent(db, {
      event_id: 'event_01',
      run_id: 'run_01',
      step_index: 0,
      timestamp: '2026-04-12T12:00:01Z',
      type: 'tool_call',
      actor: 'agent',
    });

    const events = queries.getTraceEventsForRun(db, 'run_01');
    expect(events.length).toBe(1);
    expect(events[0]!.type).toBe('tool_call');
  });

  it('enforces foreign keys (approvals to runs)', () => {
    expect(() => {
      queries.insertApproval(db, {
        approval_id: 'app_01',
        run_id: 'missing_run',
        scope: 'test',
        title: 'Title',
        description: 'Desc',
        options_json: '[]',
        status: 'pending',
        requested_at: '2026-04-12T12:00:00Z',
        timeout_at: '2026-04-12T12:05:00Z',
      });
    }).toThrow(/FOREIGN KEY constraint failed/);
  });
});
