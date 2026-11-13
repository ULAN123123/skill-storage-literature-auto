# Zotero JavaScript API 速查（本技能用到的部分）

来源：Zotero 官方文档 `dev/client_coding/javascript_api`、源码 `xpcom/attachments.js`、`xpcom/recognizeDocument.js`。Zotero 6 与 7 存在差异，以 7 为准。

## 运行环境

- 入口：`工具 → 开发者 → 运行 JavaScript`，输入框内代码被包进 `async function`，可直接 `await`，`return` 的结果显示在右侧。
- 可用全局：`Zotero`、`ZoteroPane`（窗口作用域）、`IOUtils`、`PathUtils`、`OS`。
- 打印调试：`Zotero.debug(...)`；错误看 `工具 → 开发者 → 错误控制台`。

## 库与分类

```js
Zotero.Libraries.userLibraryID            // 当前用户库 ID
Zotero.Collections.getByLibrary(libID, true)   // 返回分类数组（含子分类）
ZoteroPane.getSelectedCollection()        // 用户在左侧选中的分类（兜底用）
collection.getChildItems()                // 分类下顶层条目（不含子附件）
collection.getChildItems(true)            // 只取 itemID
item.addToCollection(collectionID); await item.saveTx();
```

## 导入 PDF

```js
const att = await Zotero.Attachments.importFromFile({
  file: "/abs/path/paper.pdf",   // nsIFile 或路径字符串
  libraryID: libID,              // 顶层条目给 libraryID
  collections: [collectionID],   // 顶层条目可指定分类（ID 或 key）
  contentType: "application/pdf",
  saveOptions: {}                // 可选
});
```

约束：

- `parentItemID` 与 `collections` **互斥**，同时传直接抛 `parentItemID and collections cannot both be provided`。
- `importFromFile` 是 **imported_file**（复制进 Zotero 存储），原文件不受影响。
- `linkFromFile({file, parentItemID, collections, contentType, title})` 创建 **linked_file**（只记路径，原文件移动即失效）。
- 返回值是 attachment 类型的 `Zotero.Item`。

## 元数据识别

```js
await Zotero.RecognizeDocument.recognizeItems([att1, att2]); // 只接受顶层 PDF/EPUB 附件
```

- 依赖联网；无匹配时该篇失败（不是整批失败），需自行回退建条目。
- 识别成功后 PDF 变成新父条目的子附件，并继承原分类。

## 建立父条目（回退方案）

```js
const parent = new Zotero.Item("document");
parent.libraryID = libID;
parent.setField("title", "文件名去掉扩展名");
parent.addToCollection(collectionID);
await parent.saveTx();

att.parentID = parent.id;   // 重新挂为子附件
await att.saveTx();
```

## 全文

```js
let text = await att.attachmentText;          // 已索引时可直接取，未索引为 null
if (!text) {
  try {
    const r = await Zotero.PDFWorker.getFullText(att.id);  // { text, ... } 或字符串
    text = typeof r === "string" ? r : (r && r.text) || "";
  } catch (e) {}
}
```

- 无文本层的扫描件两条路径都为空 → 需 OCR，不要用标题编内容。
- 大文件全文可能很长，导出前按字符上限截断并标记 `truncated`。

## 子笔记

```js
const note = new Zotero.Item("note");
note.libraryID = libID;
note.parentItemID = parent.id;     // 挂到父条目下
note.setNote("<h1>标题</h1><p>正文</p>");   // 必须是 HTML
note.addTag("paper-card");
await note.saveTx();
```

读取与更新：

```js
parent.getNotes()                  // 子笔记 itemID 数组
Zotero.Items.get(noteID).getNote() // 取 HTML
note.setNote(newHtml); await note.saveTx();
```

## 条目定位

```js
Zotero.Items.getByLibraryAndKey(libID, "ABCD2345")   // 同步，按 key 精确取
Zotero.Items.get(itemID)
Zotero.Items.getAsync(itemIDs)
item.key        // 8 位条目 key，JSON 里用它做锚点
```

标题兜底：

```js
const s = new Zotero.Search();
s.libraryID = libID;
s.addCondition("title", "is", title);
const ids = await s.search();
```

## 文件写入

```js
await Zotero.File.putContentsAsync("/abs/out.json", JSON.stringify(data, null, 2));
const raw = await Zotero.File.getContentsAsync("/abs/in.json");
```

## 常见报错

| 报错 | 原因 | 处理 |
|---|---|---|
| `parentItemID and collections cannot both be provided` | 同时传了两个互斥参数 | 顶层导入只传 `collections` |
| `collection not found` | 分类名不存在或大小写/空格不符 | 列出可用分类，让用户改配置 |
| 识别失败 / noMatches | 离线、查不到 DOI/arXiv | 回退建 `document` 条目 |
| 全文为 `null` | PDF 未索引或无文本层 | 先在阅读器打开或 OCR |
| `Already has parent` | 对已有父条目的附件再识别 | 跳过识别 |
