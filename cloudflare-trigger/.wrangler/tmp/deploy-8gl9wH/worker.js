var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// worker.js
async function trigger(env) {
  const url = `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/update.yml/dispatches`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GH_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "ads-live-dashboard-timer"
    },
    body: JSON.stringify({ ref: "main" })
  });
  if (r.status !== 204) throw new Error(`GitHub said ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return r.status;
}
__name(trigger, "trigger");
var worker_default = {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(trigger(env));
  },
  // Visiting the worker address shows a health line only. It never starts a run.
  async fetch() {
    return new Response("ads-live-dashboard timer: runs at minute 7 of every hour.\n");
  }
};
export {
  worker_default as default
};
//# sourceMappingURL=worker.js.map
