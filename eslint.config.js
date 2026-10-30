import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["frontend/**/*.js"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: globals.browser,
    },
    rules: {
      // Пользовательские данные выводятся только через textContent (защита от XSS)
      "no-restricted-properties": [
        "error",
        { property: "innerHTML", message: "Используйте h()/textContent" },
        { property: "outerHTML", message: "Используйте h()/textContent" },
      ],
      "no-restricted-syntax": [
        "error",
        { selector: "CallExpression[callee.property.name='insertAdjacentHTML']", message: "Используйте h()" },
        { selector: "CallExpression[callee.name='eval']", message: "eval запрещён" },
      ],
      "no-alert": "error",
      eqeqeq: ["error", "always"],
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "prefer-const": "error",
    },
  },
];
