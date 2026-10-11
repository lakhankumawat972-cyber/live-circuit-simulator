// MongoDB persistence. The server starts (and /api/simulate works) even while
// MongoDB is down; graph routes answer 503 until it is reachable, and the
// connection is retried in the background.

import mongoose from 'mongoose';

export class StoreUnavailableError extends Error {}

export function createMongoStore(uri, { retryMs = 2000 } = {}) {
  mongoose.set('bufferCommands', false);
  const Graph = mongoose.model(
    'Graph',
    new mongoose.Schema(
      {
        name: { type: String, required: true },
        graph: { type: mongoose.Schema.Types.Mixed, required: true },
      },
      { timestamps: true, minimize: false },
    ),
  );

  const ready = () => mongoose.connection.readyState === 1;
  const guard = () => {
    if (!ready()) throw new StoreUnavailableError('Database is not connected');
  };
  const view = (doc) => ({ id: String(doc._id), name: doc.name, graph: doc.graph, createdAt: doc.createdAt, updatedAt: doc.updatedAt });

  let stopped = false;
  async function connectWithRetry() {
    while (!stopped) {
      try {
        await mongoose.connect(uri, { serverSelectionTimeoutMS: 3000 });
        console.log('MongoDB connected');
        return;
      } catch (err) {
        console.error(`MongoDB not reachable (${err.message}); retrying in ${retryMs}ms`);
        await new Promise((resolve) => setTimeout(resolve, retryMs));
      }
    }
  }

  return {
    start: () => {
      connectWithRetry();
    },
    stop: async () => {
      stopped = true;
      await mongoose.disconnect();
    },
    isReady: ready,
    async create({ name, graph }) {
      guard();
      return view(await Graph.create({ name, graph }));
    },
    async update(id, { name, graph }) {
      guard();
      if (!mongoose.isValidObjectId(id)) return null;
      const doc = await Graph.findByIdAndUpdate(id, { name, graph }, { new: true });
      return doc && view(doc);
    },
    async get(id) {
      guard();
      if (!mongoose.isValidObjectId(id)) return null;
      const doc = await Graph.findById(id);
      return doc && view(doc);
    },
    async list() {
      guard();
      const docs = await Graph.find({}, { name: 1, updatedAt: 1 }).sort({ updatedAt: -1 }).limit(100);
      return docs.map((d) => ({ id: String(d._id), name: d.name, updatedAt: d.updatedAt }));
    },
    async remove(id) {
      guard();
      if (!mongoose.isValidObjectId(id)) return false;
      return Boolean(await Graph.findByIdAndDelete(id));
    },
  };
}
