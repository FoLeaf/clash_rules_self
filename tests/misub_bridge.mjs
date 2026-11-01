// Run the real MiSub renderer from a separate checkout; no client override.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const source = process.env.MISUB_SOURCE;
if (!source) throw new Error("Set MISUB_SOURCE to a MiSub checkout with production dependencies installed");
const require = createRequire(path.join(source, "package.json"));
const yaml = require("js-yaml");
const { renderClashFromIniTemplate } = await import(pathToFileURL(path.join(source,
  "functions/modules/subscription/template-pipeline.js")).href);
const request = JSON.parse(fs.readFileSync(0, "utf8"));
const output = renderClashFromIniTemplate(request.template, {
  ...request.options, ruleLevel: "none", isMeta: true,
});
process.stdout.write(JSON.stringify(yaml.load(output)));
