(() => {
  const pin = "927";
  const accessKey = "satelius-project-progress-access";
  const gateShell = document.querySelector("#gateShell");
  const projectContent = document.querySelector("#projectContent");
  const pinForm = document.querySelector("#pinForm");
  const pinInput = document.querySelector("#pinInput");
  const pinStatus = document.querySelector("#pinStatus");
  const lockButton = document.querySelector("#lockButton");
  const redirect = new URLSearchParams(window.location.search).get("redirect");
  const redirectTargets = {
    "harness-contract": "../harness-contract/",
    "harness-skill-walkthrough": "../harness-skill-walkthrough/",
  };

  const showProjects = () => {
    gateShell.hidden = true;
    projectContent.hidden = false;
    if (redirect && redirectTargets[redirect]) {
      window.location.replace(redirectTargets[redirect]);
      return;
    }
    document.querySelector("#projects-title").focus?.();
  };

  const lockProjects = () => {
    sessionStorage.removeItem(accessKey);
    projectContent.hidden = true;
    gateShell.hidden = false;
    pinInput.value = "";
    pinStatus.textContent = "页面已锁定。";
    pinInput.focus();
  };

  if (sessionStorage.getItem(accessKey) === "granted") showProjects();

  pinForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (pinInput.value === pin) {
      sessionStorage.setItem(accessKey, "granted");
      pinStatus.textContent = "访问已授权。";
      showProjects();
      return;
    }
    pinStatus.textContent = "PIN 不正确，请重新输入。";
    pinInput.select();
  });

  lockButton.addEventListener("click", lockProjects);
})();
