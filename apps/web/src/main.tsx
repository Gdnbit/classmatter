import React from "react"

import ReactDOM from "react-dom/client"

import App from "./App"
import DesktopChrome from "./DesktopChrome"

import "./index.css"
import "./product.css"
import "./composer.css"
import "./acceptance.css"

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {import.meta.env.VITE_CLASS_OS_DESKTOP === "true" && <DesktopChrome />}
    <App />
  </React.StrictMode>,
)
