/*
 * zotero-paper-notes · A 阶段
 * 批量把目录下的 PDF 导入 Zotero 指定分类，并导出全文 JSON
 *
 * 用法：Zotero 7 → 工具 → 开发者 → 运行 JavaScript → 修改 CONFIG → 粘贴运行
 * 建议：运行前备份 Zotero 数据目录，并暂时关闭自动同步
 */

const CONFIG = {
	folder: "/绝对路径/放PDF的文件夹",              // 必改：本机 PDF 目录
	collectionName: "reference",                    // 目标分类名
	outJson: "/绝对路径/zotero_fulltext.json",       // 必改：导出路径
	recognize: true,                                // 是否联网识别元数据
	maxCharsPerPaper: 150000,                       // 单篇正文字符上限
	skipExisting: true                              // 同名附件已存在则跳过
};

function baseName(p) {
	try {
		return PathUtils.filename(p);
	}
	catch (e) {
		return String(p).split(/[\\/]/).pop();
	}
}

function findCollection(name) {
	let cols = [];
	try {
		cols = Zotero.Collections.getByLibrary(libID, true) || [];
	}
	catch (e) {
		const sel = Zotero.getActiveZoteroPane().getSelectedCollection();
		cols = sel ? [sel] : [];
	}
	const hit = cols.find(c => String(c.name || "").trim() === String(name).trim());
	if (!hit) {
		throw new Error("collection not found: " + name
			+ " | 可用分类：" + cols.map(c => c.name).join(" / "));
	}
	return hit;
}

const libID = Zotero.Libraries.userLibraryID;
const collection = findCollection(CONFIG.collectionName);
const result = { collection: collection.name, imported: 0, skipped: 0, failed: 0, entries: [], failures: [], noText: [] };

// 1) 列出 PDF
let children = [];
try {
	children = await IOUtils.getChildren(CONFIG.folder);
}
catch (e) {
	throw new Error("无法读取目录 " + CONFIG.folder + "：" + e.message);
}
const pdfPaths = children.filter(p => /\.pdf$/i.test(p)).sort();
if (!pdfPaths.length) {
	throw new Error("目录中没有 PDF：" + CONFIG.folder);
}

// 2) 分类内已有文件名（用于跳过重复导入）
const existingNames = new Map();
for (const it of collection.getChildItems()) {
	if (it.isRegularItem && it.isRegularItem()) {
		for (const aid of it.getAttachments()) {
			const a = Zotero.Items.get(aid);
			if (a) existingNames.set(String(a.attachmentFilename || "").toLowerCase(), it);
		}
	}
	else if (it.isAttachment && it.isAttachment()) {
		existingNames.set(String(it.attachmentFilename || "").toLowerCase(), it);
	}
}

// 3) 导入
const imported = [];
for (const path of pdfPaths) {
	const name = baseName(path);
	if (CONFIG.skipExisting && existingNames.has(name.toLowerCase())) {
		result.skipped++;
		continue;
	}
	try {
		const att = await Zotero.Attachments.importFromFile({
			file: path,
			libraryID: libID,
			collections: [collection.id],
			contentType: "application/pdf"
		});
		imported.push({ att, name });
		result.imported++;
	}
	catch (e) {
		result.failed++;
		result.failures.push({ file: name, stage: "import", error: e.message });
	}
}

// 4) 元数据识别（失败不中断，后续回退建条目）
if (CONFIG.recognize && imported.length) {
	try {
		await Zotero.RecognizeDocument.recognizeItems(imported.map(r => r.att));
	}
	catch (e) {
		Zotero.debug("recognizeItems failed: " + e.message);
	}
}

// 5) 确定父条目 + 取全文
for (const r of imported) {
	let parent = r.att.parentItemID ? Zotero.Items.get(r.att.parentItemID) : null;
	let recognized = true;

	if (!parent) {
		try {
			parent = new Zotero.Item("document");
			parent.libraryID = libID;
			parent.setField("title", r.name.replace(/\.pdf$/i, ""));
			parent.addToCollection(collection.id);
			await parent.saveTx();
			r.att.parentID = parent.id;
			await r.att.saveTx();
			recognized = false;
		}
		catch (e) {
			result.failed++;
			result.failures.push({ file: r.name, stage: "parent", error: e.message });
			continue;
		}
	}
	else if (!parent.getCollections().includes(collection.id)) {
		parent.addToCollection(collection.id);
		await parent.saveTx();
	}

	let text = await r.att.attachmentText;
	if (!text) {
		try {
			const ft = await Zotero.PDFWorker.getFullText(r.att.id);
			text = typeof ft === "string" ? ft : (ft && ft.text) || "";
		}
		catch (e) {
			Zotero.debug("getFullText failed for " + r.name + ": " + e.message);
		}
	}
	text = text || "";
	const truncated = text.length > CONFIG.maxCharsPerPaper;
	const textOut = truncated ? text.slice(0, CONFIG.maxCharsPerPaper) : text;

	if (!textOut) {
		result.noText.push(r.name);
	}

	let authors = [];
	try {
		authors = (parent.getCreators() || []).map(c => c.lastName || c.name || "").filter(Boolean);
	}
	catch (e) {}

	result.entries.push({
		key: parent.key,
		attachmentKey: r.att.key,
		title: parent.getField("title") || r.name,
		year: parent.getField("date") || "",
		itemType: parent.itemType,
		metaRecognized: recognized,
		filename: r.name,
		textChars: text.length,
		truncated: truncated,
		authors: authors,
		text: textOut
	});
}

// 6) 写 JSON
const savedPath = await Zotero.File.putContentsAsync(
	CONFIG.outJson,
	JSON.stringify({
		generatedAt: new Date().toISOString(),
		collection: collection.name,
		count: result.entries.length,
		entries: result.entries
	}, null, 2)
);

return {
	collection: result.collection,
	导入成功: result.imported,
	跳过重复: result.skipped,
	失败: result.failed,
	导出条目: result.entries.length,
	无正文需OCR: result.noText,
	失败清单: result.failures,
	json路径: savedPath
};
