/**
 * Application entry point — mounts the root <App /> component into the DOM
 * and loads global styles. Rendered under React.StrictMode for dev checks.
 */
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./App.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
