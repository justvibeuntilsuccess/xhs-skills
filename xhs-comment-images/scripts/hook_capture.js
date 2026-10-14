// Capture hook for Xiaohongshu / RedNote comment APIs.
// Install with: cdp('Page.addScriptToEvaluateOnNewDocument', source=<this file's text>)
// then reload the note. Every comment payload lands in window.__bodies (newest last);
// window.__cap holds the request records (url/method/headers/body) for debugging.
(() => {
  window.__cap = [];
  window.__bodies = [];
  const rec = o => { try { window.__cap.push(o); } catch (e) {} };
  const isC = u => String(u).indexOf('comment') >= 0 && String(u).indexOf('/api/sns/') >= 0;
  const isApi = u => /\/api\/sns\//.test(String(u));
  const push = (u, t) => { try { window.__bodies.push({ url: String(u).slice(0, 260), text: t }); } catch (e) {} };

  const OF = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (isApi(url)) {
      const h = {};
      try { if (init && init.headers) new Headers(init.headers).forEach((v, k) => h[k] = v); } catch (e) {}
      rec({ via: 'fetch', url: String(url), headers: h, body: init && init.body ? String(init.body) : null });
      return OF.apply(this, arguments).then(r => {
        if (isC(url)) r.clone().text().then(t => push(url, t)).catch(() => {});
        return r;
      });
    }
    return OF.apply(this, arguments);
  };

  const OX = XMLHttpRequest.prototype.open;
  const OS = XMLHttpRequest.prototype.send;
  const OH = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
    (this.__h = this.__h || {})[k] = v;   // keep request headers (X-s / X-S-Common etc.) for debugging
    return OH.call(this, k, v);
  };
  XMLHttpRequest.prototype.open = function (m, u, ...r) {
    this.__u = u; this.__m = m;
    return OX.call(this, m, u, ...r);
  };
  XMLHttpRequest.prototype.send = function (b) {
    if (isApi(this.__u)) {
      const self = this;
      rec({ via: 'xhr', url: String(this.__u), method: this.__m, headers: this.__h || {}, body: b ? String(b) : null });
      self.addEventListener('load', () => {
        try {
          if (isC(self.__u)) push(self.__u, self.responseText);
          rec({ via: 'resp', url: String(self.__u), status: self.status, len: String(self.responseText || '').length });
        } catch (e) {}
      });
    }
    return OS.call(this, b);
  };
  return 'hook-installed';
})()
