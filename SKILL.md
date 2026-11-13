---
name: zotero-paper-notes
description: 把本地文件夹中的 PDF 批量导入 Zotero 的指定分类（默认 reference），逐篇严格按 `references/summary-prompt.md` 的提示词原文做结构化精读并生成 Paper Card，再把笔记作为子笔记写回对应文献条目之下。笔记公式按 Zotero 原生 math 节点（KaTeX）渲染、上下标转 sub/sup、配全局 note.css 排版，解决批量导入后公式与符号难看的问题。技能内自带完整的 nature-paper-card 技能文件（22 个）与 Paper Card 辅助脚本；开工前先启动 Zotero 客户端。支持 Zotero 10+ Local API 直连（Python 脚本）与 Run JavaScript 兜底两条路线。Zotero 全文接口返回 404/空时，用内置 `prepare_paper.py` 从同一 PDF 抽取逐页正文并渲染页面图逐页核对表格列结构，禁止据标题或摘要臆造。用于：批量导入文献到 Zotero、给一批 PDF 生成总结笔记并存回 Zotero、把总结挂到 Zotero 条目的子笔记、整理文献库、修笔记里显示成 `$…$` 原文的公式。不负责直接改 Zotero 数据库文件，也不代表云端进程能直连本机 Zotero 客户端。
---

# Zotero 文献批量总结笔记

## 核心事实（先读这一节）

1. **云端与本地是两台机器**。AI 助手运行在云端沙箱，**无法**直接读写用户本机 Zotero 客户端、本地磁盘或 `zotero.sqlite`。所有写库动作都由**本机脚本/代码**发起。
2. **两条本机桥**：
   - **路线 A · Local API 直连（主用，需 Zotero 10+）**：本机 Python 脚本走 `http://127.0.0.1:23119/api/`，不用粘贴 JS；首次写入在 Zotero 弹窗授权。
   - **路线 B · Run JavaScript（兜底，任意版本）**：在 `工具 → 开发者 → 运行 JavaScript` 粘贴两段 JS。
3. **不要改数据库文件**。禁止编辑或替换 `zotero.sqlite`；一切写入走官方 JavaScript API 或 Local API。
4. **全文有两条来源，Zotero 索引不是唯一来源**。刚导入的 PDF 常常还没被 Zotero 索引，`/items/<attKey>/fulltext` 会返回 **404 或空字符串**；此时**必须**走 A2 兜底：用技能内置的 `nature-paper-card/scripts/prepare_paper.py` 直接从**同一个 PDF** 抽取逐页正文，并把页面渲染成图逐页核对表格列结构。**任何情况下都不得据标题、摘要或"看起来对齐"的数字臆造内容。**
5. **公式必须落成 Zotero 原生 math 节点，否则只是难看的一串字符**。Zotero 6.0.14+ 的笔记编辑器用 KaTeX 渲染数学节点，序列化格式固定为 `<span class="math">$…$</span>`（行内）和 `<pre class="math">$$…$$</pre>`（行间）。API 写入的 HTML 不会自动解析 `$…$`，必须由转换脚本显式转成这两种节点。

## 公式、符号与排版（贯穿 B/C 阶段）

三件事一起做，缺一件笔记就还是难看：

| 环节 | 做什么 | 落在哪 |
| --- | --- | --- |
| B 阶段写法 | 行内 `$…$`、行间独立成段 `$$…$$`、上下标 `X_{sub}` / `X^{sup}`、星号 `$A^{*}$`；标题内禁止公式 | `references/summary-prompt.md` 的《附加执行规范》、`references/note-template.md` 的《公式与上下标规范》 |
| md → HTML | 用 `scripts/make_notes_json_v2.py`（旧 `make_notes_json.py` 不做公式转换）：`$…$`→math 节点、裸下标→`<sub>`、`x^y`→`<sup>`、`A*` 转义、`[Paper: …]` 变灰；`--notes` 模式可修存量 JSON | C 阶段之前 |
| 全局排版 | Zotero → Config Editor → `extensions.zotero.note.css` 粘贴 `assets/zotero-note.css`，重启客户端 | 一次性配置，全局生效 |

