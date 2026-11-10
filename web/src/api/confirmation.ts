/** Where a person answers what waits on them. The signed-in confirmation page is a server page
 * (`GET /projects/<pid>/confirm`) that answers the form itself, so the app only links to it. */
export function confirmUrl(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}/confirm`;
}

/** The page shows its own sign-in when the request carries no session. */
export function signInUrl(): string {
  return confirmUrl("sign-in");
}
