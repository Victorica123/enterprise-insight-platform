import http from 'k6/http';
import crypto from 'k6/crypto';

let session;
let renewAt = 0;
const BASE = __ENV.E2E_BASE_URL || 'http://127.0.0.1:18080';
const ISSUER = __ENV.E2E_OIDC_ISSUER || 'http://127.0.0.1:18082/realms/enterprise-insight';
const CLIENT = 'enterprise-insight-web';

// Use the same Authorization Code + S256 PKCE flow as the UI. Each VU owns
// its session; no shared rotating refresh token or disabled local login API.
export function authenticate() {
  if (session && Date.now() < renewAt) return session;
  if (!__ENV.E2E_OIDC_USERNAME || !__ENV.E2E_OIDC_PASSWORD) {
    throw new Error('Set E2E_OIDC_USERNAME and E2E_OIDC_PASSWORD for a dedicated test user.');
  }
  const verifier = crypto.sha256(crypto.randomBytes(32), 'hex');
  const challenge = crypto.sha256(verifier, 'base64rawurl');
  const state = crypto.sha256(crypto.randomBytes(16), 'hex');
  const redirect = `${BASE}/`;
  const query = `client_id=${CLIENT}&redirect_uri=${encodeURIComponent(redirect)}&response_type=code&scope=openid&state=${state}&code_challenge=${challenge}&code_challenge_method=S256`;
  const params = { redirects: 0, responseCallback: http.expectedStatuses(200, 302), tags: { endpoint: 'oidc' } };
  let result = http.get(`${ISSUER}/protocol/openid-connect/auth?${query}`, params);
  if (result.status === 200) {
    const action = result.html().find('form#kc-form-login').attr('action');
    if (!action) throw new Error('OIDC login form unavailable');
    result = http.post(action, { username: __ENV.E2E_OIDC_USERNAME, password: __ENV.E2E_OIDC_PASSWORD }, params);
  }
  const location = result.headers.Location || '';
  const code = location.match(/[?&]code=([^&]+)/);
  const returnedState = location.match(/[?&]state=([^&]+)/);
  if (!code || !returnedState || decodeURIComponent(returnedState[1]) !== state) throw new Error('OIDC callback failed');
  const grant = http.post(`${ISSUER}/protocol/openid-connect/token`, {
    grant_type: 'authorization_code', client_id: CLIENT, redirect_uri: redirect,
    code: decodeURIComponent(code[1]), code_verifier: verifier,
  }, { tags: { endpoint: 'oidc' } });
  if (grant.status !== 200) throw new Error(`OIDC token exchange failed (${grant.status})`);
  const exchanged = http.post(`${BASE}/media/api/auth/oidc/exchange`, null, {
    headers: { Authorization: `Bearer ${grant.json('access_token')}` }, tags: { endpoint: 'oidc' },
  });
  if (exchanged.status !== 200 || !exchanged.json('data.token')) throw new Error(`Workspace exchange failed (${exchanged.status})`);
  session = exchanged.json('data');
  renewAt = Date.now() + 240000;
  return session;
}
