import {
  ENGAGEMENT_LABEL,
  ENGAGEMENT_TONE,
  formatKm,
  TRACK_LABEL,
  TRACK_TONE,
  type Tone,
} from "../../scenario/format";
import { useScenario } from "../../scenario/hooks";
import { findEngagement, missionCounts } from "../../scenario/select";
import { toneClass } from "../shell/toneClass";

/** Every threat: how far from the site, and which node is answering it. */
export function ThreatList() {
  const snapshot = useScenario().snapshot;
  const tracks = snapshot?.tracks ?? [];

  return (
    <section className="c-panel" aria-label="Threats">
      <div className="c-panel-head">
        <h2 className="c-panel-title">Threats</h2>
        {snapshot && (
          <span className="c-count">
            {missionCounts(snapshot).inside} inside area
          </span>
        )}
      </div>
      {!snapshot || tracks.length === 0 ? (
        <p className="c-empty">No threats detected.</p>
      ) : (
        <ul className="c-rows">
          {tracks.map((track) => {
            const engagement = track.engagement_id
              ? findEngagement(snapshot, track.engagement_id)
              : null;
            const inbound = track.status === "INBOUND";
            let detail: string;
            let tone: Tone;
            if (!inbound) {
              detail = TRACK_LABEL[track.status];
              tone = TRACK_TONE[track.status];
            } else if (engagement) {
              detail = `${engagement.node_id} · ${ENGAGEMENT_LABEL[engagement.status]}`;
              tone = ENGAGEMENT_TONE[engagement.status];
            } else {
              detail = track.inside_protected_area
                ? "Awaiting node"
                : "Outside area";
              tone = "neutral";
            }
            return (
              <li key={track.id} className="c-row">
                <span
                  className={`c-diamond${inbound ? "" : " is-resolved"}`}
                  aria-hidden="true"
                />
                <b className="c-row-id">{track.id}</b>
                <span className="c-row-num">
                  {inbound ? formatKm(track.site_distance_km) : "-"}
                </span>
                <span className={`c-row-status ${toneClass(tone)}`}>{detail}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
