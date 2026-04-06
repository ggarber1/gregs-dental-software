/** @type {import("eslint").Linter.Config} */
module.exports = {
  root: true,
  extends: ["@dental/eslint-config"],
  parserOptions: {
    project: true,
    tsconfigRootDir: __dirname,
  },
};
