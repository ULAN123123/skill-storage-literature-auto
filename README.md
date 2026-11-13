# zotero-paper-notes · Zotero 文献批量精读笔记工具包

> 仓库名：`skill-storage-literature-auto`。核心功能：① 文献自动批量导入 Zotero；② 文献总结自动挂载到对应 Zotero 条目下的笔记。

把本机一个文件夹里的 **PDF 文献批量导入 Zotero 指定分类**，逐篇做**结构化精读（Paper Card，01–16 节）**，再把总结作为**子笔记写回对应文献条目**；公式自动转成 Zotero 原生 math 节点（KaTeX 渲染）。

> 本 README 是安装与操作手册：讲清**这是什么、环境要求、下载后如何安装、哪些开关要手动打开、哪些内容要手动填写、完整运行流程、文件清单与自检方法**。技能主指令以包内 `SKILL.md` 为准。

---

## 目录

1. [先读：这是什么 / 不是什么](#一先读这是什么--不是什么)
2. [环境要求](#二环境要求)
3. [下载后的安装步骤（GitHub 版本）](#三下载后的安装步骤github-版本)
4. [必须手动开启的开关（完整操作路径）](#四必须手动开启的开关完整操作路径)
5. [需要手动填写的内容（字段与参数对照）](#五需要手动填写的内容字段与参数对照)
6. [三段式完整运行流程](#六三段式完整运行流程)
7. [文件清单与用途](#七文件清单与用途)
8. [脚本命令行参数](#八脚本命令行参数)
9. [公式与排版硬约束](#九公式与排版硬约束)
10. [失败处理顺序](#十失败处理顺序)
11. [安装与可运行性自检清单](#十一安装与可运行性自检清单)
12. [隐私、安全与已知限制](#十二隐私安全与已知限制)

---

## 一、先读：这是什么 / 不是什么

### 这个工具包是什么

一套 **「本机脚本 + AI 精读提示词 + 内置精读技能」** 的组合：

- **本机脚本**（Python / JavaScript）：负责把 PDF 导入 Zotero、读取全文、把总结写回子笔记。
- **AI 精读阶段**：把导出的全文 JSON 交给兼容的 AI 会话，按内置提示词与 `nature-paper-card` 规则逐篇生成 Paper Card。
- **内置技能副本**：`nature-paper-card/` 自包含精读规则、论文类型片段、PDF 抽取与审计脚本。

### 不是什么（避免误解）

- **不是 Zotero 插件商店那种 `.xpi` 安装包**：不需要在 Zotero 里「安装插件」，也不往 Zotero 插件目录放文件。脚本通过 Zotero 官方 **Local API** 或 **运行 JavaScript** 接口与客户端通讯。
- **不能脱离 AI 会话独立完成精读总结**：A（导入取全文）和 C（写回笔记）可在本机独立跑；B（逐篇精读生成卡片）需要 AI 会话按 `references/summary-prompt.md` 完成。
- **不直接修改 `zotero.sqlite` 数据库文件**：一切写入走官方 API / JavaScript。
- **云端进程不能直连本机 Zotero**：本机脚本在你自己的电脑上运行。

### 两条本机通讯路线（二选一）

| | 路线 A · Local API（主用） | 路线 B · Run JavaScript（兜底） |
| --- | --- | --- |
| Zotero 版本 | **10+** | **7+** |
| 执行方式 | 本机终端跑 Python 脚本 | `工具 → 开发者 → 运行 JavaScript` 粘贴两段 JS |
| 元数据识别 | 不触发联网识别，父条目用文件名标题 | 可调 `RecognizeDocument` 联网识别 DOI/作者/期刊 |
| 写入授权 | 首次写入弹窗授权，可选「始终允许」 | 无需额外授权 |
| 适用 | 批量自动化、可重复跑 | 旧版本、无 Python、兜底 |

---

## 二、环境要求

| 项 | 要求 | 备注 |
| --- | --- | --- |
| 操作系统 | Windows（主要验证环境）；Python 脚本本身用标准库与 `pathlib`，macOS / Linux 亦可，命令按各自 shell 调整 | JS 路线在 Zotero 开发者窗口内运行，与系统无关 |
| Zotero | 路线 A：**10+**；路线 B：**7+**；笔记公式渲染建议 **6.0.14+** | 客户端需保持运行 |
| Python | 3.8+（路线 A 及 C0/A2 脚本） | 导入/写回/兜底脚本仅用标准库；C0 转换器与 A2 抽取各需一个第三方库，见下两行 |
| Python-Markdown（C0 必需） | `python -m pip install markdown` | `make_notes_json_v2.py` / `make_notes_json.py` 把 Markdown 转 HTML 时依赖；不装会 ImportError |
| PyMuPDF（A2 必需） | `python -m pip install pymupdf` | 仅当 Zotero 全文 404/空、需从 PDF 兜底抽取并渲染页面图时用到；审计脚本不依赖它 |
| PDF 资料 | 带文本层的 PDF，放在本机一个**绝对路径目录**下 | 扫描件需先 OCR |
| 网络 | 路线 B 联网识别元数据时需要；其余为本机回环通讯 | Local API 端口只本机访问，勿转发到局域网/公网 |

> 建议开工前：备份 Zotero 数据目录；暂时关闭自动同步，批量写完后手动同步一次。

---

## 三、下载后的安装步骤（GitHub 版本）

> 目标：在一台已装 Zotero 的电脑上，拿到本仓库文件后能把环境配好、跑通连通性自检。

### 步骤 1：下载并解压

1. 从 GitHub 下载仓库压缩包（Code → Download ZIP），或 `git clone <仓库地址>`。
2. 解压到一个**本地固定目录**，例如：
   - Windows：`D:\tools\zotero-paper-notes\`
   - macOS / Linux：`~/tools/zotero-paper-notes/`
3. 确认解压后根目录能看到 `SKILL.md`、`scripts/`、`references/`、`nature-paper-card/`、`assets/`。

### 步骤 2：准备 Python 环境

> 路线 A 的导入/写回、C0 笔记转换都在本机跑 Python；路线 B 仅写回用 JS，但 C0 转换仍建议在本机用 Python 完成。

1. 安装 Python 3.8+，勾选「Add Python to PATH」。
2. 打开终端（Windows 用 PowerShell 或 CMD），进入工具包目录：

   ```powershell
   cd <解压目录>\zotero-paper-notes
   ```

3. 安装第三方依赖（推荐用仓库内 `requirements.txt`）：`markdown` 为 C0 转换器必需；`pymupdf` 仅 A2 PDF 兜底需要，可先装上备用：

   ```powershell
   python -m pip install -r requirements.txt
   # 等价单行：python -m pip install markdown pymupdf
   ```

4. 校验依赖可导入、脚本语法无误（不连接 Zotero）：

   ```powershell
   python -c "import markdown; print('markdown OK')"
   python -m py_compile scripts\zotero_local_api.py scripts\fulltext_fallback.py scripts\make_notes_json_v2.py scripts\cleanup_dup.py scripts\reattach_note.py
   ```

   ```powershell
   python -m py_compile scripts\zotero_local_api.py scripts\fulltext_fallback.py scripts\make_notes_json_v2.py scripts\cleanup_dup.py scripts\reattach_note.py
   ```

   无报错即通过。

### 步骤 3：启动 Zotero

1. 打开 Zotero 客户端，等待主界面与本地服务完全加载。
2. 按[第四节](#四必须手动开启的开关完整操作路径)打开所需开关。

### 步骤 4：连通性自检（路线 A）

```powershell
python scripts\zotero_local_api.py ping
```

- 成功输出：`连接正常：API v3，Server-ID=...`，并列出当前分类。
- 输出 403：Local API 开关未开，回到第四节第 1 项检查。

### 步骤 5（可选）：作为 AI 技能加载

若在兼容的 AI 技能体系中使用，把整个目录放到用户技能目录下，目录名保持 `zotero-paper-notes`：

- 用户技能目录：`.user_skills/zotero-paper-notes/`

放置后在会话中描述任务即可触发；B 阶段由 AI 按内置规则精读。

### 步骤 6：准备资料目录

1. 新建一个存放待处理 PDF 的目录（绝对路径，路径中尽量避免特殊字符）。
2. 在 Zotero 中确认目标分类存在（默认 `reference`）；路线 A 分类不存在时脚本可自动新建，路线 B 不会自动建。

---

## 四、必须手动开启的开关（完整操作路径）

以下项目**不会随脚本自动打开**，需在 Zotero 或系统中手动操作。逐项完成后再进入流程。

### 1. 开启 Local API 通讯开关（路线 A 必做）

作用：允许本机其他程序通过 Zotero 本地接口（本机回环，默认端口 23119）调用。

操作路径：

1. Zotero 顶部菜单 → **编辑（Windows）/ Zotero（macOS）→ 设置 → 高级**。
2. 找到并勾选 **「允许此计算机上的其他应用程序与 Zotero 通讯」**。
3. 对应高级偏好项为 `extensions.zotero.httpServer.localAPI.enabled`（默认关闭）。
4. 若刚改过，重启一次 Zotero 再 `ping`。

未开启时所有接口返回 **403 `Local API is not enabled`**。

### 2. 写入授权（路线 A 首次写入时弹窗）

作用：Local API 首次向 Zotero 写入条目/笔记时需要用户授权。

操作路径：

1. 首次执行 `import-export` 或 `write-notes` 时，Zotero 会弹出授权窗口。
2. 选择 **「始终允许」**（`remember=true`）可只授权一次；选「允许」则为一次性，下次写入需再授权。
3. 授权成功后，凭证缓存在脚本同目录 `scripts/.zotero_local_auth.json`（**本机私有，不进仓库**）。
4. 如需撤销：**设置 → 高级 → 清除写入授权**。
5. 若返回 401（key 失效）：删除本地 `.zotero_local_auth.json`，下次写入重新弹窗授权。

### 3. 配置笔记全局排版 CSS（可选，推荐）

作用：统一笔记的标题层级、表格字号/斑马纹、引用块、公式块样式。

操作路径：

1. Zotero → **设置 → 高级 → 配置编辑器（Config Editor）**，接受风险提示。
2. 在搜索框输入 `extensions.zotero.note.css`。
3. 打开该项的值，把 `assets/zotero-note.css` 的**全部内容**粘贴进去。
4. **重启 Zotero** 后全局生效。

### 4. 联网识别元数据（仅路线 B，按需）

作用：导入时联网匹配 DOI / 作者 / 期刊，自动补全题录。

操作路径：

1. 保持电脑联网。
2. 在 `zotero-01-import-export.js` 的 `CONFIG` 中把 `recognize` 设为 `true`。
3. 离线或查不到时该篇识别失败，脚本回退为文件名建条目，不中断整批。

### 5. 同步与备份建议（手动）

1. 批量写入前：**先备份 Zotero 数据目录**。
2. 建议暂时**关闭自动同步**（设置 → 同步 → 取消自动同步），整批写完核对无误后再手动同步。
3. 路线 B 若要让 Zotero 自建全文索引以便站内搜索，在阅读器中打开对应 PDF 一次即可。

---

## 五、需要手动填写的内容（字段与参数对照）

所有路径、分类名、JSON 位置都需按本机实际情况填写；包内示例一律使用 `<占位符>`，**不要原样照抄**。

### 5.1 路线 A：命令行参数（终端填写）

| 参数 | 含义 | 填写示例（按本机替换） |
| --- | --- | --- |
| `--pdf-dir` | 待处理 PDF 所在本机目录 | `D:\文献\agent-papers` |
| `--collection` | 目标分类名，默认 `reference` | `reference` |
| `--out-json` | 导出全文 JSON 路径 | `D:\work\zotero_fulltext.json` |
| `--notes` | 待写回的总结 JSON 路径 | `D:\work\zotero_notes.json` |
| `--card` | 单篇 Paper Card 的 Markdown 路径（C0） | `cards\ABCD2345.md` |
| `--key` | 该篇 Zotero 父条目 key（取自 A 阶段 JSON） | `ABCD2345` |
| `--workdir` | A2 兜底的 bundle 与渲染页落盘目录 | `D:\work\paper-card-work` |

### 5.2 路线 B：JavaScript `CONFIG`（改脚本顶部后粘贴运行）

**`scripts/zotero-01-import-export.js`（A 阶段）：**

| 字段 | 含义 | 填写说明 |
| --- | --- | --- |
| `folder` | PDF 所在本机绝对路径 | 必改，如 `D:\文献\agent-papers` |
| `collectionName` | 目标分类名 | 默认 `reference`，须与 Zotero 中分类名完全一致（区分大小写/空格） |
| `outJson` | 导出全文 JSON 的绝对路径 | 必改 |
| `recognize` | 是否联网识别元数据 | `true` / `false` |
| `maxCharsPerPaper` | 单篇正文字符上限 | 默认 `150000` |
| `skipExisting` | 同名附件已存在则跳过 | `true` / `false` |

**`scripts/zotero-02-write-notes.js`（C 阶段）：**

| 字段 | 含义 | 填写说明 |
| --- | --- | --- |
| `notesJson` | 总结 JSON 的绝对路径 | 必改，即 B 阶段产出的 `zotero_notes.json` |
| `collectionName` | 目标分类名 | 与 A 阶段一致 |
| `noteTag` | 幂等识别标签 | 默认 `paper-card`，勿随意改 |
| `updateExisting` | 已存在同标签笔记则更新 | `true` / `false` |
| `extraTags` | 附加标签数组 | 如 `["literature-notes"]`，无则留空 `[]` |

### 5.3 汇报与精读要求（B 阶段告知 AI）

开始 B 阶段前，向 AI 明确：章节取舍、输出语言、字数上限、关注点、是否需要衔接你自己的已有工作。用户额外要求优先级高于默认模板。

---

## 六、三段式完整运行流程

```
A. 导入 + 取全文（本机）
   路线 A：scripts/zotero_local_api.py import-export
   路线 B：scripts/zotero-01-import-export.js
   → 输出 zotero_fulltext.json（每篇条目 key、标题、全文）
   → 某篇 fulltext 为 404/空：立即 A2 兜底（同一 PDF 抽正文 + 渲染页核对），不得留空
        ↓ 把该 JSON 上传到 AI 会话
B. 逐篇总结（AI 会话）
   加载内置 nature-paper-card 规则，严格按 references/summary-prompt.md 原文执行
   → 输出 zotero_notes.json（条目 key + 笔记 HTML）
        ↓ 把该 JSON 下载回本机
C0. 转换/规范化 HTML（本机，必做）
    make_notes_json_v2.py 把 md/JSON 规范成 math 节点 HTML，自检 residual_$ 必须为 0
C. 写回子笔记（本机）
   路线 A：scripts/zotero_local_api.py write-notes
   路线 B：scripts/zotero-02-write-notes.js
   → 在每条文献下创建/更新子笔记
```

### A 阶段：导入 PDF 并导出全文

**路线 A：**

```powershell
python scripts\zotero_local_api.py ping

python scripts\zotero_local_api.py import-export `
  --pdf-dir "<PDF 所在目录>" `
  --collection reference `
  --out-json "<输出目录>\zotero_fulltext.json"
```

行为：为每个 PDF 建 `document` 父条目（标题取文件名）→ 建 `imported_file` 附件 → 三阶段上传 PDF → 读取已索引全文并写出 JSON。

**路线 B：** 改好 `CONFIG` 后，在 `工具 → 开发者 → 运行 JavaScript` 整段粘贴运行。

### A2 全文兜底：全文 404 / 文本为空（必做，不得跳过）

刚导入的 PDF 常未被索引，全文接口返回 **404** 或空字符串。处理顺序固定：

1. **先等 30–60 秒重试一次**同一接口，确认不是索引延迟；
2. 仍为 404/空 → 立刻 PDF 兜底，用同一份 PDF 抽全文；不得把"无正文"当结论，更不得据标题/摘要臆造；
3. 只有 PDF 无文本层（扫描件）时，才判定"需要 OCR"并写明。

**批量一键（推荐）：**

```powershell
python scripts\fulltext_fallback.py `
  --fulltext "<输出目录>\zotero_fulltext.json" `
  --pdf-dir  "<PDF 所在目录>" `
  --workdir  "<工作目录>\paper-card-work"
```

在 `--workdir` 下为每篇建 `<文件名>\source_bundle.json` 与 `rendered-pages\`，补 `textSource=pdf_extraction`、`pdfPages`、`locatorMode`；只处理正文为空的条目。

**单篇直调：**

```powershell
python "nature-paper-card\scripts\prepare_paper.py" `
  "<该篇 PDF 绝对路径>" `
  --output "<工作目录>\source_bundle.json" `
  --render-dir "<工作目录>\rendered-pages"
```

**看图核对规则（强制）：**

- `page-grounded` 时一律用 bundle 里的 `pdf_page`（PDF 物理页）作引用；印刷页码只在表头声明一次。
- 用 `Read` 打开 `rendered-pages\page-0NN.png`，至少覆盖含表页、关键图页、公式密集页。
- **≥6 列的表、或一行出现连续多个数值的表，未看页面图不得写入任何数字**，不得按"看起来对齐"猜列名；列归属以页面图为准。
- 抽取文本与页面图不一致时以页面图为准；仍无法判定就写"原文表格列对应关系无法确认"，不填数字。
- 偏差（全文来自 PDF 抽取而非 Zotero 索引）必须写进笔记「分析范围说明」节，并在最终汇报单列。

### B 阶段：逐篇总结（AI 会话）

1. 读取 `zotero_fulltext.json`，按顺序逐篇处理，不跳篇、不合并篇。
2. 每篇先加载内置 `nature-paper-card/SKILL.md`，按 `manifest.yaml` 读取 `always_load` 文件、所选论文类型片段与 references；在此基础上**严格按 `references/summary-prompt.md` 提示词原文执行**，生成完整 01–16 节中文 Paper Card。提示词原文不得改写、删减、简化或翻译。
3. 笔记按 `references/note-template.md` 生成**纯 HTML**（Zotero 笔记只接受 HTML）。
4. 断言必须来自该篇正文；来源优先级：**Zotero 全文 > A2 的 `source_bundle.json`**；`truncated: true` 时标注截断位置。
5. 表格数字先核列结构再落笔；列归属无法确认的数字一律不写。
6. 汇总输出 `zotero_notes.json`，`key` 必须原样取自 A 阶段 JSON：

```json
[
  { "key": "ABCD2345", "title": "论文标题", "html": "<h1>...</h1><p>...</p>", "tags": ["paper-card"] }
]
```

### C0 阶段：转换/规范化 HTML（写库前必做）

```powershell
# 有 Markdown 源（推荐）：从 md 生成，公式规范落成 math 节点
python scripts\make_notes_json_v2.py --card "cards\ABCD2345.md" --key ABCD2345 `
  --out "<输出目录>\zotero_notes.json" --merge

# 只有 B 阶段产出的 JSON：就地规范化 $…$、裸下标、来源标注
python scripts\make_notes_json_v2.py --notes "<输出目录>\zotero_notes.json"
```

成功唯一信号：自检行 **`residual_$=0`**；`math_inline` / `math_display` 为转成的公式节点数。`residual_$>0` 先修 md 再重跑，不要直接写库。

### C 阶段：写回子笔记

**路线 A：**

```powershell
python scripts\zotero_local_api.py write-notes `
  --notes "<输出目录>\zotero_notes.json"
```

- 按 `key` 取条目；命中附件则上移到父条目。
- 已有 `paper-card` 子笔记默认覆盖更新；`--no-update-existing` 时跳过。
- 只新增/更新 `paper-card` 子笔记，**绝不删除**任何已有条目或笔记。

**路线 B：** 改 `CONFIG.notesJson` 后运行 `zotero-02-write-notes.js`：建 `note` 条目 → 挂父条目 → `setNote(html)` → 加标签 `paper-card` → 保存；同标签笔记幂等更新。

---

## 七、文件清单与用途

### 顶层

| 文件 | 用途 |
| --- | --- |
| `SKILL.md` | 技能主指令：核心事实、两条路线、三段式流水线、各阶段规则、失败处理、资源索引 |
| `.gitignore` | 排除授权凭证、Python 缓存与本机运行产物，避免进入仓库 |
| `requirements.txt` | Python 依赖清单：`markdown`（C0 必需）、`pymupdf`（A2 兜底） |
| `assets/zotero-note.css` | 笔记全局排版样式，粘贴到 Config Editor 的 `extensions.zotero.note.css` |

### `references/`（规则与提示词）

| 文件 | 用途 |
| --- | --- |
| `local-api.md` | 路线 A：连接/开关、写授权、状态码、条目 JSON、文件三阶段上传、读全文、与 JS 路线差异 |
| `zotero-js-api.md` | 路线 B：JS API 签名、库/分类、导入 PDF、元数据识别、建父条目、全文、子笔记、条目定位、常见报错 |
| `note-template.md` | Paper Card 笔记 HTML 骨架、写作规则、公式与上下标规范 |
| `summary-prompt.md` | B 阶段总结提示词原文（原样执行）+ 附加公式/上下标规范 |

### `scripts/`（本机过程脚本）

| 文件 | 类型 | 用途 |
| --- | --- | --- |
| `zotero_local_api.py` | Python（路线 A 主脚本，仅标准库） | `ping` / `import-export` / `write-notes` |
| `fulltext_fallback.py` | Python（A2 批量兜底） | 对全文为空条目调内置 `prepare_paper.py`，把逐页正文写回 JSON |
| `make_notes_json_v2.py` | Python（C0 唯一入口，现行） | Markdown/JSON → Zotero math 节点 + 上下标 + 灰色来源标注；自检 `residual_$` |
| `make_notes_json.py` | Python（旧版，仅兼容保留） | 旧转换器，**无公式转换**，新任务用 v2 |
| `cleanup_dup.py` | Python（维护，路线 A） | 列出/清理同一父条目下重复的 `paper-card` 子笔记 |
| `reattach_note.py` | Python（维护，路线 A） | 把被误改成独立笔记的子笔记重新挂回父条目 |
| `zotero-01-import-export.js` | JavaScript（路线 B，A 阶段） | 批量导入 PDF 并导出全文 JSON |
| `zotero-02-write-notes.js` | JavaScript（路线 B，C 阶段） | 把总结写回为子笔记 |

### 内置依赖 `nature-paper-card/`（精读技能副本）

| 路径 | 用途 |
| --- | --- |
| `SKILL.md` | 精读卡路由协议：加载清单 → 来源边界 → 论文类型 → 证据库 → 01–16 节 → 审计 |
| `manifest.yaml` | 核心文件加载清单、6 类论文片段映射、按需 references、质量工具与定位模式 |
| `static/core/principles.md` | 核心原则 |
| `static/core/workflow.md` | 精读工作流 |
| `static/core/output-contract.md` | 固定输出契约（01–16 节结构约束） |
| `static/fragments/paper_type/*.md` | 六类论文分析片段：methods / discovery / resource / clinical / materials / review |
| `references/evidence-and-provenance.md` | 来源标注：区分来源事实、外部事实、分析与假设 |
| `references/card-schema.md` | 01–16 节 Markdown 精确结构 |
| `references/research-idea-gates.md` | 研究方向提案把关规则（是假设，不是创新宣称） |
| `scripts/prepare_paper.py` | PDF/源码映射 → 稳定 source bundle（A2 兜底唯一入口，依赖 PyMuPDF） |
| `scripts/audit_paper_card.py` | 对照 bundle 与输出契约审计精读卡，产出报告 |
| `README.md` / `README_EN.md` | 内置技能自带中英说明 |
| `evals/evals.json` | 评测用例 |
| `tests/` | 脚本单元测试 |
| `agents/openai.yaml` | 技能面板元数据 |

> **外部依赖说明**：`manifest.yaml` 的 `always_load` 引用了 `../nature-shared/core/terminology-ledger.md`（术语台账），属外部技能，**不在本包内**；环境未安装该外部技能时，按包内 `static/core/` 三个文件继续即可。

---

## 八、脚本命令行参数

### `zotero_local_api.py`

| 子命令 | 参数 | 说明 |
| --- | --- | --- |
| `ping` | 无 | 探测 Local API 连通性，列出分类 |
| `import-export` | `--pdf-dir`（必选） | PDF 所在本机目录 |
| | `--collection`（默认 `reference`） | 目标分类名，不存在时自动新建 |
| | `--out-json`（默认 `zotero_fulltext.json`） | 导出全文 JSON 路径 |
| `write-notes` | `--notes`（必选） | `zotero_notes.json` 路径 |
| | `--update-existing` / `--no-update-existing` | 是否更新已有 `paper-card` 笔记，默认更新 |

### `fulltext_fallback.py`

| 参数 | 说明 |
| --- | --- |
| `--fulltext`（必选） | A 阶段导出的 `zotero_fulltext.json` |
| `--pdf-dir`（必选） | PDF 所在目录 |
| `--workdir`（必选） | bundle 与渲染页落盘目录 |
| `--force` | text 非空也重抽 |
| `--only` | 只处理指定文件名 |

### `make_notes_json_v2.py`

| 参数 | 说明 |
| --- | --- |
| `--card` | Paper Card 的 `.md` 路径 |
| `--key` | Zotero 父条目 key |
| `--out` | 输出 JSON 路径 |
| `--title` | 笔记标题，默认取第一个一级标题 |
| `--tags` | 逗号分隔标签，默认 `paper-card` |
| `--merge` | 与已有 JSON 合并（同 key 替换） |
| `--notes` | 存量模式：已有 `zotero_notes.json`，就地修复 html |
| `--no-subsup` | 不转换裸上下标 |
| `--keep-sources` | 不把 `[Paper: ...]` 变灰 |

### 维护脚本

| 脚本 | 参数 | 说明 |
| --- | --- | --- |
| `cleanup_dup.py` | `--parent`（必选）、`--tag`（默认 `paper-card`）、`--delete`、`--dedupe` | 排查/清理重复子笔记；默认只列出，`--delete`/`--dedupe` 才删除 |
| `reattach_note.py` | `--note`（必选）、`--parent`（必选） | 把误独立的子笔记挂回父条目 |

---

## 九、公式与排版硬约束

| 环节 | 要求 |
| --- | --- |
| B 阶段写法 | 行内 `$…$`、行间独立成段 `$$…$$`、上下标 `X_{sub}` / `X^{sup}`、星号 `$A^{*}$`；标题内禁止公式 |
| md → HTML | 用 `make_notes_json_v2.py`：`$…$`→math 节点、裸下标→`<sub>`、`x^y`→`<sup>`、`A*` 转义、`[Paper: …]` 变灰 |
| 全局排版 | Config Editor 粘贴 `assets/zotero-note.css`，重启客户端 |

禁止：标题（h1–h6）内放公式节点；KaTeX 不支持 `\begin{equation}`、`\label`、`\cite`、`\bm`、`\usepackage`；公式放进 `<code>` 不会被渲染。

---

## 十、失败处理顺序

1. **Local API 403** → 开关未开，回到第四节第 1 项；**401** → 删除本地授权缓存重新授权；**412/428** → 检查 Server-ID 头。状态码详见 `references/local-api.md`。
2. **`collection not found`** → 列出全部分类名核对；路线 A 可自动新建，路线 B 不自动建。
3. **`parentItemID and collections cannot both be provided`** → 顶层条目只能传 `collections`。
4. **全文 404/空** → 先等 30–60 秒重试；仍空则按 A2 用 `prepare_paper.py` 抽同一 PDF + 逐页看图核对，并在笔记与汇报中标明"全文来自 PDF 抽取"；只有 PDF 无文本层才判定需 OCR。不得用标题或摘要编造正文。
5. **表格数字与正文/摘要不一致** → 以页面图为准；列归属无法确认就写"列对应关系无法确认"，不填数字。
6. **元数据无匹配** → 接受回退的 `document` 条目，用文件名作标题，笔记标注"元数据未识别"。
7. 单篇失败不中断整批；全部跑完再汇总失败清单。
8. 同一错误连续两次 → 停下核对 Zotero 版本与接口状态，不要盲目重复运行。
9. **公式没渲染（显示成 `$…$` 原文）** → 依次核对：① 客户端是否 6.0.14+；② HTML 是否为 `<span class="math">$…$</span>` / `<pre class="math">$$…$$</pre>`（缺 `class="math"` 不认）；③ 公式是否被包在 `<code>`、标题或别的节点里；④ 是否忘了先跑 C0 转换。

---

## 十一、安装与可运行性自检清单

在交付/使用前逐项核对：

**文件完整性**
- [ ] 根目录含 `SKILL.md`、`.gitignore`、`requirements.txt`、`scripts/`、`references/`、`nature-paper-card/`、`assets/`
- [ ] `nature-paper-card/scripts/prepare_paper.py` 与 `audit_paper_card.py` 存在
- [ ] 无 `.zotero_local_auth.json`、无 `__pycache__/`、无 `*.pyc`、无本机运行产物 JSON

**本机环境**
- [ ] Zotero 已安装并运行；路线 A 版本 ≥ 10，路线 B 版本 ≥ 7
- [ ] Python 3.8+ 可用，`python --version` 正常
- [ ] （C0 必需）`markdown` 已安装：`python -c "import markdown"` 无报错
- [ ] （A2 需要）`pymupdf` 已安装：`python -c "import fitz"` 无报错
- [ ] Local API 开关已勾选（路线 A）

**连通性**
- [ ] `python scripts\zotero_local_api.py ping` 输出 `连接正常` 并列出分类
- [ ] 脚本语法编译无报错（见步骤 2 第 4 步）

**写入前**
- [ ] 目标分类名与 Zotero 中完全一致
- [ ] PDF 目录路径有效、PDF 带文本层
- [ ] 已备份 Zotero 数据目录，已暂停自动同步

**写回后**
- [ ] 在 Zotero 中展开条目，能看到 `paper-card` 子笔记
- [ ] 公式正常渲染（不是 `$…$` 原文）
- [ ] 偏差项（PDF 抽取、列归属无法确认、元数据未识别、扫描件需 OCR）已在笔记与汇报中单列

---

## 十二、隐私、安全与已知限制

- **授权凭证不入库**：`.zotero_local_auth.json` 由本机首次授权后自动生成，已被 `.gitignore` 排除；仓库与压缩包内不含任何 key / Server-ID。
- **本机数据不上云**：脚本产生的全文 JSON、笔记 JSON、bundle 与渲染页均为本机用户数据；B 阶段上传给 AI 的仅为你主动提供的全文内容。
- **本地回环**：Local API 只监听本机回环端口（默认 23119），不要转发到局域网或公网。
- **不臆造内容**：正文缺失时先走 A2 兜底；确无文本层才标注需 OCR；表格列归属无法确认时不填数字。
- **已知外部依赖**：`nature-shared` 术语台账不在包内（见第七节说明）；缺失时不影响主流程。
- **平台验证**：Python 脚本跨平台，文档命令以 Windows PowerShell 为例；macOS/Linux 请把路径分隔符与命令对应调整。
