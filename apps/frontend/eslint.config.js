import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist", "build", "coverage", "node_modules", "*.min.js"],
  },
  ...tseslint.configs.recommended,
);
