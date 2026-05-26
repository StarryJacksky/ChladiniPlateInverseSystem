(() => {
  const originalFetch = window.fetch.bind(window);
  let promptOpen = false;

  function needsCredentials(message) {
    const text = String(message || "").toLowerCase();
    return text.includes("comsol_credentials_required")
      || text.includes("username or password")
      || text.includes("user name or password")
      || text.includes("invalid login")
      || text.includes("no user information found");
  }

  function field(label, input) {
    const wrapper = document.createElement("label");
    wrapper.style.display = "grid";
    wrapper.style.gap = "6px";
    wrapper.style.fontSize = "12px";
    wrapper.style.color = "#475569";
    wrapper.textContent = label;
    wrapper.appendChild(input);
    return wrapper;
  }

  function input(type) {
    const element = document.createElement("input");
    element.type = type;
    element.autocomplete = "off";
    element.style.padding = "10px 12px";
    element.style.border = "1px solid #cbd5e1";
    element.style.borderRadius = "6px";
    element.style.fontSize = "14px";
    return element;
  }

  function askCredentials() {
    return new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.style.position = "fixed";
      overlay.style.inset = "0";
      overlay.style.zIndex = "9999";
      overlay.style.display = "grid";
      overlay.style.placeItems = "center";
      overlay.style.background = "rgba(15, 23, 42, 0.48)";

      const panel = document.createElement("form");
      panel.style.width = "min(360px, calc(100vw - 32px))";
      panel.style.display = "grid";
      panel.style.gap = "14px";
      panel.style.padding = "18px";
      panel.style.borderRadius = "8px";
      panel.style.background = "#ffffff";
      panel.style.boxShadow = "0 24px 64px rgba(15, 23, 42, 0.24)";

      const title = document.createElement("strong");
      title.textContent = "COMSOL Server credentials";
      title.style.fontSize = "16px";
      title.style.color = "#0f172a";

      const userInput = input("text");
      const passwordInput = input("password");

      const actions = document.createElement("div");
      actions.style.display = "flex";
      actions.style.justifyContent = "flex-end";
      actions.style.gap = "8px";

      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.textContent = "Cancel";

      const submit = document.createElement("button");
      submit.type = "submit";
      submit.textContent = "Apply";
      submit.style.fontWeight = "600";

      actions.append(cancel, submit);
      panel.append(title, field("Username", userInput), field("Password", passwordInput), actions);
      overlay.appendChild(panel);
      document.body.appendChild(overlay);

      function close(value) {
        overlay.remove();
        resolve(value);
      }

      cancel.addEventListener("click", () => close(null));
      panel.addEventListener("submit", (event) => {
        event.preventDefault();
        const username = userInput.value.trim();
        if (!username) {
          userInput.focus();
          return;
        }
        close({ username, password: passwordInput.value });
      });
      userInput.focus();
    });
  }

  async function applyCredentials() {
    if (promptOpen) {
      return;
    }
    promptOpen = true;
    try {
      const credentials = await askCredentials();
      if (!credentials) {
        return;
      }
      const response = await originalFetch("/api/comsol-credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials),
      });
      const payload = await response.json();
      const status = document.getElementById("workflowStatus");
      if (!response.ok) {
        if (status) {
          status.textContent = payload.error || "COMSOL credentials could not be applied";
        }
        return;
      }
      if (status) {
        status.textContent = "COMSOL credentials applied. Click Run again.";
      }
    } finally {
      promptOpen = false;
    }
  }

  async function inspectPayload(payload) {
    if (!payload || payload.running) {
      return;
    }
    const message = payload.error || payload.message || "";
    if (needsCredentials(message)) {
      await applyCredentials();
    }
  }

  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    const request = args[0];
    const url = typeof request === "string" ? request : String(request && request.url || "");
    if (url.includes("/api/workflow") || url.includes("/api/run-workflow")) {
      const readJson = response.json.bind(response);
      response.json = async () => {
        const payload = await readJson();
        window.setTimeout(() => inspectPayload(payload), 0);
        return payload;
      };
    }
    return response;
  };
})();
