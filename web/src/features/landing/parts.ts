import { fact, type Fact } from "./facts";
import { html, type Raw } from "./html";
import { posterFile, size, stillFile, STILLS, url, videoFile, type StillKey } from "./pictures";

/** What a render has cited so far, in the order the reader meets it. The sources list at the foot of the page reads it. */
export interface Cited {
  ids: string[];
}

/** The value of a fact, with a link to its source at the foot of the page. */
export function cite(cited: Cited, id: string): Raw {
  const one = fact(id);
  if (!cited.ids.includes(id)) cited.ids.push(id);
  return html`<span class="stat">${one.value}</span><a class="ref" href="#source-${id}" aria-label="Source"></a>`;
}

/** A fact's value and its claim as one phrase, cited. */
export function claim(cited: Cited, id: string): Raw {
  return html`${cite(cited, id)} ${fact(id).claim}`;
}

export function sourceItem(one: Fact): Raw {
  const label = one.source.kind === "survey" ? html`<a href="${one.source.url}" rel="noreferrer">${one.source.label}</a>` : html`${one.source.label}`;
  return html`<li id="source-${one.id}"><span class="stat">${one.value}</span> ${label}</li>`;
}

export function still(key: StillKey, className = ""): Raw {
  const narrow = STILLS[key].narrow;
  const [width, height] = size(stillFile(key, "light"));
  const source = (theme: "light" | "dark", small: boolean) =>
    html`<source media="${(theme === "dark" ? "(prefers-color-scheme: dark)" : "") + (small ? (theme === "dark" ? " and " : "") + "(max-width: 640px)" : "")}" srcset="${url(stillFile(key, theme, small))}">`;
  return html`<picture class="${className}">
    ${narrow ? source("dark", true) : ""}
    ${source("dark", false)}
    ${narrow ? source("light", true) : ""}
    <img src="${url(stillFile(key, "light"))}" alt="${STILLS[key].alt}" width="${width}" height="${height}" loading="lazy" decoding="async">
  </picture>`;
}

/** The hero loop. Each theme has its own video, and landing.ts plays the one that matches the system theme. Without the script the poster shows. */
export function loop(): Raw {
  const video = (theme: "light" | "dark") => {
    const [width, height] = size(videoFile(theme));
    return html`<video data-scheme="${theme}" src="${url(videoFile(theme))}" poster="${url(posterFile(theme))}" width="${width}" height="${height}" muted loop playsinline preload="none" aria-label="A brief typed into the chat, then the options it built and their checks filling in."></video>`;
  };
  return html`<div class="loop" data-loop>${video("light")}${video("dark")}</div>`;
}
