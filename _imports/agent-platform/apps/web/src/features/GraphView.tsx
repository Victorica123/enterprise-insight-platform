import React from "react";
import { Loader2, Network, RefreshCw, ScrollText, Search, X } from "lucide-react";
import {
  type ActorRole, type GraphEntity, type GraphOverview, type GraphPathQuery,
  type GraphRelation, getGraphOverview, listGraphEntities, listGraphRelations,
  queryGraphPaths, rebuildGraph,
} from "../api";
import { MetricItem, formatDate, getErrorMessage } from "./common";
import "../styles/graph-monitor.css";

const GRAPH_TYPE_ORDER = ["customer", "project", "person", "contract", "risk", "cause", "date", "ticket"];
const GRAPH_TYPE_LABELS: Record<string, string> = {
  customer: "客户", project: "项目", person: "人员", contract: "合同",
  risk: "风险", cause: "原因", date: "日期", ticket: "工单",
};
const GRAPH_TYPE_COLORS: Record<string, string> = {
  customer: "var(--viz-blue)", project: "var(--viz-aqua)", person: "var(--viz-violet)",
  contract: "var(--serious)", risk: "var(--danger)", cause: "var(--warning)",
  date: "var(--muted)", ticket: "var(--primary)",
};
const RISK_RELATION_TYPES = new Set(["延期原因", "合同风险", "约定"]);

