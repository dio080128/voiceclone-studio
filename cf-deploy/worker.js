/**
 * 声纹工坊 · 站点 + 下载代理（合一）
 *
 * 部署：cf-deploy 目录下双击「部署.bat」，或 npx wrangler deploy
 *
 * 行为：
 *   - dl.mctuesday.top/xxx 或 任意域名/dl/xxx  → 反向代理到 GitHub Release 资产
 *   - 其他所有请求 → 交给静态资源（网站页面）
 *
 * v1.0.1 起改为「按文件名映射上游」，安装包走新 tag，
 * 体积大的运行时分卷仍指向 v1.0.0，避免重复上传 3.8 GB。
 */

const REPO = "dio080128/voiceclone-studio";
const BASE = `https://github.com/${REPO}/releases/download`;
const MS = "https://modelscope.cn/models/dio0801/voiceclone-studio/resolve/master";

// 文件名 → [首选上游, 备用上游]
// 首选走魔搭（国内 CDN，实测约为 GitHub 的 3 倍），失败再回 GitHub Release。
const ASSETS = new Map([
  ["voiceclone-studio-v1.0.2-setup.exe", [
    `${MS}/voiceclone-studio-v1.0.2-setup.exe`,
    `${BASE}/v1.0.2/voiceclone-studio-v1.0.2-setup.exe`,
  ]],
  ["voiceclone-studio-v1.0.1-setup.exe", [
    `${MS}/voiceclone-studio-v1.0.1-setup.exe`,
    `${BASE}/v1.0.1/voiceclone-studio-v1.0.1-setup.exe`,
  ]],
  ["-v1.0.0-.exe", [`${BASE}/v1.0.0/-v1.0.0-.exe`]],
  ["声纹工坊-v1.0.0-安装包.exe", [`${BASE}/v1.0.0/-v1.0.0-.exe`]],
  ["runtime-part1.zip", [`${MS}/runtime-part1.zip`, `${BASE}/v1.0.0/runtime-part1.zip`]],
  ["runtime-part2.zip", [`${MS}/runtime-part2.zip`, `${BASE}/v1.0.0/runtime-part2.zip`]],
  ["runtime-part3.zip", [`${MS}/runtime-part3.zip`, `${BASE}/v1.0.0/runtime-part3.zip`]],
  ["runtime-part4.zip", [`${MS}/runtime-part4.zip`, `${BASE}/v1.0.0/runtime-part4.zip`]],
  ["runtime-part5.zip", [`${MS}/runtime-part5.zip`, `${BASE}/v1.0.0/runtime-part5.zip`]],
  ["models.zip", [`${MS}/models.zip`, `${BASE}/v1.0.0/models.zip`]],
]);

// 用户下载时看到的名字
const PRETTY = {
  "voiceclone-studio-v1.0.1-setup.exe": "声纹工坊-v1.0.1-安装包.exe",
  "-v1.0.0-.exe": "声纹工坊-v1.0.0-安装包.exe",
  "声纹工坊-v1.0.0-安装包.exe": "声纹工坊-v1.0.0-安装包.exe",
};

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    const isDlHost = url.hostname.startsWith("dl.");
    const isDlPath = url.pathname.startsWith("/dl/");

    if (isDlHost || isDlPath) {
      return handleDownload(request, url, isDlPath, ctx);
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

async function handleDownload(request, url, stripDlPrefix, ctx) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  let name = decodeURIComponent(url.pathname);
  if (stripDlPrefix) name = name.replace(/^\/dl\//, "/");
  name = name.replace(/^\//, "");

  const upstreams = ASSETS.get(name);
  if (!upstreams) {
    return new Response("Not Found", {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }

  const cache = caches.default;
  // 缓存键带版本前缀：_v1 里混进过 HEAD 的空响应，换前缀避免命中脏数据
  const cacheKey = new Request(url.origin + "/_v2/" + encodeURI(name), { method: "GET" });
  const isGET = request.method === "GET";

  const cached = await cache.match(cacheKey);
  if (cached) {
    const h = new Headers(cached.headers);
    h.set("x-cache", "HIT");
    return new Response(cached.body, { status: cached.status, headers: h });
  }

  const range = request.headers.get("range");

  let upstream = null;
  let lastError = "";
  for (const target of upstreams) {
    try {
      const r = await fetch(target, {
        method: request.method,
        headers: {
          "User-Agent": "VoiceCloneStudio-Downloader/1.2",
          ...(range ? { Range: range } : {}),
        },
        redirect: "follow",
      });
      if (r.ok || r.status === 206) {
        upstream = r;
        break;
      }
      lastError = `上游返回 ${r.status}`;
    } catch (e) {
      lastError = `上游请求失败: ${e.message}`;
    }
  }

  if (!upstream) {
    return new Response(lastError || "上游全部不可用", { status: 502 });
  }

  const headers = new Headers();
  for (const k of ["content-type", "content-length", "content-range",
                   "accept-ranges", "etag", "last-modified"]) {
    const v = upstream.headers.get(k);
    if (v) headers.set(k, v);
  }
  headers.set("x-cache", "MISS");
  headers.set("access-control-allow-origin", "*");
  const pretty = PRETTY[name] || name;
  headers.set(
    "content-disposition",
    `attachment; filename*=UTF-8''${encodeURIComponent(pretty)}`,
  );

  // 只有 GET 的完整响应才允许写缓存：HEAD 没有 body，缓存进去会污染真实下载
  const isFull = isGET && !range && upstream.status === 200;
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
