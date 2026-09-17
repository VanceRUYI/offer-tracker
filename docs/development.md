# 开发说明

## 目录结构

```text
.
├── server.py                 # 本机 HTTP 接口、静态资源入口与导出
├── store.py                  # 数据校验、SQLite 事务、历史记录和备份
├── recognition.py            # 公开页面读取与字段识别
├── browser_reader.py         # 可选隔离浏览器读取
├── rendered_extraction.py    # 动态正文和岗位 JSON 提取
├── job_sources.py            # 自动学习公开 GET 岗位入口
├── glm_recognition.py        # 可选 GLM 字段整理
├── company_logos.py          # 公司图标读取、校验与缓存
├── requirements-browser.txt # 可选浏览器依赖
├── test_server.py            # HTTP、资源加载、来源限制与导出测试
├── test_company_groups.py    # 公司归组、重投、旧库迁移测试
├── test_store.py             # 存储、更新、备份和兼容性测试
├── test_recognition.py       # 字段识别与网络访问限制测试
├── 启动秋招手帖.command       # macOS 启动入口
├── web/
│   ├── index.html            # 页面骨架
│   ├── app.js                # 页面、表单和交互流程
│   ├── model.mjs             # 日期计算、日历、筛选和待办分组
│   ├── model.test.mjs         # 前端逻辑测试
│   ├── logos.mjs             # 公司图标请求与自动补齐
│   ├── recognition-stream.mjs # 识别进度及结果读取
│   ├── dates.mjs             # 日期、时间和年份选择浮层
│   ├── selects.mjs           # 自定义单选菜单
│   ├── styles.css            # 视觉样式与响应式布局
│   └── favicon.svg
├── docs/
│   ├── development.md
│   └── archive/              # 历史方案
└── data/                     # 运行后生成，已忽略
    ├── workbench.sqlite3
    └── backups/
```

基础功能不需要安装 Python 包或构建前端。增强网址识别使用可选的 `requirements-browser.txt`，安装步骤见 README。服务按白名单提供静态资源，新增前端模块时也要更新 `server.py` 中的 `ASSETS`。

`browser_reader.py` 负责隔离浏览器子进程与动态页面读取；`rendered_extraction.py` 从渲染后的 DOM 和实际返回的 JSON 中提取候选字段。没有公司专用 API 路径。`job_sources.py` 从已成功读取的同源 GET 响应学习含数字岗位 ID 的入口，最多 32 条、内存有效期 6 小时；后续同路径岗位直接读取并重新核对岗位 ID，失败退回网页读取。明确的直接读取结果跳过模型。可选 `glm_recognition.py` 在读取后调用免费 GLM 整理候选字段。

## 本地运行与测试

```sh
python3 server.py --open
python3 server.py --port 8766 --db /tmp/offer-tracker-test/records.sqlite3
```

`--port` 指定端口，`--db` 指定数据库文件，`--open` 自动打开浏览器。开发交互测试建议使用独立数据库。修改 Python 服务后需要重启；修改现有前端文件后刷新即可。

```sh
python3 -m unittest test_company_groups test_store test_server test_recognition -v
node --test web/model.test.mjs
node --input-type=module --check < web/app.js
node --check web/dates.mjs
node --check web/selects.mjs
git diff --check
```

新增投递的回归检查：保存后关闭表单并进入投递列表，清除可能遮住新记录的搜索和筛选，新记录短暂突出显示；主动点击公司名称后才打开详情。

日期控件的回归检查：修改年月后点击左右箭头、跨年翻月、年份面板翻页、选择日期与时分、清空选填时间、Esc 关闭。鼠标点击引发的焦点变化或自动滚动不应误关浮层，键盘 Tab 离开与外部点击仍可关闭。

公司分组的回归检查：普通新增自动归组，公司内新增预填名称，简称建议不自动合并；同岗位提示重复、确认后新增；不同批次分别改状态、安排日程；搜索批次、按阶段筛选、平铺切换、公司默认收起（包括单岗位），点击公司行展开或收起；新增不会自动展开公司。

## 数据兼容

数据库默认路径相对于项目目录，不受终端当前目录影响。新字段使用空值兼容旧记录，编辑时未提交的字段保留原值。`industry` 仍保留在存储、备份和接口中以兼容旧数据，日常界面不再展示。

个性化设置存入独立的 `preferences` 表，通过 `/api/personalization` 读取和更新。文字限制长度，图标使用服务端白名单；前端展示时转义文字。JSON 备份增加可选的 `personalization` 字段，导入前校验，在同一事务中恢复，且不覆盖本机已有设置。

SQLite `user_version=2` 移除了旧版 `UNIQUE(company, role)` 约束。启动时检测旧表，在创建 `before-company-groups` 快照后，以事务重建表并保留 ID、行顺序和事件关联。迁移连接临时关闭外键，提交前运行 `foreign_key_check`；其他连接始终开启外键。

