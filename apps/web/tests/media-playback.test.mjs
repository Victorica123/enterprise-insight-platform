import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";

const streamPath = "/api/media/video/task-id/stream?token=fixture%2Bsignature%2Fvalue";
const signedObject = "https://objects.test/bucket/video.mp4?X-Amz-Signature=fixture%2Bvalue&part=1";
const cases = [
  ["same-origin proxy", "/media", streamPath, `http://127.0.0.1:8080/media${streamPath}`],
  ["proxy with trailing slash", "/media/", streamPath, `http://127.0.0.1:8080/media${streamPath}`],
  ["direct backend", "http://127.0.0.1:8081", streamPath, `http://127.0.0.1:8081${streamPath}`],
  ["absolute prefixed backend", "https://app.test/services/media", streamPath, `https://app.test/services/media${streamPath}`],
  ["absolute signed object", "/media", signedObject, signedObject],
];

for (const [name, base, streamUrl, expected] of cases) {
  test(`playback resolves ${name} and preserves the signed query`, async () => {
    const built = await build({
      entryPoints: ["src/mediaApi.ts"], bundle: true, write: false, format: "esm",
      define: { "import.meta.env": JSON.stringify({ VITE_MEDIA_API_BASE_URL: base }) },
    });
    const api = await import(`data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString("base64")}`);
    globalThis.window = {
      location: { href: "http://127.0.0.1:8080/#/media" },
      localStorage: { getItem: () => null },
    };
    globalThis.fetch = async () => new Response(JSON.stringify({
      success: true, data: { streamUrl, expiresInSeconds: 60 },
    }));
    assert.deepEqual(await api.createPlayback("task-id"), { url: expected, expiresInSeconds: 60 });
  });
}
