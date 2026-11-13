/*
 * zotero-paper-notes · C 阶段
 * 把 AI 生成的总结写回 Zotero：在对应条目下创建/更新子笔记
 *
 * 用法：Zotero 7 → 工具 → 开发者 → 运行 JavaScript → 修改 CONFIG → 粘贴运行
 * 输入：zotero_notes.json（[{ key, title, html, tags }]）
 */

const CONFIG = {
	notesJson: "/绝对路径/zotero_notes.json",   // 必改
	collectionName: "reference",               // 目标分类名
	noteTag: "paper-card",                     // 用于幂等识别
	updateExisting: true,                      // 已存在同标签笔记则更新
	extraTags: []                              // 例如 ["literature-notes"]
};

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

async function resolveItem(key, title) {
	let item = null;
	if (key) {
		try {
			item = Zotero.Items.getByLibraryAndKey(libID, key);
		}
		catch (e) {}
	}
	if (!item && title) {
		try {
			const s = new Zotero.Search();
			s.libraryID = libID;
			s.addCondition("title", "is", title);
			const ids = await s.search();
			if (ids.length) {
				item = Zotero.Items.get(ids[0]);
			}
		}
		catch (e) {}
	}
	if (!item) {
		return null;
	}
	// 若命中的是子附件，上移到父条目
	if (item.isAttachment && item.isAttachment() && item.parentItemID) {
		item = Zotero.Items.get(item.parentItemID);
	}
	return item;
}

const libID = Zotero.Libraries.userLibraryID;
const collection = findCollection(CONFIG.collectionName);

let raw;
try {
	raw = await Zotero.File.getContentsAsync(CONFIG.notesJson);
}
catch (e) {
	throw new Error("读不到笔记 JSON：" + CONFIG.notesJson + " — " + e.message);
}

let notes;
try {
	notes = JSON.parse(raw);
}
catch (e) {
	throw new Error("笔记 JSON 解析失败：" + e.message);
}
if (!Array.isArray(notes)) {
	throw new Error("笔记 JSON 顶层必须是数组");
}

const stats = { created: 0, updated: 0, skipped: 0, failed: 0, failures: [] };

for (const n of notes) {
	try {
		if (!n || !n.html) {
			throw new Error("缺少 html 字段");
		}
		const parent = await resolveItem(n.key, n.title);
		if (!parent) {
			throw new Error("找不到条目：key=" + n.key + " title=" + (n.title || ""));
		}
		if (parent.isNote && parent.isNote()) {
			throw new Error("命中项是笔记而非文献条目");
		}

		// 确保条目在目标分类
		if (!parent.getCollections().includes(collection.id)) {
			parent.addToCollection(collection.id);
			await parent.saveTx();
		}

		// 找已有同标签子笔记
		let existing = null;
		for (const nid of parent.getNotes()) {
			const note = Zotero.Items.get(nid);
			if (!note) continue;
			const tags = note.getTags() || [];
			if (tags.some(t => t.tag === CONFIG.noteTag)) {
				existing = note;
				break;
			}
		}

		if (existing) {
			if (!CONFIG.updateExisting) {
				stats.skipped++;
				continue;
			}
			existing.setNote(n.html);
			await existing.saveTx();
			stats.updated++;
			continue;
		}

		const note = new Zotero.Item("note");
		note.libraryID = libID;
		note.parentItemID = parent.id;
		note.setNote(n.html);
		note.addTag(CONFIG.noteTag);
		for (const t of (n.tags || []).concat(CONFIG.extraTags)) {
			if (t && t !== CONFIG.noteTag) note.addTag(t);
		}
		await note.saveTx();
		stats.created++;
	}
	catch (e) {
		stats.failed++;
		stats.failures.push({ key: n && n.key, title: n && n.title, error: e.message });
	}
}

return {
	目标分类: collection.name,
	新建笔记: stats.created,
	更新笔记: stats.updated,
	跳过: stats.skipped,
	失败: stats.failed,
	失败清单: stats.failures
};
