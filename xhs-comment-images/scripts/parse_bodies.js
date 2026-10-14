// Parse every captured comment payload into a flat image list.
// Run in the page after the scroll + "expand replies" pass:
//   js(open('scripts/parse_bodies.js').read())   ->  {pages, comments, subs, pics[], subPics[]}
// Then dump window.__X.pics to a JSON file and hand it to fetch_and_send.py.
(() => {
  const out = { pages: 0, comments: 0, subs: 0, pics: [], subPics: [] };
  const seen = new Set();
  const addPic = (p, where, owner) => {
    if (!p) return;
    const lst = p.info_list || [];
    const dft = (lst.find(i => i.image_scene === 'WB_DFT') || {}).url;   // best rendition
    const prv = (lst.find(i => i.image_scene === 'WB_PRV') || {}).url;   // thumbnail
    const url = dft || p.url_default || prv || p.url || '';
    if (!url || seen.has(url)) return;
    seen.add(url);
    (where === 'sub' ? out.subPics : out.pics).push({
      url, prv: prv || '', w: p.width, h: p.height, owner: owner || '', kind: where
    });
  };
  (window.__bodies || []).forEach(b => {
    let j = null;
    try { j = JSON.parse(b.text); } catch (e) { return; }   // a non-JSON body is not fatal
    const d = (j && j.data) || {};
    const cs = d.comments;
    if (!Array.isArray(cs) || !cs.length) return;
    out.pages++;
    cs.forEach(c => {
      out.comments++;
      (c.pictures || []).forEach(p => addPic(p, 'parent', (c.user_info && c.user_info.nickname) || ''));
      (c.sub_comments || []).forEach(s => {
        out.subs++;
        (s.pictures || []).forEach(p => addPic(p, 'sub', (s.user_info && s.user_info.nickname) || ''));
      });
    });
  });
  window.__X = out;
  return { pages: out.pages, comments: out.comments, subs: out.subs,
           parentPics: out.pics.length, subPics: out.subPics.length };
})()
