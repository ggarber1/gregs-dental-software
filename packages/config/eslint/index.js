/** @type {import("eslint").Linter.Config} */
module.exports = {
  parser: "@typescript-eslint/parser",
  plugins: ["@typescript-eslint", "react", "react-hooks"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended-type-checked",
    "plugin:react/recommended",
    "plugin:react-hooks/recommended",
  ],
  rules: {
    // Enforce idempotency-friendly patterns
    "@typescript-eslint/no-floating-promises": "error",
    "@typescript-eslint/no-misused-promises": "error",
    // Disallow implicit any
    "@typescript-eslint/no-explicit-any": "warn",
    // React
    "react/react-in-jsx-scope": "off",
    "react/prop-types": "off",
  },
  settings: {
    react: {
      version: "detect",
    },
  },
};
