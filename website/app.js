const demoRoutes = {
  find: {
    kicker: "ROUTE 1 · START WITH A TOPIC",
    example: "<strong>Example:</strong> Renal <em>or</em> Acid–Base, from AnKing <em>or</em> Medicine.",
    steps: [
      {
        label: "Choose topics",
        title: "Choose one or several topics",
        description: "Search “renal,” then check First Aid › Renal and Systems › Renal. If you check several topics, a card can match any one of them. It does not need to have every selected tag.",
        image: "assets/screenshots/study-builder-find-topics.png",
        alt: "Vellum Find Topics screen showing Renal topic results",
        caption: "Typing filters a local topic index. It does not run a collection-wide search on every keystroke."
      },
      {
        label: "Choose source decks",
        title: "Choose where those topics should come from",
        description: "Vellum now shows the decks and subdecks that contain those cards. Check AnKing to include its subdecks, or open a parent and choose one specific subdeck.",
        image: "assets/screenshots/study-builder-find-decks.png",
        alt: "Vellum source deck screen showing AnKing and Medicine Renal",
        caption: "Topic choices use OR. Source-deck choices use OR. The topic set and source-deck set are combined with AND."
      },
      {
        label: "Inspect the exact matches",
        title: "See availability before building",
        description: "Vellum separates ready, suspended, buried, and already-filtered cards. The card snippets are only a preview. Choose a limit, check the result, then press Build & Study.",
        image: "assets/screenshots/study-builder-find-preview.png",
        alt: "Vellum card inspection screen showing matching Renal cards",
        caption: "The final scope is recalculated immediately before building so a stale preview cannot choose unintended cards."
      }
    ]
  },
  browse: {
    kicker: "ROUTE 2 · START WITH A DECK",
    example: "<strong>Example:</strong> AnKing deck → Resources → First Aid → Renal.",
    steps: [
      {
        label: "Choose decks",
        title: "Choose a parent deck or exact subdeck",
        description: "Check AnKing to include its descendants, or expand Medicine and choose only Medicine › Renal. The disclosure arrow looks inside a deck; the checkbox selects it.",
        image: "assets/screenshots/study-builder-browse-decks.png",
        alt: "Vellum Browse Collection deck tree with AnKing selected",
        caption: "Vellum attributes cards temporarily inside filtered decks back to their original home deck for scope calculations."
      },
      {
        label: "Explore tags in scope",
        title: "See only tags used inside those decks",
        description: "Vellum shows the tags that are actually used inside your selected decks. Expand a parent to look through it without selecting it, then check the exact level you want.",
        image: "assets/screenshots/study-builder-browse-tags.png",
        alt: "Vellum scoped tag tree showing Resources, First Aid, Renal, and Pathoma",
        caption: "Maintenance and update tags stay hidden in the ordinary view but remain discoverable under All tags."
      },
      {
        label: "Inspect the exact matches",
        title: "Inspect, limit, then study",
        description: "Choose Due + New, Due, New, or All; set the card limit; optionally avoid siblings; and inspect the exact availability before creating anything.",
        image: "assets/screenshots/study-builder-browse-preview.png",
        alt: "Vellum Browse Collection card inspection screen",
        caption: "Build & Study creates a rescheduling-enabled native filtered deck and preserves Anki/FSRS answer behavior."
      }
    ]
  }
};

const routeButtons = [...document.querySelectorAll("[data-route]")];
const stepList = document.querySelector("[data-demo-steps]");
const title = document.querySelector("[data-demo-title]");
const description = document.querySelector("[data-demo-description]");
const kicker = document.querySelector("[data-demo-kicker]");
const example = document.querySelector("[data-demo-example]");
const demoImage = document.querySelector("[data-demo-image]");
const caption = document.querySelector("[data-demo-caption]");
const fullscreenLink = document.querySelector("[data-fullscreen]");
let currentRoute = "find";
let currentStep = 0;
let autoTimer;

function renderSteps() {
  const route = demoRoutes[currentRoute];
  stepList.innerHTML = route.steps.map((step, index) => `<li><button type="button" data-step="${index}" class="${index === currentStep ? "active" : ""}"><span>${index + 1}</span>${step.label}</button></li>`).join("");
  stepList.setAttribute("aria-label", `${currentRoute === "find" ? "Find Topics" : "Browse Collection"} walkthrough`);
}

function renderDemo(animate = true) {
  const route = demoRoutes[currentRoute];
  const step = route.steps[currentStep];
  kicker.textContent = route.kicker;
  title.textContent = step.title;
  description.textContent = step.description;
  example.innerHTML = route.example;
  caption.textContent = step.caption;
  fullscreenLink.href = step.image;
  if (animate) demoImage.classList.add("switching");
  window.setTimeout(() => {
    demoImage.src = step.image;
    demoImage.alt = step.alt;
    demoImage.onload = () => demoImage.classList.remove("switching");
  }, animate ? 110 : 0);
  renderSteps();
}

function resetAutoplay() {
  window.clearInterval(autoTimer);
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  autoTimer = window.setInterval(() => {
    currentStep = (currentStep + 1) % demoRoutes[currentRoute].steps.length;
    renderDemo();
  }, 6500);
}

routeButtons.forEach(button => button.addEventListener("click", () => {
  currentRoute = button.dataset.route;
  currentStep = 0;
  routeButtons.forEach(item => {
    const selected = item === button;
    item.classList.toggle("active", selected);
    item.setAttribute("aria-pressed", String(selected));
  });
  renderDemo();
  resetAutoplay();
}));

stepList.addEventListener("click", event => {
  const button = event.target.closest("[data-step]");
  if (!button) return;
  currentStep = Number(button.dataset.step);
  renderDemo();
  resetAutoplay();
});

document.querySelectorAll("[data-copy]").forEach(button => button.addEventListener("click", async () => {
  const value = button.dataset.copy;
  try { await navigator.clipboard.writeText(value); }
  catch { window.prompt("Copy this AnkiWeb code:", value); }
  const toast = document.querySelector("[data-toast]");
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 1800);
}));

const menu = document.querySelector("[data-menu]");
const nav = document.querySelector("[data-nav]");
menu.addEventListener("click", () => {
  const open = nav.classList.toggle("open");
  menu.setAttribute("aria-expanded", String(open));
});
nav.addEventListener("click", event => {
  if (!event.target.closest("a")) return;
  nav.classList.remove("open");
  menu.setAttribute("aria-expanded", "false");
});

const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    entry.target.classList.add("visible");
    revealObserver.unobserve(entry.target);
  });
}, { threshold: .08, rootMargin: "0px 0px -40px" });
document.querySelectorAll(".reveal").forEach(element => revealObserver.observe(element));

const header = document.querySelector("[data-header]");
window.addEventListener("scroll", () => header.classList.toggle("scrolled", window.scrollY > 20), { passive: true });

renderDemo(false);
resetAutoplay();
