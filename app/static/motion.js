(() => {
  "use strict";

  function ready() {
    if (!window.gsap) return;

    const gsap = window.gsap;
    if (window.ScrollTrigger) {
      gsap.registerPlugin(window.ScrollTrigger);
    }

    gsap.from(".brand", {
      opacity: 0,
      y: -10,
      duration: 0.65,
      ease: "power3.out",
    });

    gsap.from(".nav", {
      opacity: 0,
      x: -10,
      duration: 0.45,
      stagger: 0.035,
      ease: "power2.out",
    });

    const pulse = gsap.to(".route-core", {
      scale: 1.035,
      duration: 1.9,
      yoyo: true,
      repeat: -1,
      ease: "sine.inOut",
      paused: true,
    });
    if (document.querySelector(".route-core")) pulse.play();

    gsap.to(".route-lines path", {
      strokeDashoffset: -40,
      duration: 4,
      repeat: -1,
      ease: "none",
    });

    function animateView(view) {
      if (!view) return;
      const panels = view.querySelectorAll(
        ".reveal-panel, .panel, .stat, .provider-card, .guide-step",
      );
      gsap.killTweensOf(panels);
      gsap.fromTo(
        panels,
        { opacity: 0, y: 16, scale: 0.985 },
        {
          opacity: 1,
          y: 0,
          scale: 1,
          duration: 0.55,
          stagger: 0.035,
          ease: "power3.out",
          clearProps: "transform",
        },
      );
    }

    animateView(document.querySelector(".view.active"));

    const workspace = document.querySelector(".workspace");
    if (workspace) {
      const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
          if (
            mutation.type === "attributes" &&
            mutation.attributeName === "class" &&
            mutation.target.classList.contains("active")
          ) {
            animateView(mutation.target);
          }
        }
      });
      document.querySelectorAll(".view").forEach((view) => {
        observer.observe(view, { attributes: true });
      });
    }

    if (window.ScrollTrigger && window.matchMedia("(min-width: 901px)").matches) {
      const guide = document.querySelector("#guide");
      const guideHero = guide?.querySelector(".guide-hero");
      const guideSteps = guide?.querySelector(".guide-steps");
      if (guide && guideHero && guideSteps) {
        let trigger = null;

        const syncGuideTrigger = () => {
          if (!guide.classList.contains("active")) {
            trigger?.kill();
            trigger = null;
            return;
          }
          if (trigger) return;

          requestAnimationFrame(() => {
            trigger = window.ScrollTrigger.create({
              trigger: guideSteps,
              start: "top 110px",
              end: "bottom bottom-=90",
              pin: guideHero,
              pinSpacing: false,
              invalidateOnRefresh: true,
            });
            window.ScrollTrigger.refresh();
          });
        };

        const guideObserver = new MutationObserver(syncGuideTrigger);
        guideObserver.observe(guide, { attributes: true, attributeFilter: ["class"] });
        syncGuideTrigger();
      }
    }

    if (document.querySelector(".hosted-hero")) {
      gsap.from(".floating-nav", {
        opacity: 0,
        y: -18,
        duration: 0.75,
        ease: "power3.out",
      });
      gsap.from(".hosted-hero .hero-copy > *", {
        opacity: 0,
        y: 24,
        duration: 0.8,
        stagger: 0.08,
        ease: "power3.out",
      });
      gsap.from(".hero-visual", {
        opacity: 0,
        x: 30,
        scale: 0.96,
        duration: 1,
        delay: 0.12,
        ease: "power3.out",
      });

      if (window.ScrollTrigger) {
        document.querySelectorAll(".visual-frame img").forEach((image) => {
          gsap.fromTo(
            image,
            { scale: 0.82, opacity: 0.45 },
            {
              scale: 1,
              opacity: 1,
              ease: "none",
              scrollTrigger: {
                trigger: image.closest(".visual-frame"),
                start: "top 88%",
                end: "center 52%",
                scrub: true,
              },
            },
          );
          gsap.to(image, {
            opacity: 0.22,
            ease: "none",
            scrollTrigger: {
              trigger: image.closest(".visual-frame"),
              start: "center 35%",
              end: "bottom 8%",
              scrub: true,
            },
          });
        });

        const storySection = document.querySelector(".story-section");
        const storyPin = document.querySelector(".story-pin");
        if (
          storySection &&
          storyPin &&
          window.matchMedia("(min-width: 981px)").matches
        ) {
          window.ScrollTrigger.create({
            trigger: storySection,
            start: "top 110px",
            end: "bottom bottom-=80",
            pin: storyPin,
            pinSpacing: false,
            invalidateOnRefresh: true,
          });
        }

        gsap.utils.toArray(".bento-card").forEach((card, index) => {
          gsap.from(card, {
            opacity: 0,
            y: 26,
            scale: 0.985,
            duration: 0.7,
            delay: index * 0.025,
            ease: "power3.out",
            scrollTrigger: {
              trigger: card,
              start: "top 88%",
            },
          });
        });
      }
    }

    document.querySelectorAll(".interactive-card").forEach((card) => {
      card.addEventListener("pointerenter", () => {
        gsap.to(card, { y: -4, duration: 0.28, ease: "power2.out" });
      });
      card.addEventListener("pointerleave", () => {
        gsap.to(card, { y: 0, duration: 0.28, ease: "power2.out" });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ready, { once: true });
  } else {
    ready();
  }
})();
