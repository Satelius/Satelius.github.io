(() => {
  const rows = window.EVIDENCE;
  const el = id => document.getElementById(id);
  let group = 'Tabero';
  let view = [];
  function show() {
    const row = view[Number(el('choice').value)];
    el('display').replaceChildren();
    el('links').replaceChildren();
    if (!row) {
      el('state').textContent = '';
      el('title').textContent = '这一组没有符合筛选的运行';
      el('detail').textContent = '';
      el('count').textContent = '';
      return;
    }
    const video = row.media.endsWith('.mp4');
    const media = document.createElement(video ? 'video' : 'img');
    if (video) {
      media.controls = true;
      media.preload = 'metadata';
      media.playsInline = true;
      media.poster = 'assets/posters/' + row.media.split('/').join('_') + '.jpg';
    } else media.alt = row.title;
    media.src = row.media;
    el('display').append(media);
    el('state').dataset.value = el('state').textContent = row.status;
    el('title').textContent = row.title;
    el('detail').textContent = row.detail;
    for (const [label, path] of row.links.concat([['打开原始媒体', row.media]])) {
      const a = document.createElement('a'); a.href = path; a.textContent = label;
      el('links').append(a);
    }
    el('count').textContent = (Number(el('choice').value) + 1) + ' / ' + view.length + ' 条记录';
  }
  function refresh() {
    view = rows.filter(r => r.group === group && (el('filter').value === '全部' || el('filter').value === r.status));
    el('choice').replaceChildren(...view.map((r,i) => new Option(r.title, i)));
    for (const button of el('tabs').children) button.setAttribute('aria-pressed', button.textContent === group);
    show();
  }
  for (const label of ['Tabero','RoboLab','UniVTAC','生成接口']) {
    const b = document.createElement('button'); b.textContent = label; b.type = 'button';
    b.onclick = () => {group = label; el('filter').value = '全部'; refresh();};
    el('tabs').append(b);
  }
  el('filter').onchange = refresh; el('choice').onchange = show;
  refresh();
})();
