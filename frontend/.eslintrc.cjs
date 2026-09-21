/* ESLint 8 (config clásica: es la que empareja con el plugin de hooks fijado
   en package.json). Reglas mínimas — el gate fuerte del frontend es `tsc -b`
   en modo strict, no el linter. */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
  ],
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: "latest", sourceType: "module" },
  plugins: ["@typescript-eslint", "react-hooks"],
  rules: {
    ...require("eslint-plugin-react-hooks").configs.recommended.rules,
    // Recharts tipa sus render props como `any`; aislarlos con tipos propios
    // seria mas ruido que senal en un componente de presentacion.
    "@typescript-eslint/no-explicit-any": "warn",
  },
  ignorePatterns: ["dist", "node_modules", "*.cjs"],
};
