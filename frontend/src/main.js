import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router.js";
import "./styles/base.css";
import "./styles/ai-settings.css";
import "./styles/admin.css";
import "./styles/admin-skills.css";
import "./styles/home.css";
import "./styles/material-import.css";
import "./styles/search-materials.css";
import "./styles/workbench.css";
import "./styles/markdown.css";

createApp(App).use(router).mount("#app");
