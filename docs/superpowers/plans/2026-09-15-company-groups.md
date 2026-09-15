# Company groups implementation plan

**Goal:** 默认按公司收纳投递，支持自动归组、公司内新增和同岗位重投。
**Architecture:** 每次投递仍拥有独立 ID、时间线及待办。以去首尾空格、小写后的公司名称分组，不自动合并简称。新增选填 batch；明确 allow_repeat=true 才允许同公司同岗位重投。SQLite v2 移除旧唯一约束，迁移前备份，保留全部 ID 和事件。
**Tech stack:** Python 3.9 标准库 / SQLite / 原生 JavaScript / CSS。
**Spec:** 本任务中用户已确认的“公司分组、独立投递、自动归组、两种新增入口”设计。

## Constraints
- 保留现有暖白、橄榄色和字体比例；无第三方依赖。
- 不操作真实投递数据；交互验证使用独立数据库。
- 默认公司视图，保留平铺；筛选后只展示匹配项并标注数量；新增记录展开所在组。
- 公司提示通过按钮选择已有名称，可键盘访问；完全相同名称自动归组，简称只建议。
- 同岗位多次投递在日历、待办、详情以批次或日期区分。
- JSON v2 按 ID 去重；v1 保留旧公司/岗位去重兼容；新旧格式均支持导入。

## Tasks
- [x] 存储：先写旧库迁移、重复保护、重投独立历史、v2 导入幂等测试并确认失败；移除唯一约束，增加 batch / duplicate conflict；通过测试。
- [x] 分组模型：先写名称归一、筛选分组、相近名称提示、重复投递区分测试并确认失败；实现 companyKey / groupCompanies / matchingCompanies / attemptLabel。
- [x] 界面：复用平铺行组件，实现可折叠公司视图、切换、新增自动展开；公司输入建议、批次、重复选择；同步日历、详情、统计和备份说明。
- [x] 验证：运行 Python unittest、Node tests、JS 语法和 diff 检查；独立数据库验证新增不同岗位、重投、独立进展、筛选和刷新；检查截图；更新 README 后本地提交。
