(() => {
  const pages = Array.isArray(window.SATELIUS_PAGES) ? window.SATELIUS_PAGES : [];
  const pageIndex = document.querySelector("#page-index");
  const filters = document.querySelector("#index-filters");
  const search = document.querySelector("#index-search");
  const status = document.querySelector("#result-status");
  const count = document.querySelector("#entry-count");

  if (!pageIndex || !filters || !search || !status || !count) {
    return;
  }

  document.documentElement.classList.add("has-js");

  const state = {
    category: "全部",
    query: ""
  };

  const createElement = (tagName, className, text) => {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };

  const searchableTextFor = (page) => [
    page.title,
    page.label,
    page.summary,
    page.category,
    ...page.tags
  ].join(" ").toLocaleLowerCase("zh-CN");

  const createTagList = (tags) => {
    const list = createElement("ul", "entry-tags");
    list.setAttribute("aria-label", "标签");

    tags.forEach((tag) => {
      const item = createElement("li", "", tag);
      list.append(item);
    });

    return list;
  };

  const createEntry = (page) => {
    const article = createElement("article", "archive-entry");
    article.style.setProperty("--entry-accent", page.accent || "#ff4b00");

    const link = createElement("a", "entry-link");
    link.href = page.href;
    if (page.external) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.setAttribute("aria-label", `${page.title}（在新标签页打开外部网站）`);
    }

    const number = createElement("div", "entry-number");
    number.append(
      createElement("span", "entry-number-main", page.number),
      createElement("span", "entry-year", `/ ${page.year}`)
    );

    const main = createElement("div", "entry-main");
    const meta = createElement("div", "entry-meta");
    meta.append(
      createElement("span", `entry-type ${page.external ? "entry-type--external" : ""}`, page.external ? "EXT." : "LOCAL"),
      createElement("span", "entry-label", page.label)
    );

    const time = createElement("time", "entry-date", page.date.replaceAll("-", "."));
    time.dateTime = page.date;
    meta.append(time);

    main.append(
      meta,
      createElement("h3", "entry-title", page.title),
      createElement("p", "entry-summary", page.summary),
      createTagList(page.tags)
    );

    const action = createElement("div", "entry-action");
    action.append(
      createElement("span", "entry-action-label", page.external ? "VISIT" : "OPEN"),
      createElement("span", "entry-arrow", page.external ? "↗" : "→")
    );
    action.lastElementChild.setAttribute("aria-hidden", "true");

    link.append(number, main, action);
    article.append(link);
    return article;
  };

  const render = () => {
    const query = state.query.trim().toLocaleLowerCase("zh-CN");
    const visiblePages = pages.filter((page) => {
      const matchesCategory = state.category === "全部" || page.category === state.category;
      const matchesQuery = !query || searchableTextFor(page).includes(query);
      return matchesCategory && matchesQuery;
    });

    const fragment = document.createDocumentFragment();
    visiblePages.forEach((page) => fragment.append(createEntry(page)));

    pageIndex.replaceChildren(fragment);
    count.textContent = String(pages.length).padStart(2, "0");
    status.textContent = `显示 ${visiblePages.length} / ${pages.length} 条档案`;

    if (!visiblePages.length) {
      const empty = createElement("div", "empty-result");
      empty.append(
        createElement("p", "empty-code", "NO MATCH / 00"),
        createElement("h3", "", "没有匹配条目"),
        createElement("p", "", "换一个关键词，或切回“全部”。")
      );
      pageIndex.append(empty);
    }
  };

  const categories = ["全部", ...new Set(pages.map((page) => page.category))];
  categories.forEach((category) => {
    const button = createElement("button", "filter-button", category);
    button.type = "button";
    button.dataset.category = category;
    button.setAttribute("aria-pressed", category === state.category ? "true" : "false");
    button.addEventListener("click", () => {
      state.category = category;
      filters.querySelectorAll("button").forEach((filterButton) => {
        filterButton.setAttribute("aria-pressed", String(filterButton === button));
      });
      render();
    });
    filters.append(button);
  });

  search.addEventListener("input", () => {
    state.query = search.value;
    render();
  });

  render();
})();
