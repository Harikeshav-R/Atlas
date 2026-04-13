import { createRootRoute, createRoute, createRouter, RouterProvider, Link, Outlet, useParams } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import React from 'react';
import type { IpcResult } from '@atlas/schemas';

interface AtlasApi {
  invoke: <T = unknown>(channel: string, ...args: unknown[]) => Promise<T>;
}

declare global {
  interface Window {
    atlas: AtlasApi;
  }
}

// --- Root Layout ---

const rootRoute = createRootRoute({
  component: () => (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 flex h-screen overflow-hidden">
      <div className="w-64 border-r border-neutral-800 bg-neutral-900 flex flex-col">
        <div className="p-4 border-b border-neutral-800 font-bold text-xl tracking-tight">Atlas</div>
        <nav className="flex-1 p-4 space-y-2">
          <Link to="/" className="block p-2 rounded hover:bg-neutral-800 [&.active]:bg-neutral-800">Profile</Link>
          <Link to="/listings" className="block p-2 rounded hover:bg-neutral-800 [&.active]:bg-neutral-800">Listings</Link>
          <Link to="/trace" className="block p-2 rounded hover:bg-neutral-800 [&.active]:bg-neutral-800">Trace Viewer</Link>
        </nav>
      </div>
      <div className="flex-1 overflow-auto bg-neutral-950 p-8">
        <Outlet />
      </div>
    </div>
  ),
});

// --- Profile Screen ---

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: function ProfileScreen() {
    const queryClient = useQueryClient();
    const { data, isLoading } = useQuery({
      queryKey: ['profile'],
      queryFn: async () => window.atlas.invoke<IpcResult<{ profile_id: string; yaml_blob: string; parsed_json: string }>>('profile.get')
    });

    const [importing, setImporting] = React.useState(false);

    const handleImport = async () => {
      setImporting(true);
      try {
        await window.atlas.invoke('profile.import', '/dummy/path.pdf');
        await queryClient.invalidateQueries({ queryKey: ['profile'] });
      } catch (e: unknown) {
        void e;
      } finally {
        setImporting(false);
      }
    };

    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex justify-between items-center">
          <h1 className="text-3xl font-bold">Profile</h1>
          <button
            onClick={handleImport}
            disabled={importing}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded"
          >
            {importing ? 'Importing...' : 'Import Profile (PDF)'}
          </button>
        </div>
        {isLoading ? <p>Loading...</p> : (
          <pre className="p-4 bg-neutral-900 rounded overflow-x-auto text-sm">
            {data?.ok && JSON.stringify(data.data, null, 2)}
          </pre>
        )}
      </div>
    );
  }
});

// --- Listings Screen ---

interface ListingRow {
  listing_id: string;
  canonical_url: string;
  company_name: string;
  role_title: string;
  location?: string;
  remote_model: string;
  status: string;
  first_seen_at: string;
}

const listingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/listings',
  component: function ListingsScreen() {
    const queryClient = useQueryClient();
    const [url, setUrl] = React.useState('');

    const { data: listingsResult, isLoading } = useQuery({
      queryKey: ['listings'],
      queryFn: () => window.atlas.invoke<IpcResult<ListingRow[]>>('listings.list'),
    });

    const createMutation = useMutation({
      mutationFn: (pasteUrl: string) =>
        window.atlas.invoke<IpcResult<ListingRow>>('listings.createFromUrl', pasteUrl),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['listings'] });
        setUrl('');
      },
    });

    const handleSubmit = (e: React.FormEvent) => {
      e.preventDefault();
      if (!url.trim()) return;
      createMutation.mutate(url.trim());
    };

    const listings = listingsResult?.ok ? listingsResult.data : [];

    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <h1 className="text-3xl font-bold">Listings</h1>

        <form onSubmit={handleSubmit} className="flex gap-3">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste a job URL..."
            className="flex-1 bg-neutral-900 border border-neutral-700 rounded px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 placeholder:text-neutral-500"
          />
          <button
            type="submit"
            disabled={createMutation.isPending || !url.trim()}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-5 py-2.5 rounded text-sm font-medium transition-colors"
          >
            {createMutation.isPending ? 'Adding...' : 'Add Listing'}
          </button>
        </form>

        {isLoading ? (
          <p className="text-neutral-500">Loading listings...</p>
        ) : listings.length === 0 ? (
          <div className="text-center py-16 text-neutral-500">
            <p className="text-lg">No listings yet</p>
            <p className="text-sm mt-1">Paste a job URL above to get started</p>
          </div>
        ) : (
          <div className="space-y-2">
            {listings.map((listing: ListingRow) => (
              <Link
                key={listing.listing_id}
                to="/listings/$listingId"
                params={{ listingId: listing.listing_id }}
                className="block p-4 bg-neutral-900 border border-neutral-800 rounded-lg hover:border-neutral-600 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-medium">{listing.role_title}</div>
                    <div className="text-sm text-neutral-400 mt-0.5">
                      {listing.company_name}
                      {listing.location && ` · ${listing.location}`}
                      {listing.remote_model !== 'unknown' && ` · ${listing.remote_model}`}
                    </div>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded ${
                    listing.status === 'active' ? 'bg-green-900/30 text-green-400' : 'bg-neutral-800 text-neutral-400'
                  }`}>
                    {listing.status}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    );
  },
});

// --- Listing Detail Screen ---

interface EvaluationRow {
  evaluation_id: string;
  listing_id: string;
  grade: string;
  score: number;
  six_blocks_json: string;
  summary_text: string;
  created_at: string;
}

interface ScorecardRow {
  scorecard_id: string;
  evaluation_id: string;
  dimensions_json: string;
  weighted_total: number;
}

interface ListingDetail {
  listing: ListingRow;
  evaluation?: EvaluationRow;
  scorecard?: ScorecardRow;
}

const GRADE_COLORS: Record<string, string> = {
  A: 'bg-green-600',
  B: 'bg-blue-600',
  C: 'bg-yellow-600',
  D: 'bg-orange-600',
  F: 'bg-red-600',
};

function GradeBadge({ grade }: { grade: string }) {
  return (
    <span className={`inline-flex items-center justify-center w-10 h-10 rounded-lg text-lg font-bold ${GRADE_COLORS[grade] ?? 'bg-neutral-700'}`}>
      {grade}
    </span>
  );
}

const listingDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/listings/$listingId',
  component: function ListingDetailScreen() {
    const { listingId } = useParams({ from: '/listings/$listingId' });
    const queryClient = useQueryClient();

    const { data, isLoading } = useQuery({
      queryKey: ['listing', listingId],
      queryFn: () => window.atlas.invoke<IpcResult<ListingDetail>>('listings.get', listingId),
    });

    const evaluateMutation = useMutation({
      mutationFn: () => window.atlas.invoke<IpcResult<EvaluationRow>>('listings.evaluate', listingId),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['listing', listingId] });
      },
    });

    if (isLoading) return <p className="text-neutral-500">Loading...</p>;

    const detail = data?.ok ? data.data : undefined;
    if (!detail) return <p className="text-red-400">Listing not found</p>;

    const { listing, evaluation } = detail;
    const sixBlocks = evaluation?.six_blocks_json ? JSON.parse(evaluation.six_blocks_json) : undefined;

    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-start justify-between">
          <div>
            <Link to="/listings" className="text-sm text-neutral-500 hover:text-neutral-300">&larr; All Listings</Link>
            <h1 className="text-3xl font-bold mt-2">{listing.role_title}</h1>
            <p className="text-neutral-400 mt-1">
              {listing.company_name}
              {listing.location && ` · ${listing.location}`}
            </p>
            <a href={listing.canonical_url} target="_blank" rel="noopener noreferrer"
               className="text-sm text-blue-400 hover:text-blue-300 mt-1 inline-block">
              {listing.canonical_url}
            </a>
          </div>
          <div className="flex items-center gap-3">
            {evaluation && <GradeBadge grade={evaluation.grade} />}
            <button
              onClick={() => evaluateMutation.mutate()}
              disabled={evaluateMutation.isPending}
              className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded text-sm font-medium"
            >
              {evaluateMutation.isPending ? 'Evaluating...' : evaluation ? 'Re-evaluate' : 'Evaluate'}
            </button>
          </div>
        </div>

        {evaluation && (
          <div className="space-y-6">
            <div className="p-4 bg-neutral-900 rounded-lg border border-neutral-800">
              <div className="flex items-center gap-3 mb-3">
                <GradeBadge grade={evaluation.grade} />
                <div>
                  <div className="font-medium">Score: {evaluation.score}/10</div>
                  <div className="text-sm text-neutral-400">{evaluation.summary_text}</div>
                </div>
              </div>
            </div>

            {sixBlocks && (
              <div className="grid gap-4">
                <SixBlockCard title="Block 1 — Role Summary" content={sixBlocks.roleSummary} />
                <SixBlockCard title="Block 2 — CV Match" content={sixBlocks.cvMatch} />
                <SixBlockCard title="Block 3 — Level Strategy" content={sixBlocks.levelStrategy} />
                <SixBlockCard title="Block 4 — Comp Research" content={sixBlocks.compResearch} />
                <SixBlockCard title="Block 5 — Personalization" content={sixBlocks.personalization} />
                <SixBlockCard title="Block 6 — Interview Prep" content={sixBlocks.interviewPrep} />
              </div>
            )}
          </div>
        )}

        {!evaluation && (
          <div className="text-center py-16 text-neutral-500">
            <p className="text-lg">No evaluation yet</p>
            <p className="text-sm mt-1">Click "Evaluate" to run the Evaluation Agent on this listing</p>
          </div>
        )}
      </div>
    );
  },
});

function SixBlockCard({ title, content }: { title: string; content: unknown }) {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-lg">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 flex items-center justify-between text-left hover:bg-neutral-800/50 transition-colors rounded-lg"
      >
        <h3 className="font-medium">{title}</h3>
        <span className="text-neutral-500 text-sm">{expanded ? '−' : '+'}</span>
      </button>
      {expanded && (
        <div className="px-4 pb-4">
          <pre className="text-sm text-neutral-300 overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(content, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

// --- Trace Screen ---

const traceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/trace',
  component: function TraceScreen() {
    const [result, setResult] = React.useState<unknown>(null);
    const [loading, setLoading] = React.useState(false);

    const runAgent = async () => {
      setLoading(true);
      try {
        const res = await window.atlas.invoke('runs.start', 'echo-profile');
        setResult(res);
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        setResult({ error: message });
      } finally {
        setLoading(false);
      }
    };

    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between border-b border-neutral-800 pb-4">
          <h1 className="text-3xl font-bold">Trace Viewer</h1>
          <button
            onClick={runAgent}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded font-medium transition-colors"
          >
            {loading ? 'Running...' : 'Run echo-profile agent'}
          </button>
        </div>

        {!!result && (
          <div className="p-6 bg-neutral-900 rounded-lg shadow-sm border border-neutral-800">
            <h3 className="text-lg font-medium mb-4">Run Result</h3>
            <pre className="text-sm overflow-x-auto text-neutral-300">
              {JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    );
  }
});

// --- Router ---

const routeTree = rootRoute.addChildren([indexRoute, listingsRoute, listingDetailRoute, traceRoute]);
const router = createRouter({ routeTree });

export function App() {
  return <RouterProvider router={router} />;
}
