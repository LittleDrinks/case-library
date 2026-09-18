import vue from "eslint-plugin-vue";

export default [
  ...vue.configs["flat/essential"],
  {
    files: ["src/**/*.{js,vue}"],
    rules: {
      complexity: ["error", 15],
    },
  },
];
