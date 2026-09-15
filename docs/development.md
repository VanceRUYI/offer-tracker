# 开发说明

## 目录结构

```text
.
├── server.py                 # 本机 HTTP 接口、静态资源入口与导出
├── store.py                  # 数据校验、SQLite 事务、历史记录和备份
├── recognition.py            # 公开页面读取与字段识别
├── test_server.py            # HTTP、资源加载、来源限制与导出测试
├── test_store.py             # 存储、更新、备份和兼容性测试
├── test_recognition.py       # 字段识别与网络访问限制测试
├── 启动秋招手帖.command       # macOS 启动入口
├── web/
│   ├── index.html            # 页面骨架
│   ├── app.js                # 页面、表单和交互流程
│   ├── model.mjs             # 日期计算、日历、筛选和待办分组
│   ├── model.test.mjs         # 前端逻辑测试
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

不需要安装 Python 包或构建前端。服务按白名单提供静态资源，新增前端模块时也要更新 `server.py` 中的 `ASSETS`。

## 本地运行与测试

```sh
python3 server.py --open
python3 server.py --port 8766 --db /tmp/offer-tracker-test/records.sqlite3
```

`--port` 指定端口，`--db` 指定数据库文件，`--open` 自动打开浏览器。开发交互测试建议使用独立数据库。修改 Python 服务后需要重启；修改现有前端文件后刷新即可。

```sh
python3 -m unittest test_store test_server test_recognition -v
node --test web/model.test.mjs
node --input-type=module --check < web/app.js
node --check web/dates.mjs
node --check web/selects.mjs
git diff --check
```

新增投递的回归检查：保存后关闭表单并进入投递列表，清除可能遮住新记录的搜索和筛选，新记录短暂突出显示；主动点击公司名称后才打开详情。

日期控件的回归检查：修改年月后点击左右箭头、跨年翻月、年份面板翻页、选择日期与时分、清空选填时间、Esc 关闭。鼠标点击引发的焦点变化或自动滚动不应误关浮层，键盘 Tab 离开与外部点击仍可关闭。

## 数据兼容

数据库默认路径相对于项目目录，不受终端当前目录影响。新字段使用空值兼容旧记录，编辑时未提交的字段保留原值。`industry` 仍保留在存储、备份和接口中以兼容旧数据，日常界面不再展示。

个性化设置存入独立的 `preferences` 表，通过 `/api/personalization` 读取和更新。文字限制长度，图标使用服务端白名单；前端展示时转义文字。JSON 备份增加可选的 `personalization` 字段，导入前校验，在同一事务中恢复，且不覆盖本机已有设置。

备份、导入语义及完整恢复步骤见[README](../README.md#数据存在哪里)。不要把实际数据库、导出文件或招聘通知加入测试样本，使用虚构内容和临时数据库。

## 网络与隐私

- 服务只绑定 `127.0.0.1`，校验 Host、Origin 和修改请求标识。默认仅用于本机，不是面向公网的部署方案。
- 网址识别会访问用户提供的公开 HTTP/HTTPS 页面，不携带浏览器登录状态；限制重定向、响应大小和超时，并拒绝私有网络目标。
- 当前电脑配置代理且使用 Fake DNS 时，会通过 Google Public DNS 的 DoH JSON API 解析域名，再经已有代理连接验证过的公网 IP。该 DNS 请求包含域名，不包含岗位路径、粘贴通知或本地投递记录。
- 粘贴文字的识别在本机完成，不需要 AI API Key，也不会上传到第三方模型服务。
- 页面不加载外部字体、追踪脚本或 CDN 组件。支持 WebMCP 的浏览器可调用页面提供的投递工具，使用相同的数据接口。
