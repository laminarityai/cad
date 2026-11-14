import manifest from "./assets/manifest.json";

/*
 * Every picture on the page is a capture of the product, written by tools/landing_capture.py into
 * assets/. The capture writes manifest.json too, so the page knows each file's size. A retake
 * replaces the files and nothing here changes.
 */

export type Size = readonly [number, number];
export const SIZES: Readonly<Record<string, Size>> = Object.fromEntries(
  Object.entries(manifest).map(([file, [width = 0, height = 0]]) => [file, [width, height] as const]),
);
export const ASSET_DIR = "/src/features/landing/assets";

export const STILLS = {
  options: {
    alt: "The workspace after a brief: the chat on one side, the option on screen in a 3D viewer, and its checks on the other.",
    narrow: true,
  },
  waiting: {
    alt: "The scorecard of one option before the person confirms their targets. Each target shows the measure beside it and the words waiting for you, no verdict yet.",
    narrow: false,
  },
  scorecard: {
    alt: "The scorecard of one option after the person confirmed their targets. Each line has a verdict, a value, and an opened line shows its formula and its source.",
    narrow: false,
  },
} as const;

export type StillKey = keyof typeof STILLS;
export type Theme = "light" | "dark";

export const VIDEO = { name: "hero", ext: "webm", poster: "hero-poster" } as const;

export const stillFile = (key: StillKey, theme: Theme, narrow = false): string => `${key}-${theme}${narrow ? "-narrow" : ""}.webp`;
export const videoFile = (theme: Theme): string => `${VIDEO.name}-${theme}.${VIDEO.ext}`;
export const posterFile = (theme: Theme): string => `${VIDEO.poster}-${theme}.webp`;

/** Every file the page references, for the test that each one exists. */
export function allFiles(): string[] {
  const themes: Theme[] = ["light", "dark"];
  return themes.flatMap((theme) => [
    videoFile(theme),
    posterFile(theme),
    ...(Object.keys(STILLS) as StillKey[]).flatMap((key) => [stillFile(key, theme), ...(STILLS[key].narrow ? [stillFile(key, theme, true)] : [])]),
  ]);
}

export function size(file: string): Size {
  const found = SIZES[file];
  if (!found) throw new Error(`landing: ${file} is not in assets/manifest.json`);
  return found;
}

export const url = (file: string): string => `${ASSET_DIR}/${file}`;
