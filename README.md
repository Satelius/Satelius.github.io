# SATELIUS 个人网页档案

`Satelius.github.io` 的零构建静态站点。首页是一份可搜索、可筛选的子网页索引；站内页面和外部链接的元数据统一维护在 `assets/pages-data.js`。

## 技术约束

- 纯 HTML、CSS、原生 JavaScript
- 无 npm、无框架、无构建步骤
- 使用相对路径，适合 GitHub Pages 和本地静态服务器
- 子网页正文不依赖 JavaScript
- `.nojekyll` 明确关闭 Jekyll 处理

## 目录结构

```text
personal_web/
├── .nojekyll
├── 404.html
├── README.md
├── index.html
├── robots.txt
├── sitemap.xml
├── assets/
│   ├── favicon.svg
│   ├── pages-data.js
│   ├── site.js
│   └── styles.css
└── pages/
    ├── field-notes/
    │   └── index.html
    ├── harness-contract/
    │   ├── index.html
    │   ├── script.js
    │   └── styles.css
    ├── project-progress/
    │   ├── index.html
    │   ├── script.js
    │   └── styles.css
    └── vla-privileged-loop/
        └── index.html
```

## 本地预览

在项目根目录运行：

```powershell
python -m http.server 8000
```

浏览器访问：

```text
http://localhost:8000/
```

不建议只双击 HTML 文件检查。静态服务器的 URL 和目录行为更接近 GitHub Pages，也能正确验证尾部斜杠、404 和相对路径。

## 新增站内子网页

### 1. 复制示例目录

在 PowerShell 中运行：

```powershell
Copy-Item -Recurse .\pages\field-notes .\pages\reading-list
```

目录名建议只使用小写英文、数字和连字符。发布后的目录名就是 URL 的一部分，应保持稳定。

### 2. 编辑页面内容

打开 `pages/reading-list/index.html`，至少修改以下内容：

- `<title>`
- `meta[name="description"]`
- canonical 和 Open Graph URL
- 页面标题、摘要、日期和正文
- 页面编号与分类文字

保留共享资源路径：

```html
<link rel="icon" href="../../assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="../../assets/styles.css">
```

### 3. 登记首页索引

编辑唯一的索引元数据文件 `assets/pages-data.js`，向 `window.SATELIUS_PAGES` 数组追加对象：

```js
{
  id: "reading-list",
  number: "003",
  label: "READING LOG 003",
  title: "近期阅读记录",
  href: "./pages/reading-list/",
  external: false,
  category: "笔记",
  year: "2026",
  date: "2026-08-14",
  summary: "关于近期阅读、摘录和延伸线索的持续记录。",
  tags: ["阅读", "摘录", "笔记"],
  accent: "#dfff00"
}
```

保存后刷新首页。条目数量、分类筛选和检索内容会自动更新。

## 新增外链

外链不需要创建 `pages/` 目录，只需要在 `assets/pages-data.js` 增加记录：

```js
{
  id: "example-external",
  number: "004",
  label: "EXTERNAL LOG 004",
  title: "外部页面标题",
  href: "https://example.com/",
  external: true,
  category: "外链",
  year: "NOW",
  date: "2026-08-14",
  summary: "说明用户将前往哪里，以及那里有什么内容。",
  tags: ["外链", "参考"],
  accent: "#2447ff"
}
```

`external: true` 会让首页显示外链标识，并在新标签页安全打开链接。

## 元数据字段

| 字段 | 用途 |
| --- | --- |
| `id` | 稳定、唯一的机器标识 |
| `number` | 首页显示的三位档案编号 |
| `label` | 英文档案眉题 |
| `title` | 页面标题 |
| `href` | 站内相对路径或完整外部 URL |
| `external` | `true` 为外链，`false` 为站内页面 |
| `category` | 自动生成筛选按钮的分类 |
| `year` | 条目左侧显示的年份或 `NOW` |
| `date` | ISO 日期，格式为 `YYYY-MM-DD` |
| `summary` | 首页条目摘要 |
| `tags` | 参与搜索并显示在条目底部的标签数组 |
| `accent` | 条目的纯色识别色，使用 CSS 颜色值 |

## 发布前检查

1. 启动本地静态服务器。
2. 检查首页、站内页面和外链。
3. 在窄屏下检查导航、长标题和代码块。
4. 禁用 JavaScript，确认首页核心入口和子网页正文仍可访问。
5. 新增站内页面时同步更新 `sitemap.xml`。
6. 确认 canonical URL 使用 `https://satelius.github.io/` 域名。

本仓库不需要安装依赖，也不包含自动发布脚本。GitHub Pages 可以直接托管根目录中的文件。
