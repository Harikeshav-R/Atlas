import { createRootRoute, createRoute, createRouter, RouterProvider, Link, Outlet } from '@tanstack/react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import React from 'react';
import type { IpcResult, Profile } from '@atlas/schemas';

interface AtlasApi {
  invoke: <T = unknown>(channel: string, ...args: unknown[]) => Promise<T>;
}

declare global {
  interface Window {
    atlas: AtlasApi;
  }
}

const rootRoute = createRootRoute({
  component: () => (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 flex h-screen overflow-hidden">
      <div className="w-64 border-r border-neutral-800 bg-neutral-900 flex flex-col">
        <div className="p-4 border-b border-neutral-800 font-bold text-xl tracking-tight">Atlas</div>
        <nav className="flex-1 p-4 space-y-2">
          <Link to="/" className="block p-2 rounded hover:bg-neutral-800 [&.active]:bg-neutral-800">Profile</Link>
          <Link to="/trace" className="block p-2 rounded hover:bg-neutral-800 [&.active]:bg-neutral-800">Trace Viewer</Link>
        </nav>
      </div>
      <div className="flex-1 overflow-auto bg-neutral-950 p-8">
        <Outlet />
      </div>
    </div>
  ),
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: function ProfileScreen() {
    const queryClient = useQueryClient();
    const { data, isLoading } = useQuery({
      queryKey: ['profile'],
      queryFn: async () => window.atlas.invoke<IpcResult<Profile>>('profile.get')
    });
    
    const [importing, setImporting] = React.useState(false);

    const handleImport = async () => {
      setImporting(true);
      try {
        await window.atlas.invoke('profile.import', '/dummy/path.pdf');
        await queryClient.invalidateQueries({ queryKey: ['profile'] });
      } catch (e: unknown) {
        console.error(e);
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

const routeTree = rootRoute.addChildren([indexRoute, traceRoute]);
const router = createRouter({ routeTree });

export function App() {
  return <RouterProvider router={router} />;
}
