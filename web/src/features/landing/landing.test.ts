import { readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";
import capture from "./capture.json";
import { fact, FACTS, numbersIn } from "./facts";
import { allFiles, SIZES } from "./pictures";
import { body } from "./render";
import { APP_HREF, DEMO_HREF, DEMO_LABEL, REPO_HREF } from "./site";
import { shouldPlay } from "./loop";

const page = body().text;
const words = (html: string) => html.replace(/<[^>]*>/g, " ").replace(/&[a-z]+;/g, " ");
const text = words(page);

describe("the landing page numbers", () => {
  it("writes a number only in the section that cites the fact or shows the brief it comes from", () => {
    const sections = page.split(/(?=<section|<footer)/);
    const found = sections.flatMap((section) => {
      const ids = [...section.matchAll(/(?:href="#|id=")source-([\w-]+)"/g)].map((one) => String(one[1]));
      const owned = ids.flatMap((id) => [fact(id).value, fact(id).claim, fact(id).source.label]);
      if (section.includes(capture.brief)) owned.push(capture.brief);
      const allowed = new Set(owned.flatMap(numbersIn));
      return numbersIn(words(section)).filter((one) => !allowed.has(one));
    });
    expect(found).toEqual([]);
  });

  it("gives every fact a source", () => {
    for (const one of FACTS) {
      expect(one.source.label.length).toBeGreaterThan(10);
      if (one.source.kind !== "repo") expect(one.source.url).toMatch(/^https:\/\//);
    }
  });

  it("links each cited number to a source that is on the page", () => {
    for (const [, id] of page.matchAll(/href="#source-([\w-]+)"/g)) {
      expect(page).toContain(`id="source-${String(id)}"`);
      expect(fact(String(id))).toBeDefined();
    }
  });

  it("lists every fact in the sources", () => {
    for (const one of FACTS) expect(page).toContain(`id="source-${one.id}"`);
  });
});

describe("the landing page words", () => {
  it("shows the demo button as the main one, in the hero and at the end", () => {
    const buttons = [...page.matchAll(/<a class="button" href="([^"]*)" data-demo>([^<]*)<\/a>/g)];
    expect(buttons.length).toBeGreaterThanOrEqual(3);
    for (const [, href, label] of buttons) {
      expect(label).toBe(DEMO_LABEL);
      expect(href).toBe(DEMO_HREF.replace(/&/g, "&amp;"));
    }
    expect(DEMO_LABEL).toBe("Request a demo");
  });

  it("keeps the placeholder address the only one", () => {
    expect(page.match(/[\w.+-]+@[\w-]+\.[\w.]+/g)).toEqual(Array(page.match(/@/g)?.length).fill("demo@example.com"));
  });

  it("links the app and the repository", () => {
    expect(page).toContain(`href="${APP_HREF}"`);
    expect(page).toContain(`href="${REPO_HREF}"`);
    expect(APP_HREF).toBe("/app");
  });

  it("uses glossary words and promises nothing shelved", () => {
    expect(text).not.toMatch(/\bprompt/i);
    expect(text).not.toMatch(/waitlist|request access/i);
    const before = page.slice(0, page.indexOf('id="limits"'));
    expect(before).not.toMatch(/onshape|slicer|printab/i);
  });

  it("names Onshape only under what it does not do", () => {
    const start = page.indexOf('id="limits"');
    const end = page.indexOf('id="ways"');
    expect(page.slice(start, end)).toMatch(/Onshape/);
    expect(page.slice(end)).not.toMatch(/Onshape/);
  });

  it("names every scorecard state in plain words", () => {
    for (const name of ["Pass", "Fail", "Waiting for you", "Researched", "Agent-written check", "Unknown", "No test yet", "Assumed by the agent"]) {
      expect(page).toContain(`<dt>${name}</dt>`);
    }
  });

  it("holds no local path and no other site's address but the cited ones", () => {
    expect(page).not.toMatch(/\/Users\/|\/home\/|C:\\/);
    const hosts = new Set([...page.matchAll(/https?:\/\/([^/"'\s]+)/g)].map((one) => one[1]));
    const allowed = new Set(["github.com", "www.omnicalculator.com", "iot-analytics.com", "arxiv.org"]);
    for (const host of hosts) expect(allowed.has(host as string)).toBe(true);
  });

  it("loads nothing from another site", () => {
    expect(page).not.toMatch(/<(script|link|img|source|video|iframe)[^>]*(src|href|srcset)="https?:/);
  });
});

describe("the landing page pictures", () => {
  it("has every picture in the manifest and on disk", () => {
    const dir = `${process.cwd()}/src/features/landing/assets`;
    const files = new Set(readdirSync(dir));
    for (const file of allFiles()) {
      expect(SIZES[file], file).toBeDefined();
      expect(files.has(file), file).toBe(true);
    }
  });
});

describe("the hero loop", () => {
  it("plays the video that matches the theme, and none under reduced motion", () => {
    expect(shouldPlay("dark", true, false)).toBe(true);
    expect(shouldPlay("light", true, false)).toBe(false);
    expect(shouldPlay("light", false, false)).toBe(true);
    expect(shouldPlay("dark", true, true)).toBe(false);
  });
});
