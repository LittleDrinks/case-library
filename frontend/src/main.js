import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router.js";
import "./styles/base.css";
import "./styles/ai-settings.css";
import "./styles/admin.css";
import "./styles/case-detail.css";
import "./styles/home.css";
import "./styles/material-import.css";
import "./styles/prototype-workbench-ai.css";
import "./styles/search-materials.css";
import "./styles/workbench.css";

createApp(App).use(router).mount("#app");
