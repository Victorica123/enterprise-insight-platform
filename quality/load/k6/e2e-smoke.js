import http from 'k6/http';
import { check, sleep } from 'k6';
import { authenticate } from './auth.js';

const BASE = __ENV.E2E_BASE_URL || 'http://127.0.0.1:18080';

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: {
    checks: ['rate==1'],
    http_req_failed: ['rate==0'],
  },
};

function sampleVideo() {
  const bytes = new Uint8Array(16 * 1024);
  bytes.set([0, 0, 0, 24, 102, 116, 121, 112, 105, 115, 111, 109, 0, 0, 2, 0]);
  return bytes.buffer;
}

export default function () {
  const { token } = authenticate();
  check(token, { 'OIDC returns workspace JWT': (value) => !!value });
  const auth = { Authorization: `Bearer ${token}` };

  const upload = http.post(`${BASE}/media/api/media/upload/file`, {
    file: http.file(sampleVideo(), 'e2e-smoke.mp4', 'video/mp4'),
  }, { headers: auth });
  check(upload, { 'upload accepted durably': (r) => r.status === 200 && !!r.json('data.taskId') });
  const taskId = upload.json('data.taskId');
  let task;
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const result = http.get(`${BASE}/media/api/workflow/tasks/${taskId}`, { headers: auth });
    task = result.json('data');
    if (task && (task.status === 'COMPLETED' || task.status === 'FAILED')) break;
    sleep(0.25);
  }
  check(task, { 'workflow completes': (value) => value && value.status === 'COMPLETED' });

  let chat;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const result = http.post(`${BASE}/agent/chat`, JSON.stringify({
      question: 'e2e-smoke.mp4 的视频内容是什么？',
      answer_mode: 'local',
      retriever_mode: 'keyword',
      workflow_mode: 'standard',
      asset_ids: [task.videoId],
    }), { headers: { ...auth, 'Content-Type': 'application/json' } });
    chat = result.json();
    if (chat.sources && chat.sources.some((source) => source.source_type === 'video')) break;
    sleep(0.25);
  }
  check(chat, {
    'agent returns timestamped video evidence': (value) => value.sources.some((source) =>
      source.source_type === 'video' && source.asset_id === task.videoId && source.start_ms === 0),
  });
}
