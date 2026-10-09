const path = require("path");

module.exports = {
  target: "atom-shell",
  directories: {
    output: "dist",
  },
  mac: {
    category: "public.app-category.productivity",
    target: ["dmg"],
  },
  win: {
    target: "nsis",
  },
  linux: {
    target: "deb",
  },
};
