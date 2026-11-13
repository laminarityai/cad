import { html, type Raw } from "./html";
import type { Cited } from "./parts";
import { bar, foot, hero, how, limits, next, scorecard, trust, ways } from "./sections";
import { PITCH, PRODUCT_NAME } from "./site";

export const TITLE = `${PRODUCT_NAME}: ${PITCH}`;
export const DESCRIPTION =
  "An AI engineer that turns what you ask for into several options, and checks each one with code the agent cannot change. Every number cites its source.";

/** The page's body. Sections that cite a fact come in reading order, so the sources list numbers them as the reader meets them. */
export function body(): Raw {
  const cited: Cited = { ids: [] };
  const top = bar();
  const parts = [hero(cited), how(cited), scorecard(cited), trust(cited), limits(), ways(), next()];
  return html`${top}<main>${parts}</main>${foot(cited)}`;
}