硬约束：**标题（h1–h6）里不能放公式节点**（Zotero schema 的 heading 内容模型不含 `math_inline`，写了会丢）；KaTeX 不支持 `\begin{equation}`、`\label`、`\cite`、`\bm`；公式放在 `<code>` 里不会被渲染。

## 开始前：先打开 Zotero（第 0 步）

任何 A/C 阶段动作之前，先确认 Zotero 客户端已运行；**没打开就先启动，再探测 Local API**。

```powershell
$exe = $env:ZOTERO_EXE
if (-not $exe) { $exe = "<Zotero 安装目录>\zotero.exe" }   # 按实际安装位置修改，或用 ZOTERO_EXE 指定
if (-not (Get-Process -Name zotero -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath $exe
  Start-Sleep -Seconds 8      # 等客户端与本地 HTTP 服务起来
}
python scripts/zotero_local_api.py ping
```

- `ping` 输出 `连接正常：API v3，Server-ID=...` 才继续；403 说明「允许此计算机上的其他应用程序与 Zotero 通讯」没开，先让用户在 `设置 → 高级` 勾选。
- 只负责启动与探测，不改 `zotero.sqlite`；Zotero 已在运行时不要重复启动。

## 内置依赖（自包含）

- `nature-paper-card/`：完整的 nature-paper-card 技能副本（22 个文件）。B 阶段以 `nature-paper-card/SKILL.md` 为入口，按 `nature-paper-card/manifest.yaml` 的 `always_load` 逐份加载，不再依赖技能目录外的同名技能。
- `scripts/make_notes_json_v2.py`、`scripts/cleanup_dup.py`、`scripts/reattach_note.py`：本次实际使用的过程脚本，已参数化，可直接复用。`make_notes_json.py` 为旧版（无公式转换），**新任务一律用 v2**。
- `assets/zotero-note.css`：Zotero 笔记全局排版样式（标题层级、表格字号/斑马纹、引用块、公式块），一次配置全局生效。
- `scripts/fulltext_fallback.py`：A2 批量兜底脚本（只调用内置 `prepare_paper.py`），把逐页正文写回 `zotero_fulltext.json`。

## 前置条件

开工前逐项确认：

- 待处理 PDF 已放在**本机一个绝对路径目录**下，且是带文本层的 PDF（扫描件需先 OCR）。
- 目标分类存在（默认 `reference`）；脚本按名称精确匹配。
- 用户已明确：分类名、PDF 目录、总结要求（章节取舍、语言、长度上限）。
- 建议先关闭自动同步，批量写完后手动同步一次；先备份 Zotero 数据目录。
- 本机 Python 3 可用；C0 转换器需 `markdown`（`python -m pip install markdown`）；A2 兜底还需 `pymupdf`（`python -m pip install pymupdf`），并给渲染页准备一个可写目录。导入/写回/兜底脚本本身仅用标准库。

**路线 A 额外要求**：Zotero 10+ 已运行；`设置 → 高级` 勾选「允许此计算机上的其他应用程序与 Zotero 通讯」；本机有 Python 3。详见 `references/local-api.md`。

**路线 B 额外要求**：Zotero 7+，`工具 → 开发者 → 运行 JavaScript` 可用。

## 路线选择

| | 路线 A · Local API | 路线 B · Run JavaScript |
|---|---|---|
| 版本 | Zotero 10+ | Zotero 7+ |
| 执行方式 | 本机终端跑 Python 脚本 | 开发者窗口粘贴 JS |
| 元数据识别 | 不触发 `RecognizeDocument`，父条目用文件名标题 | 可调 `RecognizeDocument` 联网识别 |
| 写入授权 | 运行时弹窗授权，可始终允许 | 无需额外授权 |
| 适用 | 批量自动化、可重复跑 | 旧版本、无 Python、兜底 |

