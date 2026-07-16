const fs = require("node:fs");
const path = require("node:path");

exports.default = async function prepareDesktopResources(context) {
  const projectDir = context.packager.projectDir;
  const packageJson = JSON.parse(fs.readFileSync(path.join(projectDir, "package.json"), "utf8"));
  const outputPath = path.join(projectDir, "build", "desktop", "remote-package.json");
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify({
    name: packageJson.name,
    version: packageJson.version,
  }, null, 2)}\n`, "utf8");
};
