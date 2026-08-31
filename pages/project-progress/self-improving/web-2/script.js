const sections = [...document.querySelectorAll('main section[id]')];
const navLinks = [...document.querySelectorAll('.topbar nav a')];

const setActiveLink = () => {
  const current = sections
    .filter((section) => section.getBoundingClientRect().top <= 130)
    .at(-1)?.id;

  navLinks.forEach((link) => {
    link.classList.toggle('active', link.getAttribute('href') === `#${current}`);
  });
};

window.addEventListener('scroll', setActiveLink, { passive: true });
setActiveLink();