## 三段式流水线

```
A. 导入 + 取全文（本机）
   路线 A：scripts/zotero_local_api.py import-export
   路线 B：scripts/zotero-01-import-export.js
   → 输出 zotero_fulltext.json（每篇条目 key、标题、全文）
   → 若某篇 fulltext 为 404/空：同一篇立即执行 A2 兜底（prepare_paper.py 抽同一 PDF + 渲染页核对），不得留空
        ↓ 用户把该 JSON 上传到 AI 会话
B. 逐篇总结（云端 AI 会话）
   先加载内置 nature-paper-card 的完整技能文件，再严格按 references/summary-prompt.md 原文执行
   → 输出 zotero_notes.json（条目 key + 笔记 HTML）
        ↓ 用户把该 JSON 下载回本机
C. 写回子笔记（本机）
   路线 A：scripts/zotero_local_api.py write-notes
   路线 B：scripts/zotero-02-write-notes.js
   → 在每条文献下创建/更新子笔记
```

**不要在 B 阶段凭空补全缺失信息**：`text` 为空时先去 A2 兜底（用同一 PDF 抽取正文），A2 确认 PDF 无文本层后才如实标注"无法提取正文"；`truncated` 的条目必须标注截断位置。任何情况下都不得据标题臆造结论。

## A 阶段：导入与取全文

### 路线 A（Local API）

先探测连通性并列出分类：

```powershell
python scripts/zotero_local_api.py ping
```

再导入并导出全文：

```powershell
python scripts/zotero_local_api.py import-export `
  --pdf-dir "<PDF 所在目录>" `
  --collection reference `
  --out-json "<输出目录>\zotero_fulltext.json"
```

行为：在目标分类下为每个 PDF 建 `document` 父条目（标题取文件名）→ 建 `imported_file` 附件 → 三阶段上传 PDF → 读取已索引全文并写出 JSON。分类不存在时自动新建。

### A2 全文兜底：Zotero 全文 404 / 文本为空（必做，不得跳过）

`import-export` 刚上传完就读全文，Zotero 往往还没建索引，`GET /api/users/0/items/<attKey>/fulltext` 会返回 **404** 或 `content` 为空。处理顺序固定：

1. **先等 30–60 秒重试一次**同一接口，确认不是索引延迟；
2. 仍为 404/空 → **立刻执行下面的 PDF 兜底**，用同一份 PDF 抽全文，**不得把"无正文"当结论，更不得据标题或摘要臆造**；
3. 只有在 PDF 无文本层（扫描件）时，才判定"需要 OCR"，并在汇报里写明。

**批量一键（推荐）**：对 JSON 里 `textChars=0` 的条目逐篇调 `prepare_paper.py`，并把逐页正文写回 JSON：

```powershell
python scripts/fulltext_fallback.py `
  --fulltext "<输出目录>\zotero_fulltext.json" `
  --pdf-dir  "<PDF 所在目录>" `
  --workdir  "<工作目录>\paper-card-work"
```

它会在 `--workdir` 下为每篇建 `<文件名>\source_bundle.json` 与 `rendered-pages\`，并给 JSON 条目补 `textSource=pdf_extraction`、`pdfPages`、`locatorMode`。**只处理正文为空的条目**，已有正文不动（`--force` 可强制重抽，`--only 文件名` 可单篇重跑）。

**单篇直调（等价，需自定义路径时用）**：

```powershell
$w = "<工作目录>"   # 例：<项目目录>\paper-card-work
python "<技能目录>\nature-paper-card\scripts\prepare_paper.py" `
  "<该篇 PDF 的绝对路径>" `
  --output "$w\source_bundle.json" `
  --render-dir "$w\rendered-pages"
```

脚本按 `nature-paper-card/SKILL.md` 的调用约定运行（不要写替代脚本、不要内联 Python 解析 PDF）。成功时输出：

