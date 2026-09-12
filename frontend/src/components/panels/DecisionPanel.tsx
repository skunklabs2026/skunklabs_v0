import type {
  DefenseNode,
  Engagement,
  ScenarioSnapshot,
} from "../../scenario/contract";
import {
  ENGAGEMENT_LABEL,
  ENGAGEMENT_TONE,
  formatHeading,
  formatKm,
  plural,
} from "../../scenario/format";
import { distanceKm } from "../../scenario/geo";
import { useScenario, useScenarioCommands } from "../../scenario/hooks";
import {
  currentDecision,
  findEngagement,
  findNode,
  findTrack,
  interceptorCount,
  misalignment,
} from "../../scenario/select";
import { NodeStatePill } from "../shell/Tone";
import { toneClass } from "../shell/toneClass";

/** The assigned node, plus every free node the operator could use instead. */
function nodeChoices(
  snapshot: ScenarioSnapshot,
  assigned: DefenseNode,
  track: { latitude: number; longitude: number },
): { node: DefenseNode; km: number }[] {
  return snapshot.nodes
    .filter(
      (node) =>
        node.id === assigned.id ||
        (node.engagement_id === null && node.inventory > 0),
    )
    .map((node) => ({ node, km: distanceKm(node, track) }))
    .sort((a, b) => a.km - b.km);
}

function Decision({
  snapshot,
  decision,
}: {
  snapshot: ScenarioSnapshot;
  decision: Engagement;
}) {
  const state = useScenario();
  const { pending, connection } = state;
  const { authorize, decline, reassign, setInterceptorRequest } =
    useScenarioCommands();
  const node = findNode(snapshot, decision.node_id);
  const track = findTrack(snapshot, decision.track_id);
  if (!node || !track) return null;

  const count = interceptorCount(state, decision, node);
  const awaiting = decision.status === "AWAITING_AUTHORIZATION";
  const free = connection === "online" && pending === null;
  const queue = snapshot.decision_queue;
  const choices = nodeChoices(snapshot, node, track);
  const next = queue
    .slice(1)
    .map((id) => findEngagement(snapshot, id))
    .filter((e): e is Engagement => e !== null);

  return (
    <>
      <p className="c-decision-count">Response 1 of {queue.length}</p>
      <div className="c-decision-title">
        <span className="c-decision-id">{decision.id}</span>
        <span>
          <b>{node.id}</b> to <b className="c-threat">{track.id}</b>
        </span>
      </div>

      <dl className="c-kv">
        <dt>Node</dt>
        <dd>
          <NodeStatePill state={node.state} />
        </dd>
        <dt>Threat to {snapshot.site.id}</dt>
        <dd>{formatKm(track.site_distance_km)}</dd>
        <dt>From {node.id}</dt>
        <dd>
          {formatKm(decision.range_km)}
          <small>{formatHeading(decision.bearing_deg, 0)}</small>
        </dd>
      </dl>

      <div className="c-field">
        <label className="c-label" htmlFor="c-node-choice">
          Launching node
        </label>
        <select
          id="c-node-choice"
          className="c-select c-select-wide"
          value={node.id}
          disabled={!free || !(awaiting || decision.status === "PROPOSED")}
          onChange={(event) => reassign(decision.id, event.target.value)}
        >
          {choices.map(({ node: choice, km }) => (
            <option key={choice.id} value={choice.id}>
              {choice.id} · {formatKm(km)} · {choice.inventory} ready
            </option>
          ))}
        </select>
      </div>

      <div className="c-stepper-row">
        <span className="c-label">Interceptors</span>
        <div className="c-stepper" role="group" aria-label="Interceptors to commit">
          <button
            type="button"
            aria-label="Fewer interceptors"
            disabled={!free || count <= 1}
            onClick={() => setInterceptorRequest(decision.id, count - 1)}
          >
            −
          </button>
          <output aria-label="Interceptors selected">{count}</output>
          <button
            type="button"
            aria-label="More interceptors"
            disabled={!free || count >= node.inventory}
            onClick={() => setInterceptorRequest(decision.id, count + 1)}
          >
            +
          </button>
        </div>
        <span className="c-label">
          Proposed {decision.proposed_interceptors} · {node.inventory} at {node.id}
        </span>
      </div>

      <div className="c-decision-actions">
        <button
          type="button"
          className="c-btn c-btn-primary c-btn-authorize"
          disabled={!awaiting || !free || node.inventory < 1}
          onClick={() => authorize(decision.id, count)}
        >
          {pending === "authorize" ? "Authorizing" : "Authorize simulation"}
        </button>
        <button
          type="button"
          className="c-btn c-btn-quiet"
          disabled={!free}
          onClick={() => decline(decision.id)}
        >
          {pending === "decline" ? "Declining" : "Decline"}
        </button>
      </div>
      <p className="c-hint">
        {awaiting
          ? `Launches ${plural(count, "simulated interceptor")} from ${node.id} at ${track.id}.`
          : `${node.id} orienting, ${misalignment(node).toFixed(1)}° to go before it can be authorized.`}
      </p>

      {next.length > 0 && (
        <div className="c-queue">
          <span className="c-label">Up next</span>
          <ol>
            {next.map((engagement) => (
              <li key={engagement.id}>
                <span className="c-decision-id">{engagement.id}</span>
                <span>
                  {engagement.node_id} → {engagement.track_id}
                </span>
                <span
                  className={`c-int-status ${toneClass(ENGAGEMENT_TONE[engagement.status])}`}
                >
                  {ENGAGEMENT_LABEL[engagement.status]}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </>
  );
}

/**
 * The operator's decision flow. When threats enter the protected area, the
 * nearest nodes activate together and the backend queues one proposed response
 * per threat. This panel presents them one at a time: which node launches
 * (changeable), how many interceptors, then authorize or decline.
 */
export function DecisionPanel() {
  const { snapshot, error } = useScenario();
  const decision = snapshot ? currentDecision(snapshot) : null;
  const pendingCount = snapshot?.decision_queue.length ?? 0;

  const empty =
    snapshot?.state === "RUNNING"
      ? "No decisions pending. Nodes activate when threats enter the protected area."
      : snapshot?.state === "COMPLETE"
        ? "No decisions pending. Mission complete."
        : "Responses are proposed when threats enter the protected area.";

  return (
    <section className="c-panel c-decision" aria-label="Operator decision">
      <div className="c-panel-head">
        <h2 className="c-panel-title">Operator decision</h2>
        <span
          className={`c-chip${pendingCount > 0 ? ` is-lit ${toneClass("ready")}` : ""}`}
        >
          {pendingCount > 0 ? `${pendingCount} pending` : "Simulation only"}
        </span>
      </div>
      {snapshot && decision ? (
        <Decision snapshot={snapshot} decision={decision} />
      ) : (
        <p className="c-empty">{empty}</p>
      )}
      {error && (
        <p className="c-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
