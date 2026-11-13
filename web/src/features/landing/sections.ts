import capture from "./capture.json";
import { fact, FACTS } from "./facts";
import { html, type Raw } from "./html";
import { cite, claim, loop, sourceItem, still, type Cited } from "./parts";
import { APP_HREF, APP_LABEL, DEMO_HREF, DEMO_LABEL, PITCH, PRODUCT_NAME, REPO_HREF, REPO_LABEL } from "./site";
import { STATES } from "./states";

const demo = html`<a class="button" href="${DEMO_HREF}" data-demo>${DEMO_LABEL}</a>`;
const open = html`<a class="textlink" href="${APP_HREF}" data-app>${APP_LABEL}</a>`;
const repo = html`<a class="textlink" href="${REPO_HREF}" rel="noreferrer" data-repo>${REPO_LABEL}</a>`;

export function bar(): Raw {
  return html`<header class="bar">
    <a class="mark" href="#top">${PRODUCT_NAME}</a>
    <nav aria-label="Page"><a href="#how">How it works</a><a href="#scorecard">Scorecard</a><a href="#trust">Trust</a><a href="#limits">Limits</a></nav>
    <span class="bar-actions">${open}${demo}</span>
  </header>`;
}

export function hero(cited: Cited): Raw {
  return html`<section class="hero" id="top">
    <h1>${PITCH}</h1>
    <p class="lede">Describe the part in your own words. ${cite(cited, "options")} ${fact("options").claim} Each one is checked against what you asked for, and each check shows its math and where every number came from.</p>
    <p class="actions">${demo}${open}</p>
    <div class="twice">
      <p><strong>You can say what the part must do, but not size it.</strong> The agent picks the dimensions. You read the verdicts in plain words.</p>
      <p><strong>You will check the numbers anyway.</strong> Every line of the scorecard opens to its formula and its source.</p>
    </div>
    <figure class="frame">
      ${loop()}
      <figcaption>Recorded from the app, with the waits cut short. The brief was: &ldquo;${capture.brief}&rdquo;</figcaption>
    </figure>
  </section>`;
}

const STEPS = [
  ["Brief", "Say what you need. Add images, drawings, documents or CAD files if you have them. The agent reads them for intent and dimensions."],
  ["Variants", "The options are built at once, in a sandbox with no network. Nothing waits on you first."],
  ["Checks", "Each option gets a scorecard. A target you stated waits for one click from you, and then the same results are judged."],
  ["Change and download", "Pick an option and ask for a change in the chat. It is rebuilt and checked again. Download it as STEP, STL or 3MF."],
] as const;

export function how(cited: Cited): Raw {
  return html`<section class="sheet" id="how">
    <h2>How it works</h2>
    <div class="body">
      <ol class="steps">${STEPS.map(([name, text]) => html`<li><h3>${name}</h3><p>${text}</p></li>`)}</ol>
      <p class="aside">${cite(cited, "checks")} ${fact("checks").claim}</p>
      ${still("options", "shot")}
    </div>
  </section>`;
}

export function scorecard(cited: Cited): Raw {
  return html`<section class="sheet wide" id="scorecard">
    <h2>The scorecard</h2>
    <div class="body">
      <p class="lead">Every option comes with one. It holds what each check measured, the target you confirmed, the verdict, and the formula and source behind it. Open any line to read them.</p>
      <div class="board">
        <figure class="plate">${still("scorecard")}<figcaption>One option's scorecard, opened on two lines to show the math.</figcaption></figure>
        <dl class="states">${STATES.map((one) => html`<div class="state" data-state="${one.id}"><dt>${one.name}</dt><dd>${one.means}</dd></div>`)}</dl>
      </div>
      <figure class="plate small">${still("waiting")}<figcaption>The same option before the person confirmed. The measure sits beside the target, and no verdict is given yet.</figcaption></figure>
      <p class="aside">${cite(cited, "materials")} ${fact("materials").claim}</p>
    </div>
  </section>`;
}

export function trust(cited: Cited): Raw {
  return html`<section class="sheet" id="trust">
    <h2>Why you can trust it</h2>
    <div class="body">
      <div class="reasons">
        <div><h3>The agent proposes. Checks decide.</h3><p>The agent builds the options and chooses a material. Whether an option passes is the verdict of a check, and only of a check.</p></div>
        <div><h3>The agent cannot change a check.</h3><p>A check is fixed code. The agent cannot edit it, its inputs, or the tables it reads. Its only move is to change the design and run the checks again.</p></div>
        <div><h3>Every number has a cited source.</h3><p>Checks read strengths, densities, fastener sizes and tolerances from tables by exact key, never from search or from the model. When a value is missing, the agent reads it from a public page, the server fetches the page and finds the quote on it, and the scorecard labels the result researched.</p></div>
        <div><h3>You confirm the targets.</h3><p>A verdict rests only on a target you confirmed. A number the agent fills in itself is an assumption, shown apart, with no verdict.</p></div>
      </div>
      <h3 class="subhead">Why this matters to the people who check</h3>
      <ul class="evidence">
        <li>${claim(cited, "verify-by-hand")}</li>
        <li>${claim(cited, "back-of-envelope")}</li>
        <li>${claim(cited, "transparency")}</li>
        <li>${claim(cited, "fea-with")} ${claim(cited, "fea-without")}</li>
      </ul>
      <p class="aside">Engineers already check AI by hand. The scorecard puts the checking where they can see it.</p>
    </div>
  </section>`;
}

const LIMITS = [
  ["Freeform shapes", "Sweeps, lofts and sculpted surfaces are not reliable yet. The agent says so, offers the closest prismatic version, and marks the shape requirement unverified."],
  ["Strength across print layers", "A printed part is usually weaker across its layers than along them. The checks do not model print direction, so a stress result on a printed part does not account for it."],
  ["Print time and cost", "No slicer runs, so an option has no print time, filament weight or cost."],
  ["Sending to Onshape", "Not available. Download STEP, STL or 3MF and import it."],
] as const;

export function limits(): Raw {
  return html`<section class="sheet" id="limits">
    <h2>What it does not do yet</h2>
    <div class="body">
      <p class="lead">A design should never look more checked than it is. These are the edges today.</p>
      <dl class="limits">${LIMITS.map(([name, text]) => html`<div><dt>${name}</dt><dd>${text}</dd></div>`)}</dl>
    </div>
  </section>`;
}

export function ways(): Raw {
  return html`<section class="sheet" id="ways">
    <h2>Two ways in</h2>
    <div class="body two">
      <div><h3>The web app</h3><p>Chat with the agent and see each option in 3D beside its scorecard. Ask for changes in your own words.</p><p>${open}</p></div>
      <div><h3>Your own MCP client</h3><p>The product is an MCP server. Claude Code or any MCP client that can sign in gets the same tools and the same checks. The checks run on the server, so your client can do the engineering and cannot grade its own work.</p><p>${repo}</p></div>
    </div>
  </section>`;
}

export function next(): Raw {
  return html`<section class="next" id="next">
    <h2>Bring a part you would design next.</h2>
    <p class="actions">${demo}${open}${repo}</p>
  </section>`;
}

export function foot(cited: Cited): Raw {
  const rest = FACTS.filter((one) => !cited.ids.includes(one.id));
  const used = cited.ids.map((id) => fact(id));
  return html`<footer class="foot">
    <h2>Sources for the numbers on this page</h2>
    <ol class="sources">${[...used, ...rest].map(sourceItem)}</ol>
    <p>${PRODUCT_NAME} is a working name. This page is static. It sets no cookies and loads nothing from other sites.</p>
  </footer>`;
}
