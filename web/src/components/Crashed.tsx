import { Component, type ReactNode } from "react";
import { Notice } from "./Gate";

/** A page that throws shows what happened, not a blank screen. */
export class Crashed extends Component<{ children: ReactNode }, { error: Error | null }> {
  override state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error): { error: Error } {
    return { error };
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <Notice title="Something broke">
        <p className="font-mono text-xs">{error.message}</p>
        <p className="mt-2">Reload the page. If it breaks again, tell whoever runs this server.</p>
      </Notice>
    );
  }
}
