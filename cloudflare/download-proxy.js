/**
 * 声纹工坊 · 下载加速代理
 *
 * 作用：把 mctuesday.top/dl/<文件名> 映射到 GitHub Release 的附件，
 *      借助 Cloudflare 的边缘缓存，让国内访问比直连 GitHub 快。
 *
 * 部署：Cloudflare 控制台 → Workers & Pages → 新建 Worker → 粘贴本文件 → 绑定路由 dl 子域
 *
 * 说明：
 *  - 缓存只对 <512 MB 的文件生效（Cloudflare 免费版单文件缓存上限）。
 *    安装包 214 MB 能缓存，运行时大分卷会走透传（但仍可断点续传）。
 *  - Range 请求原样透传，所以启动器的断点续传功能正常。
 */

const UPSTREAM = "https://github.com/dio080128/voiceclone-studio/releases/download/v1.0.0";

// 只放行这些文件，避免被当成开放代理刷流量
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
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // 支持 /dl/xxx.zip 和 /xxx.zip 两种写法
    let name = decodeURIComponent(url.pathname);
    name = name.replace(/^\/dl\//, "/").replace(/^\//, "");

    if (!ALLOW.has(name)) {
      return new Response("Not Found", { status: 404, headers: { "content-type": "text/plain; charset=utf-8" } });
    }

    const cache = caches.default;
    const cacheKey = new Request(url.toString(), { method: "GET" });

    // 命中缓存直接回
    let cached = await cache.match(cacheKey);
    if (cached) {
      const h = new Headers(cached.headers);
      h.set("x-cache", "HIT");
      return new Response(cached.body, { status: cached.status, headers: h });
    }

    const target = `${UPSTREAM}/${encodeURIComponent(name)}`;

    let upstream;
    try {
      upstream = await fetch(target, {
        method: request.method,
        headers: {
          "User-Agent": "VoiceCloneStudio-Downloader/1.0",
          // 透传断点续传的 Range
          ...(request.headers.get("range") ? { Range: request.headers.get("range") } : {}),
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
    for (const k of ["content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"]) {
      const v = upstream.headers.get(k);
      if (v) headers.set(k, v);
    }
    headers.set("x-cache", "MISS");

    const isFull = !request.headers.get("range") && upstream.status === 200;
    if (isFull) {
      headers.set("cache-control", "public, max-age=604800, immutable");
    }

    const resp = new Response(upstream.body, { status: upstream.status, headers });

    // 完整的 200 响应才写缓存（分片响应缓存了没意义）
    if (isFull) {
      const size = Number(upstream.headers.get("content-length") || 0);
      // 超过 450 MB 不尝试缓存，避免浪费
      if (size > 0 && size < 450 * 1024 * 1024) {
        ctx.waitUntil(cache.put(cacheKey, resp.clone()));
      }
    }

    return resp;
  },
};
