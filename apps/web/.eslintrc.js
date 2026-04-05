/** @type {import("eslint").Linter.Config} */
module.exports = {
  root: true,
  extends: ["@dental/eslint-config", "next/core-web-vitals"],
  parserOptions: {
    project: true,
    tsconfigRootDir: __dirname,
  },
};
