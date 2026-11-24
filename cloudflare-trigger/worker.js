// Hourly timer for the ads dashboards.
// Cloudflare runs this on the schedule in wrangler.toml. It only asks GitHub to start
// the "Update dashboards" workflow. It reads no ad data and holds no ad account keys.
// Secret GH_TOKEN: a GitHub fine-grained token with Actions read and write on this one repo only.

async function trigger(env) {
  const url = `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/update.yml/dispatches`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GH_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "ads-live-dashboard-timer",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  if (r.status !== 204) throw new Error(`GitHub said ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return r.status;
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(trigger(env));
  },
  // Visiting the worker address shows a health line only. It never starts a run.
  async fetch() {
    return new Response("ads-live-dashboard timer: runs at minute 7 of every hour.\n");
  },
};
