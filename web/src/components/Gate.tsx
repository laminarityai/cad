import type { ReactNode } from "react";
import { signInUrl } from "@/api/confirmation";
import { Loading } from "@/components/ui/busy";
import { Button } from "@/components/ui/button";
import type { Resource } from "@/state/resource";

export function Notice({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className="mx-auto my-16 max-w-md border border-border bg-panel p-6" role="status">
      <h1 className="font-mono text-sm font-semibold uppercase tracking-wider">{title}</h1>
      {children ? <div className="mt-3 text-ink-2">{children}</div> : null}
    </section>
  );
}

export function SignedOutView() {
  return (
    <Notice title="Signed out">
      <p>Sign in to see your projects, variants and scorecards.</p>
      <Button render={<a href={signInUrl()} />} variant="accent" className="mt-4">
        Sign in
      </Button>
    </Notice>
  );
}

/** Shows what a request is doing when it is not done: loading, signed out, not found, or failed. */
export function Gate<T>({ resource, children }: { resource: Resource<T>; children: (data: T) => ReactNode }) {
  switch (resource.status) {
    case "loading":
      return <Loading label="Loading" size="small" className="p-6" />;
    case "signed_out":
      return <SignedOutView />;
    case "not_found":
      return (
        <Notice title="Not found">
          <p>There is nothing here in your account.</p>
        </Notice>
      );
    case "error":
      return (
        <Notice title="Something went wrong">
          <p>{resource.message}</p>
        </Notice>
      );
    case "ok":
      return <>{children(resource.data)}</>;
  }
}
