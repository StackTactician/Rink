/**
 * Rink keepalive: a Cloudflare Worker on a 5-minute cron.
 *
 * Chosen over GitHub Actions because a cron trigger here is not billed
 * per-run, is free at any frequency above a minute, and does not compete with
 * the private repo's 2,000/month Actions minutes.
 *
 * Every 5 minutes is well inside Render's ~15 minute idle spin-down, and
 * leaves two consecutive slots to absorb a missed tick.
 *
 * Deploy:  npx wrangler deploy        (from this directory)
 * Logs:    npx wrangler tail
 */

const TARGET = "https://rink.onrender.com/api/formats";

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(ping());
  },

  // hitting the worker URL by hand runs the same check
  async fetch(request, env, ctx) {
    const result = await ping();
    return new Response(JSON.stringify(result, null, 2), {
      status: result.ok ? 200 : 503,
      headers: { "content-type": "application/json" },
    });
  },
};

async function ping() {
  const started = Date.now();
  try {
    const res = await fetch(TARGET, {
      // Render free cold start is ~30-60s; timeout must clear that.
      signal: AbortSignal.timeout(120_000),
      headers: { "user-agent": "rink-keepalive/1.0" },
    });
    const result = {
      ok: res.ok,
      status: res.status,
      ms: Date.now() - started,
      at: new Date().toISOString(),
    };
    console.log(JSON.stringify(result));
    return result;
  } catch (err) {
    const result = {
      ok: false,
      error: String(err),
      ms: Date.now() - started,
      at: new Date().toISOString(),
    };
    console.error(JSON.stringify(result));
    return result;
  }
}
