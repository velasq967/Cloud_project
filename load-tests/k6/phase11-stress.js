import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';

export const options = {
  stages: [
    { duration: '20s', target: 100 },
    { duration: '20s', target: 500 },
    { duration: '20s', target: 1000 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.05'], // menos del 5% de errores
  },
};

export default function () {
  const corrId = `COR-LOAD-${__VU}-${__ITER}`;
  const res = http.get(`${BASE_URL}/inventory/1`, {
    headers: { 'X-Correlation-ID': corrId },
  });

  check(res, {
    'status is 200': (r) => r.status === 200,
  });

  sleep(0.1);
}