/** The states a scorecard names, in the app's own words and colours (web/src/index.css). */
export interface State {
  id: "pass" | "fail" | "wait" | "res" | "unk" | "none" | "assumed";
  name: string;
  means: string;
}

export const STATES: readonly State[] = [
  { id: "pass", name: "Pass", means: "A check measured the option, and it meets a target you confirmed." },
  { id: "fail", name: "Fail", means: "A check measured the option, and it misses a target you confirmed. The line shows the measure." },
  { id: "wait", name: "Waiting for you", means: "You stated a target and have not confirmed it yet. The line shows the measure beside your target and gives no verdict." },
  { id: "res", name: "Researched", means: "The table lacked a value. The agent read it from a public page, and the server fetched that page and found the quote on it. The verdict is labelled and counted apart." },
  { id: "unk", name: "Unknown", means: "A check could not decide, because a value is missing or a feature is out of its reach. It is never shown as a pass." },
  { id: "none", name: "No test yet", means: "No check decides this requirement. Every scorecard lists these, so an option never looks more checked than it is." },
  { id: "assumed", name: "Assumed by the agent", means: "A number the agent filled in so it could build, such as a load you did not state. It is shown apart and never gets a verdict." },
];
