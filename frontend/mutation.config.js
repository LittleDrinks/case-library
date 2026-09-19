import { mergeConfig } from "vite";
import base from "./vite.config.js";
import { mutationReporter } from "./tests/tooling/mutation.js";

export default mergeConfig(base, {
  test: { reporters: [mutationReporter] },
});