export function GraphView({ actorRole, setError }: { actorRole: ActorRole; setError: (e: string | null) => void }) {
  const [overview, setOverview] = React.useState<GraphOverview | null>(null);
  const [entities, setEntities] = React.useState<GraphEntity[]>([]);
  const [relations, setRelations] = React.useState<GraphRelation[]>([]);
  const [selectedEntity, setSelectedEntity] = React.useState("");
  const [pathSource, setPathSource] = React.useState("");
  const [pathTarget, setPathTarget] = React.useState("");
  const [pathResult, setPathResult] = React.useState<GraphPathQuery | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [isRebuilding, setIsRebuilding] = React.useState(false);
  const [isQueryingPath, setIsQueryingPath] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const [nextOverview, nextEntities, nextRelations] = await Promise.all([
        getGraphOverview(),
        listGraphEntities(),
        listGraphRelations(),
      ]);
      setOverview(nextOverview);
      setEntities(nextEntities);
      setRelations(nextRelations);
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setIsLoading(false);
    }
  }, [setError]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleRebuild() {
    setIsRebuilding(true);
    setError(null);
    try {
      await rebuildGraph(actorRole);
      await refresh();
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setIsRebuilding(false);
    }
  }

  async function handlePathQuery(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pathSource || !pathTarget) return;
    setIsQueryingPath(true);
    setError(null);
    try {
      setPathResult(await queryGraphPaths(pathSource, pathTarget));
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setIsQueryingPath(false);
    }
  }

  const filteredRelations = selectedEntity
    ? relations.filter((r) => r.source_name === selectedEntity || r.target_name === selectedEntity)
    : relations;
  const entityOptions = entities.filter((entity) => entity.entity_type !== "date");

  return (
    <div className="graph-container">
      <section className="v3-metrics-band">
        <MetricItem label="实体" value={overview?.entity_count ?? 0} />
        <MetricItem label="关系" value={overview?.relation_count ?? 0} />
        <MetricItem label="覆盖文档" value={overview?.document_count ?? 0} />
        <MetricItem label="风险链路" value={relations.filter((r) => RISK_RELATION_TYPES.has(r.relation_type)).length} />
        <MetricItem label="最近构建" value={overview?.built_at ? formatDate(overview.built_at) : "—"} />
      </section>

      <section className="card">
        <h2>
          <Network size={19} />
          图谱视图
          {isLoading ? <Loader2 size={16} className="spin" /> : null}
          <span className="graph-toolbar">
            <button
              className="icon-button subtle"
              type="button"
              onClick={() => void handleRebuild()}
              disabled={isRebuilding || actorRole === "viewer"}
              title="从全部文档与工单重建图谱"
            >
              {isRebuilding ? <Loader2 size={16} /> : <RefreshCw size={16} />}
            </button>
          </span>
        </h2>
        {entities.length === 0 ? (
          <div className="empty-state">
            图谱为空。上传文档后自动抽取实体关系，或点击右上角重建图谱。
          </div>
        ) : (
          <>
            <GraphCanvas
              entities={entities}
              relations={relations}
              selectedEntity={selectedEntity}
              onSelectEntity={(name) => setSelectedEntity(name === selectedEntity ? "" : name)}
            />
            <div className="graph-legend">
              {GRAPH_TYPE_ORDER.filter((type) => entities.some((entity) => entity.entity_type === type)).map((type) => (
                <span className="graph-legend-item" key={type}>
                  <span className="graph-legend-dot" style={{ background: GRAPH_TYPE_COLORS[type] }} />
                  {GRAPH_TYPE_LABELS[type]}
                </span>
              ))}
              <span className="graph-legend-item">
                <span className="graph-legend-line" />
                风险关系
              </span>
            </div>
          </>
        )}
      </section>

      <section className="card">
        <h2>
          <Search size={19} />
          关系链查询
        </h2>
        <form className="path-form" onSubmit={handlePathQuery}>
          <label>
            起点
            <select value={pathSource} onChange={(event) => setPathSource(event.target.value)}>
              <option value="">选择实体</option>
              {entityOptions.map((entity) => (
                <option key={`${entity.entity_type}-${entity.name}`} value={entity.name}>
                  {entity.name}（{entity.type_label}）
                </option>
              ))}
            </select>
          </label>
          <label>
            终点
            <select value={pathTarget} onChange={(event) => setPathTarget(event.target.value)}>
              <option value="">选择实体</option>
              {entityOptions.map((entity) => (
                <option key={`${entity.entity_type}-${entity.name}`} value={entity.name}>
                  {entity.name}（{entity.type_label}）
                </option>
              ))}
            </select>
          </label>
          <button className="button" type="submit" disabled={!pathSource || !pathTarget || isQueryingPath}>
            {isQueryingPath ? <Loader2 size={14} /> : <Search size={14} />}
            查询链路
          </button>
        </form>
        {pathResult ? (
          pathResult.paths.length === 0 ? (
            <div className="empty-state">
              {pathResult.source} 与 {pathResult.target} 在 {pathResult.max_depth} 跳内没有关系链。
            </div>
          ) : (
            <ul className="graph-path-list result">
              {pathResult.paths.map((path, index) => (
                <li key={`${path.display}-${index}`}>{path.display}</li>
              ))}
            </ul>
          )
        ) : null}
      </section>

      <section className="card">
        <h2>
          <ScrollText size={19} />
          关系明细
          {selectedEntity ? (
            <span className="entity-chip active" onClick={() => setSelectedEntity("")}>
              {selectedEntity} <X size={12} />
            </span>
          ) : null}
          <span className="count-badge">{filteredRelations.length}</span>
        </h2>
        {filteredRelations.length === 0 ? (
          <div className="empty-state">暂无关系记录。</div>
        ) : (
          <div className="ticket-table-wrapper">
            <table className="ticket-table graph-table">
              <thead>
                <tr><th>源实体</th><th>关系</th><th>目标实体</th><th>证据</th><th>来源</th></tr>
              </thead>
              <tbody>
                {filteredRelations.slice(0, 60).map((relation, index) => (
                  <tr key={`${relation.source_name}-${relation.relation_type}-${relation.target_name}-${index}`}>
                    <td>
                      <span className="graph-node-label" style={{ borderColor: GRAPH_TYPE_COLORS[relation.source_type] }}>
                        {relation.source_name}
                      </span>
                    </td>
                    <td>
                      <span className={"relation-tag" + (RISK_RELATION_TYPES.has(relation.relation_type) ? " risk" : "")}>
                        {relation.relation_type}
                      </span>
                    </td>
                    <td>
                      <span className="graph-node-label" style={{ borderColor: GRAPH_TYPE_COLORS[relation.target_type] }}>
                        {relation.target_name}
                      </span>
                    </td>
                    <td className="evidence-cell">{relation.evidence || "—"}</td>
                    <td className="mono">
                      {relation.filename === "tickets" ? "工单" : `${relation.filename} #${relation.chunk_index}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function GraphCanvas({ entities, relations, selectedEntity, onSelectEntity }: {
  entities: GraphEntity[];
  relations: GraphRelation[];
  selectedEntity: string;
  onSelectEntity: (name: string) => void;
}) {
  const columns = GRAPH_TYPE_ORDER.filter((type) => entities.some((entity) => entity.entity_type === type));
  const leftPad = 24;
  const topPad = 52;
  const colWidth = 204;
  const nodeWidth = 164;
  const nodeHeight = 40;
  const rowGap = 58;

  const positions = new Map<string, { x: number; y: number; type: string; col: number }>();
  let maxRows = 0;
  columns.forEach((type, colIndex) => {
    const columnEntities = entities.filter((entity) => entity.entity_type === type).slice(0, 8);
    maxRows = Math.max(maxRows, columnEntities.length);
    columnEntities.forEach((entity, rowIndex) => {
      positions.set(entity.name, {
        x: leftPad + colIndex * colWidth,
        y: topPad + rowIndex * rowGap,
        type,
        col: colIndex,
      });
    });
  });

  const width = leftPad * 2 + columns.length * colWidth - (colWidth - nodeWidth);
  const height = topPad + Math.max(1, maxRows) * rowGap + 16;
  const drawableRelations = relations.filter(
    (relation) => positions.has(relation.source_name) && positions.has(relation.target_name),
  );
  const showEdgeLabels = drawableRelations.length <= 16;

  const isDimmed = (name: string) =>
    Boolean(selectedEntity) &&
    name !== selectedEntity &&
    !drawableRelations.some(
      (relation) =>
        (relation.source_name === selectedEntity && relation.target_name === name) ||
        (relation.target_name === selectedEntity && relation.source_name === name),
    );

  return (
    <div className="graph-canvas-wrapper">
      <svg className="graph-canvas" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="实体关系图">
        {columns.map((type, colIndex) => (
          <text
            key={type}
            x={leftPad + colIndex * colWidth + nodeWidth / 2}
            y={26}
            textAnchor="middle"
            className="graph-column-title"
            fill={GRAPH_TYPE_COLORS[type]}
          >
            {GRAPH_TYPE_LABELS[type]}
          </text>
        ))}
        {drawableRelations.map((relation, index) => {
          const source = positions.get(relation.source_name)!;
          const target = positions.get(relation.target_name)!;
          const forward = target.col >= source.col;
          const sx = forward ? source.x + nodeWidth : source.x;
          const tx = forward ? target.x : target.x + nodeWidth;
          const sy = source.y + nodeHeight / 2;
          const ty = target.y + nodeHeight / 2;
          const bend = Math.min(90, Math.max(28, Math.abs(tx - sx) / 2));
          const path = `M ${sx} ${sy} C ${sx + (forward ? bend : -bend)} ${sy}, ${tx - (forward ? bend : -bend)} ${ty}, ${tx} ${ty}`;
          const isRisk = RISK_RELATION_TYPES.has(relation.relation_type);
          const involvesSelected =
            !selectedEntity ||
            relation.source_name === selectedEntity ||
            relation.target_name === selectedEntity;
          return (
            <g key={`${relation.source_name}-${relation.relation_type}-${relation.target_name}-${index}`}
              className={"graph-edge" + (isRisk ? " risk" : "") + (involvesSelected ? "" : " dimmed")}>
              <path d={path} fill="none" />
              {showEdgeLabels ? (
                <text x={(sx + tx) / 2} y={(sy + ty) / 2 - 6} textAnchor="middle" className="graph-edge-label">
                  {relation.relation_type}
                </text>
              ) : (
                <title>{`${relation.source_name} —${relation.relation_type}→ ${relation.target_name}`}</title>
              )}
            </g>
          );
        })}
        {entities.map((entity) => {
          const position = positions.get(entity.name);
          if (!position) return null;
          const label = entity.name.length > 10 ? `${entity.name.slice(0, 9)}…` : entity.name;
          return (
            <g
              key={`${entity.entity_type}-${entity.name}`}
              className={
                "graph-node" +
                (entity.name === selectedEntity ? " selected" : "") +
                (isDimmed(entity.name) ? " dimmed" : "")
              }
              transform={`translate(${position.x}, ${position.y})`}
              onClick={() => onSelectEntity(entity.name)}
            >
              <rect width={nodeWidth} height={nodeHeight} rx={10} style={{ stroke: GRAPH_TYPE_COLORS[position.type] }} />
              <circle cx={16} cy={nodeHeight / 2} r={4} fill={GRAPH_TYPE_COLORS[position.type]} />
              <text x={30} y={nodeHeight / 2 + 4}>{label}</text>
              <title>{`${entity.name}（${GRAPH_TYPE_LABELS[position.type]} · 提及 ${entity.mention_count} 次）`}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
