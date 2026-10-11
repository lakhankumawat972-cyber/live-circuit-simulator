import cors from 'cors';
import express from 'express';
import { StoreUnavailableError } from './store.js';
import { ValidationError, validateGraphDocument, validateSimulateBody } from './validate.js';

/**
 * @param {object} deps
 * @param {object} deps.store       graph persistence (see store.js)
 * @param {object} deps.simulation  simulation client (see simulation.js)
 */
export function createApp({ store, simulation }) {
  const app = express();
  app.use(cors());
  app.use(express.json({ limit: '1mb' }));

  const route = (handler) => async (req, res, next) => {
    try {
      await handler(req, res);
    } catch (err) {
      next(err);
    }
  };

  app.get('/api/health', (_req, res) => res.json({ ok: true, service: 'api', database: store.isReady() }));

  // Live sync endpoint: validate, forward, and give up on the upstream call as
  // soon as the browser abandons the request (a newer edit replaced it).
  app.post('/api/simulate', route(async (req, res) => {
    const payload = validateSimulateBody(req.body);
    const abort = new AbortController();
    res.on('close', () => {
      if (!res.writableEnded) abort.abort();
    });
    const outcome = await simulation.simulate(payload, { signal: abort.signal });
    if (outcome.aborted) return;
    res.status(outcome.status).json(outcome.body);
  }));

  app.get('/api/graphs', route(async (_req, res) => res.json(await store.list())));

  app.post('/api/graphs', route(async (req, res) => {
    res.status(201).json(await store.create(validateGraphDocument(req.body)));
  }));

  app.get('/api/graphs/:id', route(async (req, res) => {
    const doc = await store.get(req.params.id);
    if (!doc) return res.status(404).json({ error: 'Graph not found' });
    res.json(doc);
  }));

  app.put('/api/graphs/:id', route(async (req, res) => {
    const doc = await store.update(req.params.id, validateGraphDocument(req.body));
    if (!doc) return res.status(404).json({ error: 'Graph not found' });
    res.json(doc);
  }));

  app.delete('/api/graphs/:id', route(async (req, res) => {
    if (!(await store.remove(req.params.id))) return res.status(404).json({ error: 'Graph not found' });
    res.status(204).end();
  }));

  app.use((_req, res) => res.status(404).json({ error: 'Not found' }));

  // eslint-disable-next-line no-unused-vars
  app.use((err, _req, res, _next) => {
    if (err instanceof ValidationError) return res.status(400).json({ error: err.message });
    if (err instanceof StoreUnavailableError) return res.status(503).json({ error: err.message });
    if (err.type === 'entity.too.large') return res.status(413).json({ error: 'Graph is too large' });
    if (err.type === 'entity.parse.failed') return res.status(400).json({ error: 'Body is not valid JSON' });
    console.error(err);
    res.status(500).json({ error: 'Internal error' });
  });

  return app;
}
