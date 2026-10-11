// Everything the browser says to the backend goes through the Node API.
export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:5000';
export const SIMULATE_URL = `${API_URL}/api/simulate`;

async function call(path, options) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, { headers: { 'content-type': 'application/json' }, ...options });
  } catch {
    throw new Error('Cannot reach the API');
  }
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error ?? `Request failed (${res.status})`);
  return body;
}

export const listGraphs = () => call('/api/graphs');
export const loadGraph = (id) => call(`/api/graphs/${id}`);
export const saveGraph = ({ id, name, graph }) =>
  id
    ? call(`/api/graphs/${id}`, { method: 'PUT', body: JSON.stringify({ name, graph }) })
    : call('/api/graphs', { method: 'POST', body: JSON.stringify({ name, graph }) });
