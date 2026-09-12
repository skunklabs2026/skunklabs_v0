import { NODE_LABEL, NODE_TONE } from "../../scenario/format";
import { useScenario, useScenarioCommands } from "../../scenario/hooks";
import { displayedNodeId, findEngagement } from "../../scenario/select";
import { toneClass } from "../shell/toneClass";

/**
 * Every node in the network, and which one this view shows.
 *
 * By default it follows the response the operator is deciding on; picking a
 * node pins it until "follow" is ticked again. Each tab carries the node's
 * state colour and how many interceptors it still holds, so the whole network
 * is readable without leaving the view.
 */
export function NodeTabs() {
  const state = useScenario();
  const { selectNode } = useScenarioCommands();
  const { snapshot } = state;
  if (!snapshot) return null;
  const shown = displayedNodeId(state);
  const following = state.selectedNodeId === null;

  return (
    <div className="c-node-picker">
      <div className="c-node-tabs" role="tablist" aria-label="Defense nodes">
        {snapshot.nodes.map((node) => {
          const engagement = node.engagement_id
            ? findEngagement(snapshot, node.engagement_id)
            : null;
          const label = `${node.id}, ${NODE_LABEL[node.state]}, ${node.inventory} of ${node.inventory_capacity} interceptors${
            engagement ? `, answering ${engagement.track_id}` : ""
          }`;
          return (
            <button
              key={node.id}
              type="button"
              role="tab"
              className="c-node-tab"
              aria-selected={node.id === shown}
              aria-label={label}
              title={label}
              onClick={() => selectNode(node.id)}
            >
              <span
                className={`c-node-dot-sm ${toneClass(NODE_TONE[node.state])}`}
                aria-hidden="true"
              />
              <span className="c-node-tab-id">{node.id.replace("NODE-", "")}</span>
              <span className="c-node-tab-count">{node.inventory}</span>
            </button>
          );
        })}
      </div>
      <label className="c-follow">
        <input
          type="checkbox"
          checked={following}
          onChange={(event) => selectNode(event.target.checked ? null : shown)}
        />
        Follow current decision
      </label>
    </div>
  );
}
