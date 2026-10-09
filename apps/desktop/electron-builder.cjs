const path = require("path");

module.exports = {
  appId: "com.yjarvis.desktop",
  productName: "YJarvis",
  electronVersion: require("electron/package.json").version,
  directories: { output: "../../release" },
  files: ["dist/**/*", "electron/**/*", "package.json"],
  extraResources: [
    { from: "../../scripts/startup.cjs", to: "startup.cjs" },
    { from: "../../build/agent/jarvis-agent", to: "agent" }
  ],
  asar: true,
  npmRebuild: false,
  publish: null,
  win: { target: [{ target: "nsis", arch: ["x64"] }], signAndEditExecutable: false },
  nsis: {
    oneClick: false,
    perMachine: false,
    allowElevation: false,
    allowToChangeInstallationDirectory: true,
    createDesktopShortcut: true,
    createStartMenuShortcut: true,
    deleteAppDataOnUninstall: false,
    runAfterFinish: false,
    artifactName: "YJarvis-${version}-windows-${arch}-setup.${ext}"
  },
  mac: { target: ["dmg"], category: "public.app-category.productivity" }
};
