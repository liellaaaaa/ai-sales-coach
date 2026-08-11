import React, { useEffect, useState } from "react";
import { formatDate } from "../utils/score";
import { Empty } from "../components/Layout";

export default function History({ sessions, onOpen, onRetry, onClear }) {
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const pageSizeOptions = [5, 10];
  const totalPages = Math.max(1, Math.ceil(sessions.length / pageSize));
  const safePage = Math.min(currentPage, totalPages);
  const startIndex = (safePage - 1) * pageSize;
  const visibleSessions = sessions.slice(startIndex, startIndex + pageSize);
  const endIndex = Math.min(startIndex + visibleSessions.length, sessions.length);
  const showPagination = sessions.length > pageSize;

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  return (
    <section className="page">
      <div className="hero">
        <div className="intro"><span className="eyebrow">历史记录</span><h3>训练留档</h3><p className="hint">查看训练报告，或基于上一次问题再次训练。</p></div>
        <div className="metric-card"><span className="small">记录数</span><strong>{sessions.length}</strong><p className="small">当前账号数据</p></div>
      </div>
      <div className="panel">
        <div className="panel-inner">
          <div className="section-title history-title">
            <div>
              <h4>训练历史</h4>
              {!!sessions.length && <p className="small">每页显示 {pageSize} 条，当前 {sessions.length ? startIndex + 1 : 0}-{endIndex} / {sessions.length} 条。</p>}
            </div>
            <div className="history-actions">
              <div className="page-size-switch" aria-label="每页显示条数">
                <span>每页</span>
                {pageSizeOptions.map((size) => (
                  <button
                    className={pageSize === size ? "active" : ""}
                    key={size}
                    type="button"
                    onClick={() => {
                      setPageSize(size);
                      setCurrentPage(1);
                    }}
                  >
                    {size} 条
                  </button>
                ))}
              </div>
              <button className="secondary" onClick={onClear}>清空我的训练记录</button>
            </div>
          </div>
          {!sessions.length && <Empty title="还没有训练记录" text="先完成一次训练，就能在这里看到留档和再次训练入口。" />}
          <div className="records">{visibleSessions.map((item) => (
            <article className="record-item" key={item.id}>
              <div className="record-copy">
                <b>{item.customer_name} / {item.goal}</b>
                <div className="mini-line"><span>{formatDate(item.created_at)}</span><span>{item.training_type}</span><span>{item.stage}</span><span>{item.status}</span></div>
                <p className="small">查看报告，或基于这次记录再次训练。</p>
              </div>
              <div className="record-actions"><button className="secondary" onClick={() => onOpen(item)}>查看报告</button><button className="primary" onClick={() => onRetry(item)}>再次训练</button></div>
            </article>
          ))}</div>
          {showPagination && (
            <div className="pagination-bar" aria-label="训练历史分页">
              <span>第 {safePage} / {totalPages} 页</span>
              <div className="pagination-controls">
                <button className="secondary" onClick={() => setCurrentPage((page) => Math.max(1, page - 1))} disabled={safePage === 1}>上一页</button>
                {Array.from({ length: totalPages }, (_, index) => index + 1).map((page) => (
                  <button
                    className={`page-number${page === safePage ? " active" : ""}`}
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    aria-current={page === safePage ? "page" : undefined}
                  >
                    {page}
                  </button>
                ))}
                <button className="secondary" onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))} disabled={safePage === totalPages}>下一页</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
