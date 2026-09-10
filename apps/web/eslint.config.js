import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // 只启用经典的两条 Hook 规则。eslint-plugin-react-hooks 7.x 的 recommended 还包含
      // React Compiler 校验规则（refs、set-state-in-effect、purity 等）；本项目未启用
      // React Compiler，且 `refs` 规则会把携带 ref 的 props 对象的所有属性读取误报为
      // “渲染期访问 ref”，因此不作为门禁。
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
);