```
Pages: N   Sections: ...   Figures: ...   Tables: ...   Equations: ...
Bundle validation: valid / valid_with_warnings
Recommended locator mode: page-grounded
```

- **页码口径**：`Recommended locator mode: page-grounded` 时，Paper Card 一律用 bundle 里的 `pdf_page`（PDF 物理页）作引用；印刷页码只在表头声明一次。
- **自动识别为 0 不等于没有图表**：中文期刊 PDF 的 `Sections/Figures/Tables` 常识别为 0，必须人工逐页看图。
- **逐页看图核对（强制）**：用 `Read` 打开 `rendered-pages\page-0NN.png`（批量路径为 `<workdir>\<文件名>\rendered-pages\`），至少覆盖"含表页 / 含关键图页 / 公式密集页"。
- **表格列结构必须看图确认**：文本层会把多列表压成"一行一串数字"，列边界不可靠。**≥6 列的表、或一行出现连续多个数值的表，未看页面图不得写入任何数字，也不得按"看起来对齐"猜列名。** 主表的列名（Prec./Rec./F1/Ord./R.L./B.S./Rel./Eff./Comp./Pos./Avg.）与行归属，一律以页面图为准。
- **冲突处理**：抽取文本与页面图不一致时以页面图为准；仍无法判定就写"原文表格列对应关系无法确认"，**不填数字**。
- **偏差披露**：把"该篇全文来自 PDF 抽取而非 Zotero 索引"写进笔记的「分析范围说明」节，并在最终汇报里单列。

### 路线 B（JavaScript）

改脚本顶部 `CONFIG`（`folder`、`collectionName`、`outJson`）后整段粘贴运行。脚本用 `importFromFile` 复制进 Zotero 存储，调 `RecognizeDocument` 识别元数据；识别失败回退文件名建 `document` 条目。

要点与坑：

- `importFromFile` 的 `parentItemID` 与 `collections` **不能同时传**，顶层导入只能给 `collections`。
- `linkFromFile` 只建**链接附件**，文件仍在原位置；要"存进 Zotero"必须用 `importFromFile`。
- 元数据识别依赖联网，离线或查不到时失败；回退建条目，不中断整批。
- 全文取 `attachment.attachmentText`，为空再试 `Zotero.PDFWorker.getFullText`；仍为空**不要直接下"扫描件"结论**，先按 A2 用内置 `prepare_paper.py` 对同一 PDF 抽正文并看渲染页。

## B 阶段：逐篇总结

1. 读取用户上传的 `zotero_fulltext.json`，按顺序逐篇处理，不跳篇、不合并篇。
2. 每篇先加载内置 `nature-paper-card/SKILL.md`，并按它的 `manifest.yaml` 读取 `always_load` 全部文件、所选 `paper_type` 片段与 `references/` 三份文件；在此基础上严格按 `references/summary-prompt.md` 的提示词原文执行：对该篇做结构化精读并生成中文 Paper Card，输出完整的 01–16 节（内容结构以提示词要求为准）。提示词原文必须原封不动执行，不得改写、删减、简化或翻译；用户的额外要求（章节取舍、语言、字数、关注点）优先级高于默认模板。
3. 笔记按 `references/note-template.md` 生成**纯 HTML**（Zotero 笔记只接受 HTML，不认 Markdown）。公式按 `references/summary-prompt.md` 的《附加执行规范》写：行内 `$…$`、行间独立成段 `$$…$$`、上下标 `X_{sub}` / `X^{sup}`；标题内不写公式。
4. 断言必须来自该篇正文。正文来源优先级：**Zotero 全文（`text`） > A2 的 `source_bundle.json`（`pages[].pdf_page` + `text`）**；两处都不存在时才谈缺失。`truncated: true` 时在笔记顶部标注"全文被截断，结论仅基于前 N 字符"。只有在 A2 兜底已执行且 PDF 确无文本层时，才写"无法提取正文（可能为扫描件，需 OCR）"。
5. **表格数字先核列结构，再落笔**：按 A2 的规则逐页看图确认列归属（≥6 列或一行多值必看）。列归属无法确认的数字一律不写，改写成"原文未报告列对应关系"。引用同一指标时要注明口径（全量主表 vs 100 条子集），不得跨口径直接比较。
6. 汇总输出 `zotero_notes.json`（HTML 必须经 `scripts/make_notes_json_v2.py` 生成或规范化，不要手搓 `$…$` 直接塞进 `html` 字段）：

```json
[
  {
    "key": "ABCD2345",
    "title": "论文标题",
    "html": "<h1>...</h1><p>...</p>",
    "tags": ["paper-card"]
  }
]
```

`key` 必须原样取自 A 阶段 JSON，不得改写、猜测或重新生成。

7. 交付该 JSON 给用户下载，并提示放到本机可访问路径。**若 B 阶段同时保留了每篇 Paper Card 的 `.md`，一并交付**——本机可用 `--card` 重新生成，比事后正则修 HTML 更干净。

## C 阶段：写回子笔记

### C0. 先转换/规范化 HTML（必做）

```powershell
# 有 Markdown 源（推荐）：从 md 生成，公式规范落成 math 节点
python scripts/make_notes_json_v2.py --card "cards\ABCD2345.md" --key ABCD2345 `
  --out "<输出目录>\zotero_notes.json" --merge

# 只有 B 阶段产出的 JSON：就地规范化 $…$、裸下标、来源标注
python scripts/make_notes_json_v2.py --notes "<输出目录>\zotero_notes.json"
```

