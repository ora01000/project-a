import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ThemeProvider } from "./context/ThemeContext";
import { installAuthFetchInterceptor } from "./utils/api";
import "./index.css";
import "./styles/theme-light.css";
import "./styles/theme-homebrew.css";
import "./styles/theme-monochrome.css";

installAuthFetchInterceptor();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
