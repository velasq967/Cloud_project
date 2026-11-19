// Fase 5: carga solo sobre WH-002 (a traves del nginx) para comparar 1 vs 3 replicas
// RATE = req/s (default 200), DURATION (default 60s)

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const URL = __ENV.WH2 || 'http://localhost:8002';
const RATE = parseInt(__ENV.RATE || '200');
const DURATION = __ENV.DURATION || '60s';

const porInstancia = new Counter('requests_por_instancia');

export const options = {
  scenarios: {
    wh002: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: 50,
      maxVUs: 400,
    },
  },
  // estos thresholds no fallan nunca, solo hacen que el resumen muestre el conteo por replica
  thresholds: {
    'requests_por_instancia{instancia:wh002-api-1}': ['count>=0'],
    'requests_por_instancia{instancia:wh002-api-2}': ['count>=0'],
    'requests_por_instancia{instancia:wh002-api-3}': ['count>=0'],
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  const res = http.get(`${URL}/inventory/1`);
  check(res, { 'status 200': (r) => r.status === 200 });
  const inst = res.headers['X-Instance-Id'];
  if (inst) porInstancia.add(1, { instancia: inst });
}
