(() => {
  "use strict";

  const toast = (message) => {
    const node = document.querySelector("#hostedToast");
    if (!node) return;
    node.textContent = message;
    node.classList.add("show");
    window.setTimeout(() => node.classList.remove("show"), 1800);
  };

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    toast("Command copied");
  }

  function boot() {
    document.addEventListener("click", (event) => {
      const route = event.target.closest("[data-route-panel]");
      if (route) {
        document.querySelectorAll("[data-route-panel]").forEach((button) => {
          button.classList.toggle("active", button === route);
        });
        return;
      }

      const runTab = event.target.closest("[data-run-tab]");
      if (runTab) {
        const name = runTab.dataset.runTab;
        document.querySelectorAll("[data-run-tab]").forEach((button) => {
          button.classList.toggle("active", button === runTab);
        });
        document.querySelectorAll("[data-run-content]").forEach((panel) => {
          panel.classList.toggle("active", panel.dataset.runContent === name);
        });
        return;
      }

      const copy = event.target.closest("[data-copy]");
      if (copy) {
        copyText(copy.dataset.copy || "");
      }
    });

    const track = document.querySelector("#storyTrack");
    const slides = track ? [...track.children] : [];
    let index = 0;

    const renderCarousel = () => {
      if (!track || !slides.length) return;
      track.style.transform = `translateX(-${index * 100}%)`;
    };

    document.querySelector("#storyPrev")?.addEventListener("click", () => {
      index = (index - 1 + slides.length) % slides.length;
      renderCarousel();
    });

    document.querySelector("#storyNext")?.addEventListener("click", () => {
      index = (index + 1) % slides.length;
      renderCarousel();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
