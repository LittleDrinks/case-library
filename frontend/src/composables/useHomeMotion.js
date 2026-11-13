import { nextTick, onBeforeUnmount, watch } from "vue";

export function useHomeMotion(root, hero, loading) {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let observer;
  let animationFrame = 0;
  let parallaxStarted = false;

  function reveal(entries) {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add("is-revealed");
      observer?.unobserve(entry.target);
    }
  }

  function observeContent() {
    const elements = root.value?.querySelectorAll("[data-reveal]") || [];
    if (reducedMotion.matches || !("IntersectionObserver" in window)) {
      elements.forEach(element => element.classList.add("is-revealed"));
      return;
    }
    observer?.disconnect();
    observer = new IntersectionObserver(reveal, { threshold: 0.12, rootMargin: "0px 0px -24px" });
    elements.forEach(element => observer.observe(element));
  }

  function moveHero() {
    animationFrame = 0;
    if (!hero.value || reducedMotion.matches) return;
    const offset = Math.min(window.scrollY * 0.12, 72);
    hero.value.style.setProperty("--hero-shift", `${offset}px`);
  }

  function queueMove() {
    if (!animationFrame) animationFrame = window.requestAnimationFrame(moveHero);
  }

  function startParallax() {
    if (parallaxStarted) return;
    parallaxStarted = true;
    window.addEventListener("scroll", queueMove, { passive: true });
    moveHero();
  }

  async function start() {
    await nextTick();
    observeContent();
    startParallax();
  }

  function stop() {
    observer?.disconnect();
    if (parallaxStarted) window.removeEventListener("scroll", queueMove);
    if (animationFrame) window.cancelAnimationFrame(animationFrame);
  }

  watch(loading, value => {
    if (!value) void start();
  }, { immediate: true });

  onBeforeUnmount(stop);
}
