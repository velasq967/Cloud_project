// Carga por bodega: WH-001 50 req/s, WH-002 800 req/s, WH-003 20 req/s
// SCALE baja todas las tasas igual (default 0.1 -> 5/80/2)
// docker run --rm -i --network host -v "$PWD/load-tests:/load-tests" grafana/k6 run /load-tests/k6/phase4-multi-warehouse.js

import http from 'k6/http';
import { check } from 'k6';

const SCALE = parseFloat(__ENV.SCALE || '0.1');
const DURATION = __ENV.DURATION || '60s';

const WAREHOUSES = {
  'WH-001': { url: __ENV.WH1 || 'http://localhost:8001', rate: 50 },
  'WH-002': { url: __ENV.WH2 || 'http://localhost:8002', rate: 800 },
  'WH-003': { url: __ENV.WH3 || 'http://localhost:8003', rate: 20 },
};

function scenario(wh, cfg) {
  const rate = Math.max(1, Math.round(cfg.rate * SCALE));
  return {
    executor: 'constant-arrival-rate',
    rate,
    timeUnit: '1s',
    duration: DURATION,
    preAllocatedVUs: Math.max(5, rate),
    maxVUs: Math.max(20, rate * 4),
    exec: 'hitWarehouse',
    env: { WH: wh },
    tags: { warehouse: wh },
  };
}

export const options = {
  scenarios: Object.fromEntries(
    Object.entries(WAREHOUSES).map(([wh, cfg]) => [wh.replace('-', '_'), scenario(wh, cfg)]),
  ),
  thresholds: {
    'http_req_duration{warehouse:WH-001}': ['p(95)<500'],
    'http_req_duration{warehouse:WH-002}': ['p(95)<500'],
    'http_req_duration{warehouse:WH-003}': ['p(95)<500'],
    'http_req_failed{warehouse:WH-001}': ['rate<0.01'],
    'http_req_failed{warehouse:WH-002}': ['rate<0.01'],
    'http_req_failed{warehouse:WH-003}': ['rate<0.01'],
  },
  summaryTrendStats: ['avg', 'p(50)', 'p(95)', 'p(99)', 'max'],
};

export function hitWarehouse() {
  const wh = __ENV.WH;
  const base = WAREHOUSES[wh].url;
  // 90% inventario, 10% productos
  const productId = 1 + Math.floor(Math.random() * 3);
  const url = Math.random() < 0.9 ? `${base}/inventory/${productId}` : `${base}/products`;
  const res = http.get(url, {
    headers: { 'X-Correlation-ID': `k6-${wh}-${__VU}-${__ITER}` },
    tags: { warehouse: wh },
  });
  check(res, { 'status 200': (r) => r.status === 200 }, { warehouse: wh });
}
