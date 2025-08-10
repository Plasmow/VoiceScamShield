import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";  // Adjust the path if your component filename is different
import "./index.css"; // Adjust filename if you used main.css or another name

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
