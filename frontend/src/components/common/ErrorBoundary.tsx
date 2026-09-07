import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** What failed, named for the operator. */
  label?: string;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Stops one broken panel from blanking the whole console.
 *
 * React unmounts the entire tree on an uncaught render error, which during a
 * demo means a white screen and no way back. Wrapping the panels separately
 * keeps the video and the mission state on screen even if a readout throws
 * on unexpected telemetry.
 *
 * Class component because error boundaries have no hook equivalent.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[${this.props.label ?? "ui"}] render failed`, error, info);
  }

  private retry = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback;

    return (
      <div className="boundary" role="alert">
        <div className="boundary-title">
          {this.props.label ?? "Panel"} unavailable
        </div>
        <div className="boundary-detail">{error.message}</div>
        <button type="button" className="ghost-button" onClick={this.retry}>
          Retry
        </button>
      </div>
    );
  }
}
