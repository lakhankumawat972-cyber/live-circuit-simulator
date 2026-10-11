import { createApp } from './app.js';
import { createSimulationClient } from './simulation.js';
import { createMongoStore } from './store.js';

const port = Number(process.env.PORT || 5000);
const store = createMongoStore(process.env.MONGO_URI || 'mongodb://localhost:27017/live_circuit');
const simulation = createSimulationClient({
  baseUrl: process.env.SIMULATION_URL || 'http://localhost:8000',
  timeoutMs: Number(process.env.SIMULATION_TIMEOUT_MS || 10_000),
});

// Listen first: the API (and live simulation) must not wait for MongoDB.
const server = createApp({ store, simulation }).listen(port, () => console.log(`API listening on ${port}`));
store.start();

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, async () => {
    server.close();
    await store.stop();
    process.exit(0);
  });
}