判断成功的唯一信号是自检行里 **`residual_$=0`**（没有漏转的 `$`）；`math_inline` / `math_display` 为转成的公式节点数。若 `residual_$>0`，说明有公式没落成节点，先修 md 再重跑，不要直接写库。

### 路线 A（Local API）

```powershell
python scripts/zotero_local_api.py write-notes `
  --notes "<输出目录>\zotero_notes.json"
```

- 按 `key` 取条目；命中附件则上移到父条目。
- 已有带 `paper-card` 标签的子笔记默认覆盖更新；`--no-update-existing` 时跳过。
- 只新增/更新 `paper-card` 子笔记，**绝不删除**任何已有条目或笔记。

### 路线 B（JavaScript）

改 `CONFIG.notesJson` 后运行 `scripts/zotero-02-write-notes.js`：`new Zotero.Item('note')` → `parentItemID` → `setNote(html)` → `addTag('paper-card')` → `saveTx()`；同标签笔记幂等更新。

## 失败处理顺序

1. Local API 403 → 开关未开，引导到 设置 → 高级 勾选；401 → 重新授权；412/428 → 检查 Server-ID 头。状态码详见 `references/local-api.md`。
2. `collection not found` → 列出全部分类名让用户核对；路线 A 可自动新建，路线 B 不自动建。
3. `parentItemID and collections cannot both be provided` → 顶层条目只能传 `collections`。
4. 全文 404/空 → 先等 30–60 秒重试同一接口；仍空则**按 A2 用 `prepare_paper.py` 抽同一 PDF + 逐页看图核对**，并在笔记与汇报中标明"全文来自 PDF 抽取"；只有 PDF 无文本层（扫描件）才判定需 OCR。不得用标题或摘要编造正文。
5. 表格数字与正文/摘要不一致 → 以页面图为准；列归属无法确认就写"列对应关系无法确认"，不填数字，不用"最像的列"凑数。
6. 元数据无匹配 → 接受回退的 `document` 条目，用文件名作标题，笔记标注"元数据未识别"。
7. 单篇失败不中断整批；全部跑完再汇总失败清单。
8. 同一错误连续两次 → 停下核对 Zotero 版本与接口状态，不要盲目重复运行。
9. 公式没渲染（显示成 `$…$` 原文）→ 依次核对：① 客户端是否 6.0.14+；② HTML 里是否确实是 `<span class="math">$…$</span>` / `<pre class="math">$$…$$</pre>`（缺 `class="math"` 不认）；③ 公式是否被包在 `<code>`、标题或别的节点里；④ 是否忘了先跑 C0 转换。

## 交付说明

完成后向用户报告：处理篇数、成功写入数、失败清单、分类位置、核对方式（在 Zotero 中展开条目看子笔记）。并提醒：本机脚本产生的 JSON 与笔记属于用户数据，云端不保留副本。

**偏差必须单列，不得省略**：例如"Zotero 全文接口 404，该篇正文来自 `prepare_paper.py` 的 PDF 抽取"、"某表列对应关系无法确认"、"元数据未识别"、"某篇为扫描件需 OCR"。每条偏差要写清：影响哪一篇/哪一张表、采取了什么替代路径、哪些结论因此需要打折。

## 资源索引

- `references/local-api.md`：Local API 连接、授权、上传三阶段、状态码与字段约定（路线 A）。
- `references/zotero-js-api.md`：JavaScript API 签名、约束与常见报错（路线 B）。
- `references/note-template.md`：Paper Card 笔记的 HTML 结构、字段、写作规则与《公式与上下标规范》。
- `references/summary-prompt.md`：B 阶段逐篇总结使用的提示词原文（原样执行，不得改写）。
- `scripts/zotero_local_api.py`：路线 A 直连脚本，子命令 `ping` / `import-export` / `write-notes`。
- `scripts/fulltext_fallback.py`：A2 批量兜底脚本，逐篇调用内置 `prepare_paper.py`，把逐页正文写回 `zotero_fulltext.json`（新增 `textSource` / `pdfPages` / `locatorMode`）。
- `scripts/zotero-01-import-export.js`：路线 B，A 阶段导入 PDF 并导出全文 JSON。
- `scripts/zotero-02-write-notes.js`：路线 B，C 阶段把总结写回为子笔记。
- `nature-paper-card/`：内置的完整 nature-paper-card 技能（22 个文件：`SKILL.md`、`manifest.yaml`、`static/core/` 3 个、`static/fragments/paper_type/` 6 个、`references/` 3 个、`scripts/` 2 个，以及 README、evals、tests 等）。B 阶段只用这份内置副本。
- `nature-paper-card/scripts/prepare_paper.py`：PDF → `source_bundle.json`（逐页正文、`pdf_page`/印刷页码、渲染页）；**A2 全文兜底的唯一入口**，按 `nature-paper-card/SKILL.md` 的调用约定使用，不要写替代脚本。
- `nature-paper-card/scripts/audit_paper_card.py`：Paper Card 落地审计，产出 `audit-report.json`。
- A2 产物：`source_bundle.json`、`rendered-pages/page-0NN.png`。渲染页是**核对表格列结构与图表的唯一依据**，Paper Card 的页码引用以 `source_bundle.json` 的 `pdf_page` 为准。
- `scripts/make_notes_json_v2.py`：**C0 唯一入口**。Paper Card Markdown（或已有 `zotero_notes.json`）→ Zotero 原生 math 节点 + 上下标 + 灰色来源标注；`--merge` 按 key 合并，`--notes` 修存量，自检输出 `residual_$` 必须为 0。
- `assets/zotero-note.css`：粘贴到 Config Editor 的 `extensions.zotero.note.css`，统一标题层级、表格字号/斑马纹、引用块与公式块排版（全局生效，需重启 Zotero）。
- `scripts/make_notes_json.py`：旧版转换器（**无公式转换，仅保留兼容**，新任务用 v2）。
- `scripts/cleanup_dup.py`：列出/清理同一父条目下重复的 `paper-card` 子笔记（默认只列出，`--delete` 或 `--dedupe` 才删除）。
- `scripts/reattach_note.py`：把被误改成独立笔记的子笔记重新挂回指定父条目。
