(() => {
  "use strict";

  function ready() {
    if (!window.gsap) return;

    const gsap = window.gsap;
    const ScrollTrigger = window.ScrollTrigger;
    if (ScrollTrigger) gsap.registerPlugin(ScrollTrigger);

    const brand = document.querySelector(".brand-lockup");
    if (brand) {
      gsap.from(brand, {
        opacity: 0,
        y: -10,
        duration: 0.65,
        ease: "power3.out",
      });
    }

    const navItems = document.querySelectorAll(".nav");
    if (navItems.length) {
      gsap.from(navItems, {
        opacity: 0,
        y: -8,
        duration: 0.45,
        stagger: 0.025,
        ease: "power2.out",
      });
    }

    const signalCore = document.querySelector(".signal-core");
    if (signalCore) {
      gsap.to(signalCore, {
        scale: 1.035,
        duration: 1.9,
        yoyo: true,
        repeat: -1,
        ease: "sine.inOut",
      });
      gsap.to(".orbit-b", {
        rotation: 360,
        transformOrigin: "50% 50%",
        duration: 32,
        repeat: -1,
        ease: "none",
      });
    }

    const sphereCore = document.querySelector(".sphere-core");
    if (sphereCore) {
      gsap.to(sphereCore, {
        scale: 1.04,
        duration: 2.1,
        yoyo: true,
        repeat: -1,
        ease: "sine.inOut",
      });
      gsap.to(".ring-two", {
        rotation: 360,
        transformOrigin: "50% 50%",
        duration: 38,
        repeat: -1,
        ease: "none",
      });
    }

    function animateView(view) {
      if (!view) return;
      const elements = view.querySelectorAll(
        ".system-hero, .telemetry-cell, .matrix-panel, .setup-intro, .setup-console, " +
          ".credential-provider, .providers-intro, .provider-row, .playground-shell, " +
          ".usage-workspace, .catalog-surface, .guide-hero, .guide-stack article, .route-accordion",
      );
      if (!elements.length) return;

      gsap.killTweensOf(elements);
      gsap.fromTo(
        elements,
        { opacity: 0, y: 16 },
        {
          opacity: 1,
          y: 0,
          duration: 0.5,
          stagger: 0.025,
          ease: "power3.out",
          clearProps: "transform",
        },
      );
    }

    const activeView = document.querySelector(".view.active");
    if (activeView) animateView(activeView);

    document.querySelectorAll(".view").forEach((view) => {
      const observer = new MutationObserver(() => {
        if (view.classList.contains("active")) {
          requestAnimationFrame(() => animateView(view));
        }
      });
      observer.observe(view, { attributes: true, attributeFilter: ["class"] });
    });

    const publicHero = document.querySelector(".cinematic-hero");
    if (publicHero) {
      gsap.from(".site-nav", {
        opacity: 0,
        y: -18,
        duration: 0.75,
        ease: "power3.out",
      });
      gsap.from(".cinematic-hero .hero-copy > *", {
        opacity: 0,
        y: 26,
        duration: 0.85,
        stagger: 0.075,
        ease: "power3.out",
      });
      gsap.from(".router-sphere", {
        opacity: 0,
        scale: 0.86,
        duration: 1.15,
        delay: 0.12,
        ease: "power3.out",
      });
    }

    if (!ScrollTrigger) return;

    gsap.utils.toArray(".bento").forEach((card, index) => {
      gsap.from(card, {
        opacity: 0,
        y: 24,
        duration: 0.7,
        delay: index * 0.025,
        ease: "power3.out",
        scrollTrigger: {
          trigger: card,
          start: "top 88%",
        },
      });
    });

    const desire = document.querySelector(".desire-chapter");
    const pinnedCopy = document.querySelector(".pinned-copy");
    if (
      desire &&
      pinnedCopy &&
      window.matchMedia("(min-width: 981px)").matches
    ) {
      ScrollTrigger.create({
        trigger: desire,
        start: "top 118px",
        end: "bottom bottom-=90",
        pin: pinnedCopy,
        pinSpacing: false,
        invalidateOnRefresh: true,
      });
    }

    const stackCards = gsap.utils.toArray(".stack-card");
    stackCards.forEach((card, index) => {
      const image = card.querySelector("img");
      if (image) {
        gsap.fromTo(
          image,
          { scale: 0.9 },
          {
            scale: 1,
            ease: "none",
            scrollTrigger: {
              trigger: card,
              start: "top 90%",
              end: "top 28%",
              scrub: true,
            },
          },
        );
      }

      gsap.to(card, {
        scale: 1 - index * 0.018,
        transformOrigin: "50% 0%",
        ease: "none",
        scrollTrigger: {
          trigger: card,
          start: "top 150px",
          end: "bottom 120px",
          scrub: true,
        },
      });

      if (index < stackCards.length - 1) {
        gsap.to(card, {
          opacity: 0.34,
          ease: "none",
          scrollTrigger: {
            trigger: stackCards[index + 1],
            start: "top 65%",
            end: "top 24%",
            scrub: true,
          },
        });
      }
    });

    const finalAction = document.querySelector(".final-action");
    if (finalAction) {
      gsap.from(finalAction.children, {
        opacity: 0,
        y: 30,
        duration: 0.75,
        stagger: 0.08,
        ease: "power3.out",
        scrollTrigger: {
          trigger: finalAction,
          start: "top 82%",
        },
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ready, { once: true });
  } else {
    ready();
  }
})();