投递增加选填 `batch`（最长 80 字），旧记录读取为空字符串。公司按 `strip().lower()` 精确归组，保存时统一为首次记录的名称。创建同公司同岗位记录返回 HTTP 409 和 `duplicates`；请求明确传入布尔值 `allow_repeat=true` 才会独立创建。状态更新按 ID 执行，不影响其他投递。

JSON version 2 按 ID 去重，version 1 保留旧公司/岗位去重规则；导入仍在单个事务完成，时间线编号冲突会回滚。CSV 新增“批次”列。WebMCP 创建接口支持 `batch` 和 `allow_repeat`，搜索结果包含 `batch`。

备份、导入语义及完整恢复步骤见[README](../README.md#数据存在哪里)。不要把实际数据库、导出文件或招聘通知加入测试样本，使用虚构内容和临时数据库。

## 网络与隐私

- 服务只绑定 `127.0.0.1`，校验 Host、Origin 和修改请求标识。默认仅用于本机，不是面向公网的部署方案。
- 网址识别会访问用户提供的公开 HTTP/HTTPS 页面，不携带浏览器登录状态；限制重定向、响应大小和超时，并拒绝私有网络目标。
- 当前电脑配置代理且使用 Fake DNS 时，优先通过阿里公共 DNS 的 DoH JSON API 解析域名，网络不可用时回退 Google Public DNS，再经已有代理连接验证过的公网 IP。避免国内招聘页面被固定解析到较远的 CDN 节点；系统 DNS 已返回公网地址时沿用原路径。该 DNS 请求只包含域名，不包含岗位路径、粘贴通知或本地投递记录，返回内网地址仍直接拒绝。
- 粘贴文字的识别在本机完成，不需要 AI API Key，也不会上传到第三方模型服务。
- 浏览器读取使用全新临时上下文，不导入日常浏览器的账号或 Cookie；仅保留网站在本次临时会话中新发放的访客 Cookie，以支持需要会话校验的公开岗位接口，关闭上下文后清除。页面资源通过已校验公网 IP 的连接读取，重定向和子资源均受相同限制；禁用 Service Worker、WebSocket、下载及样式表/图片/媒体加载；复用初次取得的 HTML，在岗位数据就绪后提前结束。只允许页面加载所需 GET、HEAD、OPTIONS、POST 请求，不点击投递、登录等按钮。
- 每次浏览器读取最多 140 次资源请求，单资源解压后最多 8 MB，总量预算 32 MB，POST 请求体最多 128 KB。并发网络请求上限 6，读取窗口 45 秒，子进程硬超时 60 秒；仅允许同时读取一个页面。支持 gzip/deflate，压缩传输和解压后的内容均受大小限制。基础 HTML 读取另有独立超时。已学习入口读取限时 3 秒；图标推迟到保存后读取，限时 5 秒。空白页面的关键脚本明确失败后提前返回，不再等待整个读取窗口。页面所需辅助服务不可用时，仍可能无法加载岗位。
- 识别只返回字段及依据，不存储网页正文或账号数据。图标候选只在用户填入识别结果、保存相同公司及网址的投递后才写入本地缓存；保留用户手动图标选择。
- 页面不加载外部字体、追踪脚本或 CDN 组件。支持 WebMCP 的浏览器可调用页面提供的投递工具，使用相同的数据接口。

### 可选模型调用

`glm_recognition.py` 从环境变量或 `.env.local` 读取密钥，固定请求智谱 HTTPS 端点和 `glm-4.7-flash`，拒绝重定向，关闭深度思考，限制单并发、响应大小和连接等待，不重试、不切换收费模型。输入只包含截取的公开正文、标题及五类岗位字段线索；不传完整 HTML、网络响应或数据库记录。输出限制字段类型、长度并检查文字来源，未知和个人进度字段不填。

`POST /api/recognize-stream` 沿用同源及 `X-Workbench` 校验，通过 NDJSON 输出真实读取/模型阶段和最终结果。模型不可用时 `ai_status=fallback`，保留规则结果；未配置密钥仍可运行。前端仅展示字段候选及必要的现有值对照，不展示来源、耗时和模型诊断，诊断字段仍由接口返回。密钥不写入响应、日志、数据库或备份。

首次浏览器读取也会捕获通用 `name` 岗位字段及 `workLocations` 城市数组，经岗位 ID 或当前页面标题匹配后提取。网页标题、正文或接口已给出公司和岗位时，立即返回数据（`ai_status=not_needed`），不为城市、编号或批次等选填字段继续等待模型。仍缺少核心字段时保留模型整理流程，模型网络等待超时为 3 秒，不重试。
