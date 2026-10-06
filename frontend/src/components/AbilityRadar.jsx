import React, { useState } from "react";

const LABEL_SHORT = {
  工艺探询: "工艺探询",
  产品选型: "产品选型",
  技术边界: "技术边界",
  异议处理: "异议处理",
  故障归因: "故障归因",
  价值合规: "价值合规",
  推进动作: "推进动作",
};

export default function AbilityRadar({ scores }) {
  const items = (scores || []).slice(0, 7);
  const [activeIndex, setActiveIndex] = useState(null);
  if (!items.length) return <div className="radar-empty">暂无评分维度</div>;
  const center = 118;
  const maxRadius = 78;
  const axis = items.map((item, index) => {
    const angle = (Math.PI * 2 * index) / items.length - Math.PI / 2;
    const valueRadius = maxRadius * Math.max(0, Math.min(5, item.value)) / 5;
    return {
      ...item,
      shortName: LABEL_SHORT[item.name] || item.name,
      labelX: center + Math.cos(angle) * (maxRadius + 18),
      labelY: center + Math.sin(angle) * (maxRadius + 18),
      endX: center + Math.cos(angle) * maxRadius,
      endY: center + Math.sin(angle) * maxRadius,
      pointX: center + Math.cos(angle) * valueRadius,
      pointY: center + Math.sin(angle) * valueRadius,
    };
  });
  const polygon = axis.map((item) => `${item.pointX},${item.pointY}`).join(" ");
  const rings = [1, 2, 3, 4, 5].map((level) => {
    const radius = maxRadius * level / 5;
    return axis.map((_, index) => {
      const angle = (Math.PI * 2 * index) / items.length - Math.PI / 2;
      return `${center + Math.cos(angle) * radius},${center + Math.sin(angle) * radius}`;
    }).join(" ");
  });
  const activeItem = activeIndex === null ? null : axis[activeIndex];
  return (
    <div className="radar-wrap">
      <div className="radar-figure">
        <svg className="radar-chart" viewBox="0 0 236 236" role="img" aria-label="能力雷达图">
          {rings.map((points, index) => <polygon key={index} points={points} className="radar-ring" />)}
          {axis.map((item) => <line key={item.name} x1={center} y1={center} x2={item.endX} y2={item.endY} className="radar-axis" />)}
          <polygon points={polygon} className="radar-area" />
          <polyline points={`${polygon} ${axis[0].pointX},${axis[0].pointY}`} className="radar-line" />
          {axis.map((item, index) => (
            <g
              key={item.name}
              className="radar-point"
              role="button"
              tabIndex="0"
              aria-label={`${item.name} ${item.value}分`}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseLeave={() => setActiveIndex(null)}
              onFocus={() => setActiveIndex(index)}
              onBlur={() => setActiveIndex(null)}
              onClick={() => setActiveIndex(activeIndex === index ? null : index)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setActiveIndex(activeIndex === index ? null : index);
                }
              }}
            >
              <circle cx={item.pointX} cy={item.pointY} r="12" className="radar-hit" />
              <circle cx={item.pointX} cy={item.pointY} r="4" className={`radar-dot ${activeIndex === index ? "active" : ""}`} />
            </g>
          ))}
        </svg>
        {axis.map((item) => (
          <span
            className={`radar-label ${activeItem?.name === item.name ? "active" : ""}`}
            key={item.name}
            style={{
              left: `${(item.labelX / 236) * 100}%`,
              top: `${(item.labelY / 236) * 100}%`,
              transform: "translate(-50%, -50%)",
            }}
          >
            {item.shortName}
          </span>
        ))}
        {activeItem && (
          <div
            className="radar-tooltip"
            style={{
              left: `${(activeItem.pointX / 236) * 100}%`,
              top: `${(activeItem.pointY / 236) * 100}%`,
            }}
          >
            <b>{activeItem.name}</b>
            <span>{activeItem.value} 分</span>
          </div>
        )}
      </div>
    </div>
  );
}
