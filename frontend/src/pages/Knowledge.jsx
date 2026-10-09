import React, { useEffect, useRef, useState } from "react";
import { api, apiForm } from "../api";
import {
  documentUploadDefaults,
  documentTypeOptions,
  documentTagPresets,
  chunkStageOptions,
  chunkScenarioOptions,
  documentPageSizes,
} from "../constants/documents";
import {
  splitDocumentTags,
  toggleDocumentTag,
  fileExtensionLabel,
  fileSizeLabel,
  analysisStatusText,
  analysisStatusTitle,
  readDocumentPreview,
  inferDocumentSourceType,
  inferDocumentTags,
  parseStatusLabel,
} from "../utils/knowledge";

function DocumentCard({ document, canEdit, onToggle, onOpenChunks, onSave, onDelete }) {
  const current = document.current_version;
  const isActive = document.status === "active";
  const parsed = document.parse_status === "parsed";
  const tags = splitDocumentTags(document.tags);
  const versions = document.versions || [];
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [editForm, setEditForm] = useState({ title: document.title, source_type: document.source_type, tags: document.tags || "", reparse: false });
  const editTags = splitDocumentTags(editForm.tags);
  const editTagPresets = documentTagPresets[editForm.source_type] || [];

  useEffect(() => {
    if (!isEditing) setEditForm({ title: document.title, source_type: document.source_type, tags: document.tags || "", reparse: false });
  }, [document.id, document.title, document.source_type, document.tags, isEditing]);

  async function submitEdit() {
    const title = editForm.title.trim();
    if (!title) return;
    setIsSaving(true);
    try {
      await onSave(document.id, { ...editForm, title });
      setIsEditing(false);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <article className={`document-card ${document.status === "disabled" ? "is-disabled" : ""} ${isEditing ? "is-editing" : ""} ${canEdit ? "" : "no-actions"}`}>
      <div className="document-main">
        <div className="document-title-row">
          <b>{document.title}</b>
          <span className="doc-type-chip">{document.source_type}</span>
          <span className={`parse-chip ${parsed ? "success" : ""}`}>{parseStatusLabel(document.parse_status)}</span>
        </div>
        <div className="document-tags">
          {tags.length ? tags.slice(0, 5).map((tag) => <span key={tag}>{tag}</span>) : <span>未设置标签</span>}
        </div>
        {document.error_message && <p className="error-line">{document.error_message}</p>}
      </div>
      <div className="document-version-panel">
        <div className="version-metric" title={`共 ${versions.length} 个版本`}>
          <strong>{current?.version_label || "未解析"}</strong>
          <span>版本</span>
        </div>
        <button className="chunk-count-button" type="button" onClick={onOpenChunks}>
          <b>{current?.chunk_count || 0}</b>
          <span>片段</span>
        </button>
      </div>
      {canEdit && (
        <div className="document-actions">
          <div className="document-action-toggle">
            <span>AI 引用</span>
            <button
              className={`ios-switch ${isActive ? "on" : ""}`}
              type="button"
              role="switch"
              aria-checked={isActive}
              aria-label={`${isActive ? "停用" : "启用"}${document.title}`}
              onClick={() => onToggle(document.id)}
            >
              <span />
            </button>
          </div>
          <div className="document-action-buttons">
            <button className={`doc-action-button ${isEditing ? "is-active" : ""}`} type="button" onClick={() => setIsEditing((value) => !value)}>{isEditing ? "收起" : "编辑"}</button>
            <button className="doc-action-button danger" type="button" onClick={onDelete}>删除</button>
          </div>
        </div>
      )}
      {canEdit && isEditing && (
        <div className="document-edit-panel">
          <div className="document-edit-group">
            <div className="edit-group-title">
              <span>文件信息</span>
              <small>用于列表名称和引用来源</small>
            </div>
            <label>
              <span>文件名</span>
              <input value={editForm.title} onChange={(event) => setEditForm({ ...editForm, title: event.target.value })} />
            </label>
            <label className="document-reparse-toggle">
              <input type="checkbox" checked={editForm.reparse} onChange={(event) => setEditForm({ ...editForm, reparse: event.target.checked })} />
              <span>保存后重新解析文件</span>
            </label>
          </div>
          <div className="document-edit-group document-edit-settings">
            <div className="edit-group-title">
              <span>资料设置</span>
              <small>影响检索、解析和 AI 引用</small>
            </div>
            <div className="document-edit-row">
              <span>资料类型</span>
              <div className="edit-type-toggle">
                {documentTypeOptions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={editForm.source_type === item ? "active" : ""}
                    onClick={() => setEditForm({ ...editForm, source_type: item, tags: "" })}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
            <div className="document-edit-row">
              <span>标签设置</span>
              <div className="edit-tag-row">
                {editTagPresets.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    className={editTags.includes(tag) ? "selected" : ""}
                    onClick={() => setEditForm({ ...editForm, tags: toggleDocumentTag(editForm.tags, tag) })}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="document-edit-actions">
            <div className="edit-save-note">
              <span>保存设置</span>
              <p>{editForm.reparse ? "会重新解析当前文件，并更新后续 AI 引用。" : "仅更新文件名、类型和标签，不重新拆分片段。"}</p>
            </div>
            <div className="edit-save-buttons">
              <button className="edit-save-button is-ghost" type="button" disabled={isSaving} onClick={() => setIsEditing(false)}>取消</button>
              <button className="edit-save-button is-primary" type="button" disabled={isSaving || !editForm.title.trim()} onClick={submitEdit}>{isSaving ? "保存中" : "保存"}</button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

function ChunkDetail({ document, onBack, onError }) {
  const [chunks, setChunks] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [filters, setFilters] = useState({ chunk_type: "", stage: "", scenario: "", status: "" });
  const [loading, setLoading] = useState(false);
  const typeOptions = Object.keys(document.current_version?.structured_data?.chunk_types || {});
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    setPage(1);
  }, [pageSize, filters.chunk_type, filters.stage, filters.scenario, filters.status]);

  useEffect(() => {
    loadChunks().catch((err) => onError(err.message));
  }, [document.id, page, pageSize, filters.chunk_type, filters.stage, filters.scenario, filters.status]);

  async function loadChunks() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.set(key, value);
      });
      const data = await api(`/knowledge/documents/${document.id}/chunks?${params.toString()}`);
      setChunks(data.items || []);
      setTotal(data.total || 0);
    } finally {
      setLoading(false);
    }
  }

  function updateFilter(key, value) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <section className="page chunk-detail-page">
      <div className="chunk-detail-head">
        <button className="text-button back-button" onClick={onBack}>返回</button>
        <b>{document.title}</b>
        <span className="small">{document.current_version?.version_label || "-"} · {total} 个片段</span>
      </div>
      <section className="panel chunk-detail-panel">
        <div className="panel-inner">
          <div className="chunk-controls">
            <label>片段类型<select value={filters.chunk_type} onChange={(e) => updateFilter("chunk_type", e.target.value)}><option value="">全部类型</option>{typeOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label>商机阶段<select value={filters.stage} onChange={(e) => updateFilter("stage", e.target.value)}>{chunkStageOptions.map((item) => <option key={item} value={item}>{item || "全部阶段"}</option>)}</select></label>
            <label>场景<select value={filters.scenario} onChange={(e) => updateFilter("scenario", e.target.value)}>{chunkScenarioOptions.map((item) => <option key={item || "all"} value={item}>{item || "全部场景"}</option>)}</select></label>
            <label>状态<select value={filters.status} onChange={(e) => updateFilter("status", e.target.value)}><option value="">全部状态</option><option value="active">启用</option><option value="disabled">停用</option></select></label>
            <div className="page-size-switch">
              <span>每页</span>
              {documentPageSizes.map((size) => <button key={size} className={pageSize === size ? "active" : ""} type="button" onClick={() => setPageSize(size)}>{size}</button>)}
            </div>
          </div>
          <div className="chunk-list">
            {loading ? <div className="empty-card">正在加载片段...</div> : chunks.map((chunk) => (
              <article className="chunk-card" key={chunk.id}>
                <div className="chunk-card-head">
                  <div>
                    <b>{chunk.title}</b>
                    <div className="mini-line">
                      <span>{chunk.chunk_type}</span>
                      <span>{chunk.stage}</span>
                      <span>{chunk.scenario}</span>
                      <span>{chunk.section_title || "未标注章节"}</span>
                    </div>
                  </div>
                  <div className="chunk-meta">
                    <span>{chunk.page_start ? `第 ${chunk.page_start}${chunk.page_end && chunk.page_end !== chunk.page_start ? `-${chunk.page_end}` : ""} 页` : "无页码"}</span>
                    <em>{chunk.confidence}%</em>
                    <i className={chunk.status === "active" ? "active" : ""}>{chunk.status === "active" ? "启用" : "停用"}</i>
                  </div>
                </div>
                <p>{chunk.content}</p>
              </article>
            ))}
            {!loading && !chunks.length && <div className="empty-card">当前筛选下没有片段。</div>}
          </div>
          <div className="pagination-bar">
            <span>当前 {total ? (page - 1) * pageSize + 1 : 0}-{Math.min(page * pageSize, total)} / {total} 条</span>
            <div className="pagination-controls">
              <button className="secondary" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>
              <span className="small">第 {page} / {totalPages} 页</span>
              <button className="secondary" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>下一页</button>
            </div>
          </div>
        </div>
      </section>
    </section>
  );
}

export default function Knowledge({
  user,
  items,
  documents = [],
  onChanged,
  onError,
}) {
  const [form, setForm] = useState(documentUploadDefaults);
  const [file, setFile] = useState(null);
  const fileInputRef = useRef(null);
  const [localDocuments, setLocalDocuments] = useState([]);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [typeFilter, setTypeFilter] = useState("全部");
  const [isUploading, setIsUploading] = useState(false);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [uploadNotice, setUploadNotice] = useState("");
  const [analysisStatus, setAnalysisStatus] = useState("idle");
  const [analysisSummary, setAnalysisSummary] = useState("");
  const canEdit = user.role === "admin";
  const allDocuments = documents.length ? documents : localDocuments;
  const pageDocuments = typeFilter === "全部" ? allDocuments : allDocuments.filter((item) => item.source_type === typeFilter);
  const selectedTags = splitDocumentTags(form.tags);
  const tagPresets = documentTagPresets[form.source_type] || [];
  const isAnalyzing = analysisStatus === "analyzing";

  useEffect(() => {
    if (documents.length) return;
    refreshLocalDocuments().catch(() => setLocalDocuments([]));
  }, [documents.length]);

  async function refreshLocalDocuments() {
    const nextDocuments = await api("/knowledge/documents");
    setLocalDocuments(nextDocuments);
    return nextDocuments;
  }

  function openFilePicker() {
    if (!isUploading && !isAnalyzing) fileInputRef.current?.click();
  }

  async function prepareFile(nextFile) {
    if (isUploading || isAnalyzing) return;
    if (!nextFile) {
      setUploadNotice("没有选择文件。");
      return;
    }
    setFile(nextFile);
    setAnalysisStatus("analyzing");
    setAnalysisSummary("");
    setUploadNotice("正在分析文件内容，并匹配资料类型和标签。");
    try {
      const formData = new FormData();
      formData.append("source_type", form.source_type);
      formData.append("file", nextFile);
      const result = await apiForm("/knowledge/documents/analyze", formData);
      const nextSourceType = documentTypeOptions.includes(result.source_type) ? result.source_type : form.source_type;
      const allowedTags = documentTagPresets[nextSourceType] || [];
      const nextTags = Array.isArray(result.tags)
        ? result.tags.filter((tag) => allowedTags.includes(tag)).slice(0, 5)
        : [];
      setForm({ source_type: nextSourceType, tags: nextTags.join("、") });
      setAnalysisStatus("ready");
      setAnalysisSummary(result.summary || "已完成文档预分析，可在右侧调整后上传。");
      setUploadNotice("已完成预分析，可确认资料类型和标签后上传文件。");
    } catch {
      const preview = await readDocumentPreview(nextFile);
      const nextSourceType = inferDocumentSourceType(nextFile, form.source_type, preview);
      const nextTags = inferDocumentTags(nextFile, nextSourceType, preview);
      setForm({ source_type: nextSourceType, tags: nextTags.join("、") });
      setAnalysisStatus("error");
      setAnalysisSummary("LLM 预分析暂不可用，已使用本地规则预选资料类型和标签。");
      setUploadNotice("预分析失败，已用本地规则预选；可手动调整后上传。");
    }
  }

  async function uploadSelectedFile(targetFile = file, targetForm = form) {
    if (!targetFile) {
      setUploadNotice("请先选择一个资料文件");
      return onError("请先选择一个资料文件");
    }
    const formData = new FormData();
    formData.append("source_type", targetForm.source_type);
    formData.append("tags", targetForm.tags);
    formData.append("source_name", targetFile.name);
    formData.append("recommended", "根据文档内容生成可引用依据。");
    formData.append("banned", "不要编造文档中没有的信息。");
    formData.append("file", targetFile);
    try {
      setIsUploading(true);
      setUploadNotice("正在上传并解析；如果是同名文件，系统会自动生成新版。");
      await apiForm("/knowledge/documents", formData);
      setFile(null);
      setForm({ ...documentUploadDefaults, source_type: targetForm.source_type });
      setAnalysisStatus("idle");
      setAnalysisSummary("");
      setUploadNotice("已上传，文档版本和片段数量已更新。");
      await onChanged();
      await refreshLocalDocuments();
    } catch (err) {
      setUploadNotice(`上传失败：${err.message}`);
      onError(err.message);
    } finally {
      setIsUploading(false);
    }
  }

  async function uploadDocument(event) {
    event.preventDefault();
    await uploadSelectedFile();
  }

  function cancelUpload() {
    if (isUploading) return;
    setFile(null);
    setForm(documentUploadDefaults);
    setAnalysisStatus("idle");
    setAnalysisSummary("");
    setUploadNotice("");
    setIsDraggingFile(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleFileInputChange(event) {
    await prepareFile(event.target.files?.[0] || null);
    event.target.value = "";
  }

  function handleDragOver(event) {
    event.preventDefault();
    if (!isUploading && !isAnalyzing) setIsDraggingFile(true);
  }

  function handleDragLeave(event) {
    if (event.relatedTarget && event.currentTarget.contains(event.relatedTarget)) return;
    setIsDraggingFile(false);
  }

  function handleDropZoneKeyDown(event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    openFilePicker();
  }

  async function handleDrop(event) {
    event.preventDefault();
    setIsDraggingFile(false);
    await prepareFile(event.dataTransfer.files?.[0] || null);
  }

  async function toggleDocument(documentId) {
    try {
      await api(`/knowledge/documents/${documentId}/toggle`, { method: "POST" });
      onChanged();
    } catch (err) {
      onError(err.message);
    }
  }

  async function saveDocument(documentId, payload) {
    try {
      await api(`/knowledge/documents/${documentId}`, { method: "PATCH", body: JSON.stringify(payload) });
      await onChanged();
      await refreshLocalDocuments();
    } catch (err) {
      onError(err.message);
      throw err;
    }
  }

  async function deleteDocument(documentId, title) {
    if (!window.confirm(`确认删除「${title}」？删除后该文档版本和片段都不会再参与引用。`)) return;
    try {
      await api(`/knowledge/documents/${documentId}`, { method: "DELETE" });
      await onChanged();
      await refreshLocalDocuments();
    } catch (err) {
      onError(err.message);
    }
  }

  if (selectedDocument) {
    return (
      <ChunkDetail
        document={selectedDocument}
        onBack={() => setSelectedDocument(null)}
        onError={onError}
      />
    );
  }

  return (
    <section className="page">
      {canEdit && (
        <form className="panel doc-upload-panel" onSubmit={uploadDocument}>
          <div className="panel-inner knowledge-manager">
            <div className="section-heading">
              <div><h4>导入资料</h4></div>
            </div>
            <div className="upload-box">
              <div
                className={`upload-drop ${file ? "has-file" : ""} ${isDraggingFile ? "is-dragging" : ""}`}
                role="button"
                tabIndex={0}
                aria-disabled={isUploading || isAnalyzing}
                onClick={openFilePicker}
                onKeyDown={handleDropZoneKeyDown}
                onDragOver={handleDragOver}
                onDragEnter={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <input ref={fileInputRef} type="file" accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={handleFileInputChange} disabled={isUploading || isAnalyzing} />
                <span>{isDraggingFile ? "松开分析" : "选择文件"}</span>
                <b>{file?.name || "拖拽文件到这里，或点击选择"}</b>
                <em>{file ? analysisStatusText(analysisStatus) : "支持 TXT / MD / PDF / DOCX，同名文件自动生成新版"}</em>
                {file && (
                  <div className="upload-file-meta">
                    <i>{fileExtensionLabel(file)}</i>
                    <i>{fileSizeLabel(file.size)}</i>
                  </div>
                )}
              </div>
              <div className="upload-options">
                <div className="upload-option-block">
                  <span className="option-label">资料类型</span>
                  <div className={`mode-switch compact ${form.source_type === "产品说明书" ? "product-doc" : ""}`}>
                    {documentTypeOptions.map((item) => (
                      <button
                        key={item}
                        type="button"
                        className={`mode-option ${form.source_type === item ? "active" : ""}`}
                        disabled={isAnalyzing}
                        onClick={() => setForm({ ...documentUploadDefaults, source_type: item })}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="upload-option-block">
                  <span className="option-label">标签</span>
                  <div className="tag-preset-grid">
                    {tagPresets.map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        className={selectedTags.includes(tag) ? "selected" : ""}
                        disabled={isAnalyzing}
                        onClick={() => setForm({ ...form, tags: toggleDocumentTag(form.tags, tag) })}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                  <p className="micro-hint">标签用于辅助检索，阶段、场景和客户类型会由解析结果自动识别。</p>
                </div>
                <div className={`analysis-status ${analysisStatus}`}>
                  <span>{analysisStatusTitle(analysisStatus)}</span>
                  <p>{analysisSummary || "选择文件后，会先分析内容，再让你确认资料类型和标签。"}</p>
                </div>
              </div>
            </div>
            {file && !isAnalyzing && (
              <div className="upload-confirm-bar">
                <div>
                  <span>确认入库</span>
                  <p>{uploadNotice || "资料类型和标签确认无误后，再上传并生成可检索片段。"}</p>
                </div>
                <div className="upload-confirm-actions">
                  <button className="secondary" type="button" disabled={isUploading} onClick={cancelUpload}>取消上传</button>
                  <button className="primary" type="submit" disabled={isUploading}>
                    {isUploading ? "上传中..." : "确认上传"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </form>
      )}

      <div className="document-toolbar">
        <div>
          <span className="small">文档列表</span>
          <h4>当前资料</h4>
        </div>
        <div className="doc-filter-tabs">
          {["全部", ...documentTypeOptions].map((item) => (
            <button className={typeFilter === item ? "active" : ""} key={item} onClick={() => setTypeFilter(item)}>{item}</button>
          ))}
        </div>
      </div>

      <div className="document-list">
        {pageDocuments.length ? pageDocuments.map((document) => (
          <DocumentCard
            key={document.id}
            document={document}
            canEdit={canEdit}
            onToggle={toggleDocument}
            onOpenChunks={() => setSelectedDocument(document)}
            onSave={saveDocument}
            onDelete={() => deleteDocument(document.id, document.title)}
          />
        )) : <div className="empty-card">{canEdit ? "还没有文档。先上传一份 SOP、话术或产品说明书。" : "还没有可查看的文档。"}</div>}
      </div>
    </section>
  );
}
