// Fase 7: misma carga a la consulta en vivo (A) y al read model (B)
// RATE = req/s para cada una (default 50), DURATION (default 30s)

import http from 'k6/http';
import { check } from 'k6';

const CENTRAL = __ENV.CENTRAL || 'http://localhost:8010';
const RATE = parseInt(__ENV.RATE || '50');
const DURATION = __ENV.DURATION || '30s';
const SKU = __ENV.SKU || 'PROD-001';

function scenario(exec) {
  return {
    executor: 'constant-arrival-rate',
    exec,
    rate: RATE,
    timeUnit: '1s',
    duration: DURATION,
    preAllocatedVUs: 20,
    maxVUs: 200,
  };
}

export const options = {
  scenarios: {
    a_en_vivo: scenario('enVivo'),
    b_read_model: scenario('readModel'),
  },
  // los thresholds hacen que k6 muestre la latencia separada por alternativa
  thresholds: {
    'http_req_duration{alternativa:A}': ['p(95)>=0'],
    'http_req_duration{alternativa:B}': ['p(95)>=0'],
    'http_req_failed{alternativa:A}': ['rate>=0'],
    'http_req_failed{alternativa:B}': ['rate>=0'],
  },
};

export function enVivo() {
  const r = http.get(`${CENTRAL}/global/inventory-live/${SKU}`, { tags: { alternativa: 'A' } });
  check(r, { 'A status 200': (x) => x.status === 200 });
}

export function readModel() {
  const r = http.get(`${CENTRAL}/global/inventory/${SKU}`, { tags: { alternativa: 'B' } });
  check(r, { 'B status 200': (x) => x.status === 200 });
}
