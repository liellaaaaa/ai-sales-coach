import React, { useEffect, useState } from "react";
import { formatDate } from "../utils/score";
import { Empty } from "../components/Layout";

export default function History({ sessions, onOpen, onRetry, onClear }) {
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;
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
      <div className="panel">
        <div className="panel-inner">
          {!sessions.length && <Empty title="还没有训练记录" text="先完成一次训练，就能在这里看到记录。" />}
          <div className="records">{visibleSessions.map((item) => (
            <article className="record-item" key={item.id}>
              <div className="record-copy">
                <b>{item.customer_name} / {item.goal}</b>
                <div className="mini-line"><span>{formatDate(item.created_at)}</span><span>{item.training_type}</span><span>{item.stage}</span><span>{item.status}</span></div>
              </div>
              <div className="record-actions"><button className="secondary" onClick={() => onOpen(item)}>查看</button><button className="primary" onClick={() => onRetry(item)}>再练</button></div>
            </article>
          ))}</div>
          {showPagination && (
            <div className="pagination-bar" aria-label="训练历史分页">
              <span>第 {safePage} / {totalPages} 页</span>
              <div className="pagination-controls">
                <button className="secondary" onClick={() => setCurrentPage((page) => Math.max(1, page - 1))} disabled={safePage === 1}>上一页</button>
                <button className="secondary" onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))} disabled={safePage === totalPages}>下一页</button>
              </div>
            </div>
          )}
          {!!sessions.length && (
            <div className="history-foot">
              <span className="small">{startIndex + 1}-{endIndex} / {sessions.length}</span>
              <button className="text-button" onClick={onClear}>清空</button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
