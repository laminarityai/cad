/** Whether the hero video for `scheme` should play: it matches the system theme, and the person has not asked for less motion. */
export function shouldPlay(scheme: "light" | "dark", systemIsDark: boolean, reducedMotion: boolean): boolean {
  return !reducedMotion && (scheme === "dark") === systemIsDark;
}

export function follow(root: ParentNode, media: (query: string) => MediaQueryList): void {
  const dark = media("(prefers-color-scheme: dark)");
  const reduced = media("(prefers-reduced-motion: reduce)");
  const videos = [...root.querySelectorAll<HTMLVideoElement>("[data-loop] video")];
  const apply = () => {
    for (const video of videos) {
      if (shouldPlay(video.dataset.scheme === "dark" ? "dark" : "light", dark.matches, reduced.matches)) {
        video.preload = "auto";
        video.play().catch(() => undefined);
      } else {
        video.pause();
      }
    }
  };
  dark.addEventListener("change", apply);
  reduced.addEventListener("change", apply);
  apply();
}
