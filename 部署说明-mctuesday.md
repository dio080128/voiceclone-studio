# mctuesday.top 部署说明

站点有 4 个页面，已按 Cloudflare Pages 的目录约定排好：

```
site/
├─ index.html          根路径 → 自动跳到 /home
├─ _redirects          路由规则（/ 跳 /home，/donut 跳 /donate）
├─ assets/
│  ├─ style.css        全站样式
│  └─ favicon.svg      浏览器标签图标
├─ home/index.html     → mctuesday.top/home     软件信息
├─ about/index.html    → mctuesday.top/about    B 站 UP 主介绍
├─ download/index.html → mctuesday.top/download 下载页
└─ donate/index.html   → mctuesday.top/donate   爱发电（/donut 也能进）
```

---

## 方法一：网页拖拽上传（推荐，最快）

全程在浏览器里点，不需要装任何东西。

### 1. 建项目

1. 打开 <https://dash.cloudflare.com/>
2. 左侧菜单点 **Workers & Pages**
3. 点 **Create**（创建）
4. 选 **Pages** 标签页
5. 点 **Upload assets**（上传资源）

### 2. 上传文件

1. 项目名填 `mctuesday`（或你喜欢的，会成为 xxx.pages.dev 的前缀）
2. 把 **site 文件夹里的全部内容**（不是 site 这个文件夹本身）拖进上传框
   - 正确：拖进去能看到 `index.html`、`_redirects`、`assets`、`home`、`about`…
   - 错误：拖进去只有一个 `site` 文件夹
3. 点 **Deploy site**

等十几秒，会给你一个 `https://mctuesday.pages.dev` 的地址。先打开验一下：

- `/` 应该自动跳到 `/home`
- 顶部导航「关于」「下载」「赞助」都能点
- `/donut` 也能进到赞助页

### 3. 绑定域名

1. 进入刚建好的项目 → **Custom domains**（自定义域）
2. 点 **Set up a custom domain**
3. 输入 `mctuesday.top` → 继续
4. 因为域名已经托管在 Cloudflare，它会自动加一条 CNAME 记录，点确认即可

再重复一次，填 `www.mctuesday.top`（可选，但建议加）。

> 生效一般 1~2 分钟。如果浏览器还显示旧内容，Ctrl+F5 强制刷新一下。

---

## 方法二：命令行部署（改起来方便）

已经装好 Node.js 的话，一条命令搞定：

```bash
# 第一次会打开浏览器让你登录 Cloudflare
npx wrangler pages deploy ./site --project-name mctuesday
```

以后每次改完页面，重跑这一条就更新了。

---

## 方法三：接 GitHub 自动部署（长期最省事）

1. 把 site 目录推到 GitHub 仓库
2. Cloudflare Pages → **Connect to Git** → 选仓库
3. 构建设置留空（纯静态，不需要构建命令）
4. 输出目录填 `site`

之后 push 代码就自动发布。

---

## 上线后需要改的地方

页面里的链接目前是占位，替换成你真实的地址：

| 文件 | 位置 | 现在写的 | 改成 |
|---|---|---|---|
| `about/index.html` | B 站主页链接 | `https://space.bilibili.com/` | 你的空间地址 |
| `about/index.html` | GitHub 链接 | `https://github.com/mctuesday` | 你的仓库 |
| `download/index.html` | 下载按钮 ×2 | `github.com/mctuesday/voiceclone-studio/...` | 实际仓库地址 |
| `donate/index.html` | 爱发电链接 | `https://afdian.com/a/mctuesday` | 你的爱发电主页 |

改完重新上传一次即可（方法一重复上传，或方法二重跑命令）。

### 爱发电二维码

把爱发电主页的二维码图片存成 `assets/afdian-qr.png`，赞助页会自动替换掉那个虚线占位框，不用改代码。

---

## 常见问题

**Q：访问根域名没跳到 /home？**
检查 `_redirects` 文件是否上传成功。这个文件名必须以 `_` 开头，且放在站点根目录（和 index.html 同级）。Cloudflare Pages 只认根目录的 `_redirects`。

**Q：页面样式丢了（变成白底黑字）？**
CSS 路径写的是绝对路径 `/assets/style.css`，必须部署在域名根目录。如果你部署在子路径（比如 `xxx.pages.dev/blog/`），需要把 HTML 里的 `/assets/` 改成 `assets/`。

**Q：改完文件重新上传，还是旧页面？**
浏览器缓存。Ctrl+F5 强刷，或在 Cloudflare 后台 **Caching → Purge Everything** 清一次。

**Q：想加新页面？**
新建一个目录，里面放 `index.html`，比如 `contact/index.html`，访问路径就是 `/contact`。然后在各页面顶部的 `<nav>` 里加一行链接。

---

## 本地预览（可选）

上传前想先看看效果，在 site 目录里起个本地服务：

```bash
cd site
python -m http.server 8000
```

浏览器打开 <http://localhost:8000>。

注意：本地这个简易服务器不认 `_redirects`，所以 `/` 会显示跳转中转页而不是直接进 /home，这是正常的。
