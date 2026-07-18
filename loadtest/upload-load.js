// k6 压测脚本：上传→异步处理链路（P2 MQ 量化验证）
//
// 压测入口选 POST /api/media/upload/file（单文件上传）：一次请求即触发
// 「存盘 → createTask → publish → 异步处理」完整链路，且无 Redis 分片会话与
// MD5 去重/单飞的干扰变量（不带 MD5 → contentMd5=null → standalone 处理路径），
// A/B 对比只剩一个变量：app.mq.enabled。
//
// 两轮跑法（详见 docs/LOADTEST.md）：
//   轮 1（MQ 关）: APP_TRANSCRIPT_MOCK_DELAY_MS=5000 mvn spring-boot:run
//   轮 2（MQ 开）: APP_TRANSCRIPT_MOCK_DELAY_MS=5000 APP_MQ_ENABLED=true mvn spring-boot:run
//   每轮: k6 run loadtest/upload-load.js
//
// 可调参数（环境变量）：
//   BASE_URL   目标地址，默认 http://localhost:8081
//   VUS        峰值并发虚拟用户数，默认 10
//   RAMP       爬坡时长，默认 20s；HOLD 平台期时长，默认 2m
//   THINK      每次迭代后的思考时间（秒），默认 0.5
//   FILE_KB    上传文件大小（KB），默认 64（压测对象是提交/排队，不是磁盘 IO）
//   K6_USER/K6_PASS 压测账号，默认 k6-loadtest / k6-password-123

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.BASE_URL || 'http://localhost:8081';
const USERNAME = __ENV.K6_USER || 'k6-loadtest';
const PASSWORD = __ENV.K6_PASS || 'k6-password-123';
const VUS = parseInt(__ENV.VUS || '10');
const RAMP = __ENV.RAMP || '20s';
const HOLD = __ENV.HOLD || '2m';
const THINK = parseFloat(__ENV.THINK || '0.5');
const FILE_KB = parseInt(__ENV.FILE_KB || '64');

// 内容随意（Mock 处理不读内容），零填充即可；文件名必须过 MediaFileValidator 的视频扩展名白名单
const fileData = new Uint8Array(FILE_KB * 1024).buffer;

export const options = {
    scenarios: {
        upload: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: RAMP, target: VUS },
                { duration: HOLD, target: VUS },
                { duration: '15s', target: 0 },
            ],
        },
    },
    thresholds: {
        // 仅作参考展示，不因超阈值中断压测（对比数据本身就是产出）
        'http_req_duration{endpoint:upload}': [{ threshold: 'p(99)<60000', abortOnFail: false }],
    },
};

export function setup() {
    const jsonHeaders = { headers: { 'Content-Type': 'application/json' } };
    // 注册幂等处理：账号已存在会返回失败，忽略；随后登录必须成功
    http.post(`${BASE}/api/auth/register`,
        JSON.stringify({ username: USERNAME, password: PASSWORD }), jsonHeaders);
    const login = http.post(`${BASE}/api/auth/login`,
        JSON.stringify({ username: USERNAME, password: PASSWORD }), jsonHeaders);
    const token = login.json('data.token');
    if (!token) {
        throw new Error(`登录失败，无法开始压测: HTTP ${login.status} ${login.body}`);
    }
    return { token };
}

export default function (data) {
    const res = http.post(`${BASE}/api/media/upload/file`, {
        file: http.file(fileData, 'load-test.mp4', 'video/mp4'),
    }, {
        headers: { Authorization: `Bearer ${data.token}` },
        tags: { endpoint: 'upload' },
    });

    // MQ 关：线程池(队列50+max4)打满后 publish 抛 TaskRejectedException → 503，此 check 失败率即「被拒单率」
    // MQ 开：syncSend 毫秒级返回，预期全程 200
    check(res, {
        'upload accepted (200)': (r) => r.status === 200,
    });

    sleep(THINK);
}
