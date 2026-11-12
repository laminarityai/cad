import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

const CLIENT = "Call the server through request() or openStream() in src/api/client.ts: it is the one place that calls fetch and spells a /v1 path.";
const WIDGET = "Use the wrapper in src/components/ui/: it is the one place that imports the primitive library (@base-ui/react) or sonner.";
const LOAD = "Load a GET through useResource or useResources in src/state/resource.ts, not by calling the API in an effect.";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/api/types.ts"] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: { parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-unused-vars": ["error", { varsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/api/**", "src/test/**", "src/**/*.test.{ts,tsx}"],
    rules: {
      "no-restricted-globals": ["error", ...["fetch", "EventSource", "XMLHttpRequest"].map((name) => ({ name, message: CLIENT }))],
      "no-restricted-properties": ["error", ...["window", "globalThis", "self"].map((object) => ({ object, property: "fetch", message: CLIENT }))],
      "no-restricted-syntax": [
        "error",
        { selector: "Literal[value=/\\/v1\\//]", message: CLIENT },
        { selector: "TemplateElement[value.raw=/\\/v1\\//]", message: CLIENT },
        { selector: "CallExpression[callee.name='useEffect'] CallExpression[callee.object.name=/^(api|chat)$/][callee.property.name=/^(?!follow$)/]", message: LOAD },
      ],
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/components/ui/**"],
    rules: {
      "no-restricted-imports": ["error", { patterns: [{ group: ["@base-ui/*", "sonner"], message: WIDGET }] }],
    },
  },
  { files: ["*.config.js", "*.config.ts"], ...tseslint.configs.disableTypeChecked },
);
