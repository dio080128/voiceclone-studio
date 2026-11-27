/**
 * 声纹工坊 · 站点 + 下载代理（合一）
 *
 * 用法：贴进现有 Worker（restless-math-a985），替换默认代码后 Deploy。
 *
 * 行为：
 *   - 访问 dl.mctuesday.top/xxx.zip 或 任意域名/dl/xxx.zip  → 代理到 GitHub Release
 *   - 其他所有请求 → 交给静态资源（网站页面）
 */

const UPSTREAM = "https://github.com/dio080128/voiceclone-studio/releases/download/v1.0.0";

const ALLOW = new Set([
  "声纹工坊-v1.0.0-安装包.exe",
  "runtime-part1.zip",
  "runtime-part2.zip",
  "runtime-part3.zip",
  "runtime-part4.zip",
  "runtime-part5.zip",
  "models.zip",
]);

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    const isDlHost = url.hostname.startsWith("dl.");
    const isDlPath = url.pathname.startsWith("/dl/");

    if (isDlHost || isDlPath) {
      return handleDownload(request, url, isDlPath);
    }

    // 其余请求回到静态资源
    if (env && env.ASSETS) {
      return env.ASSETS.fetch(request);
    }
    return new Response(
      "静态资源未绑定。如果这是纯 Worker 项目，请忽略此提示。",
      { status: 404, headers: { "content-type": "text/plain; charset=utf-8" } },
    );
  },
};

async function handleDownload(request, url, stripDlPrefix) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  let name = decodeURIComponent(url.pathname);
  if (stripDlPrefix) name = name.replace(/^\/dl\//, "/");
  name = name.replace(/^\//, "");

  if (!ALLOW.has(name)) {
    return new Response("Not Found", {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }

  const cache = caches.default;
  const cacheKey = new Request(url.origin + "/" + encodeURI(name), { method: "GET" });

  let cached = await cache.match(cacheKey);
  if (cached) {
    const h = new Headers(cached.headers);
    h.set("x-cache", "HIT");
    return new Response(cached.body, { status: cached.status, headers: h });
  }

  const target = `${UPSTREAM}/${encodeURIComponent(name)}`;
  const range = request.headers.get("range");

  let upstream;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers: {
        "User-Agent": "VoiceCloneStudio-Downloader/1.0",
        ...(range ? { Range: range } : {}),
      },
      redirect: "follow",
    });
  } catch (e) {
    return new Response(`上游请求失败: ${e.message}`, { status: 502 });
  }

  if (!upstream.ok && upstream.status !== 206) {
    return new Response(`上游返回 ${upstream.status}`, { status: upstream.status });
  }

  const headers = new Headers();
  for (const k of ["content-type", "content-length", "content-range",
                   "accept-ranges", "etag", "last-modified"]) {
    const v = upstream.headers.get(k);
    if (v) headers.set(k, v);
  }
  headers.set("x-cache", "MISS");
  headers.set("access-control-allow-origin", "*");

  const isFull = !range && upstream.status === 200;
  if (isFull) headers.set("cache-control", "public, max-age=604800, immutable");

  const resp = new Response(upstream.body, { status: upstream.status, headers });

  // 完整响应且小于 450 MB 才写缓存（Cloudflare 单文件缓存上限 512 MB）
  if (isFull) {
    const size = Number(upstream.headers.get("content-length") || 0);
    if (size > 0 && size < 450 * 1024 * 1024) {
      ctx.waitUntil(cache.put(cacheKey, resp.clone()));
    }
  }

  return resp;
}
