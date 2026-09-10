import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { authenticate } from './auth.js';

const BASE = __ENV.E2E_BASE_URL || 'http://127.0.0.1:18080';
const DURATION = __ENV.SOAK_DURATION || '10m';
const CHAT_VUS = parseInt(__ENV.CHAT_VUS || '24');
const UPLOAD_RATE = parseInt(__ENV.UPLOAD_RATE || '8');
const DRAIN_TIMEOUT_SECONDS = parseInt(__ENV.DRAIN_TIMEOUT_SECONDS || '900');

export const options = {
  scenarios: {
    upload_pressure: {
      executor: 'constant-arrival-rate',
      exec: 'uploadPressure',
      rate: UPLOAD_RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: Math.max(UPLOAD_RATE * 2, 20),
      maxVUs: Math.max(UPLOAD_RATE * 8, 100),
    },
    chat_pressure: {
      executor: 'constant-vus',
      exec: 'chatPressure',
      vus: CHAT_VUS,
      duration: DURATION,
    },
  },
  thresholds: {
    'http_req_failed{endpoint:upload}': ['rate<0.01'],
    'http_req_failed{endpoint:chat}': ['rate<0.01'],
    'http_req_duration{endpoint:upload}': ['p(95)<2000'],
    'http_req_duration{endpoint:chat}': ['p(95)<3000'],
    checks: ['rate>0.99'],
  },
};

function sampleVideo() {
  const bytes = new Uint8Array(16 * 1024);
  bytes.set([0, 0, 0, 24, 102, 116, 121, 112, 105, 115, 111, 109, 0, 0, 2, 0]);
  return bytes.buffer;
}

export function setup() {
  const { token } = authenticate();
  const auth = { Authorization: `Bearer ${token}` };
  const upload = http.post(`${BASE}/media/api/media/upload/file`, {
    file: http.file(sampleVideo(), 'soak-seed.mp4', 'video/mp4'),
  }, { headers: auth });
  const taskId = upload.json('data.taskId');
  let task;
  for (let attempt = 0; attempt < 120; attempt += 1) {
    task = http.get(`${BASE}/media/api/workflow/tasks/${taskId}`, { headers: auth }).json('data');
    if (task && task.status === 'COMPLETED') break;
    sleep(0.25);
  }
  if (!task || task.status !== 'COMPLETED') throw new Error(`seed workflow did not complete: ${JSON.stringify(task)}`);
  return { token, assetId: task.videoId };
}

export function uploadPressure(data) {
  const name = `load-${exec.vu.idInTest}-${exec.scenario.iterationInTest}.mp4`;
  const result = http.post(`${BASE}/media/api/media/upload/file`, {
    file: http.file(sampleVideo(), name, 'video/mp4'),
  }, {
    headers: { Authorization: `Bearer ${authenticate().token}` },
    tags: { endpoint: 'upload' },
  });
  check(result, { 'overload upload remains durably accepted': (r) => r.status === 200 && !!r.json('data.taskId') });
}

export function chatPressure(data) {
  const result = http.post(`${BASE}/agent/chat`, JSON.stringify({
    question: 'soak-seed.mp4 的证据内容是什么？',
    answer_mode: 'local',
    retriever_mode: 'keyword',
    workflow_mode: 'standard',
    asset_ids: [data.assetId],
  }), {
    headers: { Authorization: `Bearer ${authenticate().token}`, 'Content-Type': 'application/json' },
    tags: { endpoint: 'chat' },
  });
  check(result, { 'chat returns scoped evidence': (r) => r.status === 200 && Array.isArray(r.json('sources')) });
  sleep(0.1);
}

export function teardown(data) {
  let state = { active: -1, failed: -1, total: -1, status: 0 };
  const attempts = Math.max(1, Math.ceil(DRAIN_TIMEOUT_SECONDS / 2));
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const result = http.get(`${BASE}/media/api/workflow/tasks`, {
      headers: { Authorization: `Bearer ${authenticate().token}` },
      tags: { endpoint: 'drain' },
    });
    if (result.status === 200) {
      const tasks = result.json('data') || [];
      const active = tasks.filter((task) => ['QUEUED', 'TRANSCRIBING', 'SUMMARIZING'].includes(task.status)).length;
      const failed = tasks.filter((task) => task.status === 'FAILED').length;
      state = { active, failed, total: tasks.length, status: result.status };
      if (active === 0) break;
    } else {
      state.status = result.status;
    }
    sleep(2);
  }
  check(state, {
    'task inventory remains reachable': (value) => value.status === 200,
    'accepted workflow backlog drains': (value) => value.active === 0,
    'no accepted workflow finishes failed': (value) => value.failed === 0,
  });
}

export function handleSummary(data) {
  return {
    stdout: JSON.stringify(data.metrics, null, 2),
    'runtime/local-prod/results/platform-soak-summary.json': JSON.stringify(data, null, 2),
  };
}
