# Zotero Local API 速查（本机直连，Zotero 10+）

以下结论来自 Zotero 10.0.8 安装包源码 `server_localAPI.js` 与官方 Local API 文档。

## 连接与开关

- Base：Zotero 本地 API，本机回环默认端口 23119；用户库前缀：`/api/users/0`（`0` 代表当前登录用户，也可换成真实数字 userID）。
- API 版本：v3；每个响应带 `Zotero-API-Version` 与 `Zotero-Server-ID` 头。
- 开关：设置 → 高级 → 勾选「允许此计算机上的其他应用程序与 Zotero 通讯」。对应偏好 `extensions.zotero.httpServer.localAPI.enabled`，默认 **false**。
- 未开启时所有接口返回 **403** `Local API is not enabled`。
- 该端口只能本机访问，**不要**转发到局域网或公网。

## 写授权

1. 先从任意响应读 `Zotero-Server-ID`（GET `/api/` 即可）。
2. `POST /api/local/authorize`，头带 `Zotero-Server-ID`，JSON 体 `{"appName": "应用名"}`。
3. Zotero 弹窗：允许 / 始终允许 / 拒绝。批准返回 `{"key": "<32位>", "remember": bool}`。
   - `remember=false`：key 一次性，首次成功写入后作废，下次写需再授权。
   - `remember=true`：可长期复用；可在 设置 → 高级 → 清除写入授权 处撤销。
4. 写请求头：`Zotero-API-Key: <key>`、`Zotero-Server-ID: <id>`，可选 `Zotero-Write-Token`（5–32 字符，防重复提交）。

### 状态码

| 码 | 含义 | 处理 |
|---|---|---|
| 401 | 缺 key / key 无效或已失效 | 重新 `authorize` |
| 403 | 本地 API 未开启，或用户拒绝授权（`{"denied":true}`） | 开开关 / 请用户点允许 |
| 412 | Server-ID 不匹配 | 丢弃缓存，重新读 `/api/` |
| 428 | 写请求缺 `Zotero-Server-ID` | 补头 |
| 429 | 授权弹窗过于频繁 | 按 `Retry-After` 退避 |
| 501 | API 版本不匹配 | 带正确 `Zotero-API-Version` 头 |

## 条目 JSON 约定

- 批量写入：`POST /api/users/0/items`，体为数组；响应 `{successful:[{key,...}], failed:[{...}]}`。
- 父条目：
  ```json
  {"itemType":"document","title":"标题","collections":["<collectionKey>"],"tags":[{"tag":"paper-imported"}]}
  ```
- 存储型附件：
  ```json
  {"itemType":"attachment","linkMode":"imported_file","parentItem":"<parentKey>","contentType":"application/pdf","title":"文件名.pdf"}
  ```
- 子笔记：
  ```json
  {"itemType":"note","parentItem":"<parentKey>","note":"<HTML>","tags":[{"tag":"paper-card"}]}
  ```
- 分类：`POST /api/users/0/collections`，体 `[{"name":"reference"}]`。

## 文件三阶段上传（仅 `imported_file` / `imported_url`，单文件 <4 GB）

1. **申请**：`POST /api/users/0/items/<attKey>/file`，查询参数 `md5`（32 位十六进制）、`filename`、`filesize`（字节）、`mtime`（**毫秒**，秒级时间戳会被 400 拒绝）、`contentType`；头 `If-None-Match: *`。
   - 已存在同 MD5：返回 `{"exists":1}`，跳过。
   - 否则返回 `{"url":"/api/local/uploads/<uploadKey>","uploadKey":"...","contentType":"...","prefix":"","suffix":""}`。
2. **传字节**：`POST` 文件原始字节到 `url`（此步无需 API key 与 Server-ID）；成功 **201**；字节 MD5 必须与申请阶段一致。
3. **登记落盘**：再 `POST /api/users/0/items/<attKey>/file?upload=<uploadKey>`，带 `If-None-Match: *`；成功 **204**，文件移入附件存储目录。

## 读全文

- `GET /api/users/0/items/<attKey>/fulltext` → `{content: "...", ...}`（字段也可能是 `text`）。
- 新导入的 PDF 往往尚未被索引：接口会返回 **404**，或返回 200 但 `content` 为空字符串。**这不是"扫描件"的证据**，也不是可以留空的理由。
- 处理顺序（与 `SKILL.md` 的 A2 一致）：
  1. 等待 30–60 秒后重试同一接口一次；
  2. 仍 404/空 → 用 `nature-paper-card/scripts/prepare_paper.py` 对**同一个 PDF** 抽取 `source_bundle.json` 并渲染页面图，逐页核对正文与表格列结构；
  3. 只有当 PDF 本身无文本层时，才判定需要 OCR。
- 若希望 Zotero 自己建索引（便于站内全文搜索），在客户端打开该 PDF 一次即可；但这不影响 A2 兜底的结论，也不要求等索引完成再开工。

## 与 JS 路线的差异（重要）

- **Local API 调不到 `RecognizeDocument`**：不会自动联网补 DOI/作者/期刊。父条目默认用 PDF 文件名作标题；要补题录需走 zotero.org Web API，或导入后在 Zotero 手动「检索元数据」。
- 本地接口默认不分页，一次返回全量；不支持 Atom。
- 本地对象版本号仅对应当前实例，与 Web API 版本无关，不要跨实例比较。
