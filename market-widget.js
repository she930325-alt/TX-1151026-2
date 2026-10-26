(function () {
  "use strict";
  const dataUrl = new URL("data/market.json", document.baseURI).toString();
  const fmt = (v, digits = 2) => v == null || v === "" || !Number.isFinite(Number(v))
    ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: digits });
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
  const table = (rows, quarterly) => {
    if (!rows || !rows.length) return '<p class="muted">目前沒有可用資料；首次排程完成後再重新整理。</p>';
    return '<div class="tablewrap"><table style="min-width:900px"><thead><tr>' +
      '<th>期間結束日</th><th>營收（百萬美元）</th><th>EPS（美元）</th><th>毛利率</th>' +
      '<th>自由現金流（百萬美元）</th><th>申報日期</th><th>表單</th></tr></thead><tbody>' +
      rows.slice().reverse().map(r => '<tr><td>' + esc(r.period_end) + '</td>' +
        '<td>' + fmt(r.revenue == null ? null : r.revenue / 1e6, 1) + '</td>' +
        '<td>' + fmt(r.eps, 3) + '</td>' +
        '<td>' + (r.gross_margin_pct == null ? '—' : fmt(r.gross_margin_pct, 2) + '%') + '</td>' +
        '<td>' + fmt(r.free_cash_flow == null ? null : r.free_cash_flow / 1e6, 1) + '</td>' +
        '<td>' + esc(r.filed || '') + '</td><td>' + esc(r.form || '') + '</td></tr>').join('') +
      '</tbody></table></div>';
  };
  function addCard(parent, id, title) {
    let el = document.getElementById(id);
    if (!el) {
      el = document.createElement("div");
      el.id = id;
      el.className = "card span12";
      el.innerHTML = "<h2>" + title + "</h2><div class='muted'>正在讀取自動資料…</div>";
      parent.appendChild(el);
    }
    return el;
  }
  function start() {
    const overview = document.querySelector("#overview .grid");
    const financialPanel = document.querySelector("#financials .grid");
    if (!overview || !financialPanel) return;
    const statusCard = addCard(overview, "autoMarketStatus", "自動行情資料");
    const financialCard = addCard(financialPanel, "autoFundamentals", "自動匯入財報（SEC）");
    fetch(dataUrl, { cache: "no-store" }).then(response => {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    }).then(data => {
      const stocks = data.stocks || {};
      const tickers = Object.keys(stocks);
      if (typeof state !== "undefined" && Array.isArray(state.stocks)) {
        tickers.forEach(ticker => {
          const item = stocks[ticker];
          let stock = state.stocks.find(s => String(s.ticker).toUpperCase() === ticker);
          if (!stock) {
            stock = {ticker, name:item.company || ticker, price:0, eps:0, pe:15, mos:25,
              asof:"", status:"觀察中", risk:"自動匯入；估值假設請自行設定", financials:[]};
            state.stocks.push(stock);
          }
          if (item.company) stock.name = item.company;
          if (item.price != null && item.quote && item.quote.date) {
            stock.price = Number(item.price);
            stock.asof = item.quote.date;
          }
        });
        if (typeof persist === "function") persist();
        if (typeof renderAll === "function") renderAll();
      }
      const selected = document.getElementById("tickerSelect");
      const render = () => {
        const ticker = selected && stocks[selected.value] ? selected.value : tickers[0];
        const item = stocks[ticker] || {};
        const q = item.quote || {};
        const pstatus = item.status && item.status.price || "unknown";
        const sstatus = item.status && item.status.sec || "unknown";
        statusCard.innerHTML = "<h2>自動行情資料</h2>" +
          "<p><b>" + esc(ticker) + " " + esc(item.company || "") + "</b></p>" +
          "<div class='metrics'>" +
          "<div class='metric'><small>最新可用收盤價（USD）</small><strong>" + fmt(q.close) + "</strong></div>" +
          "<div class='metric'><small>行情日期</small><strong>" + esc(q.date || "—") + "</strong></div>" +
          "<div class='metric'><small>成交量</small><strong>" + fmt(q.volume, 0) + "</strong></div>" +
          "<div class='metric'><small>資料集更新時間（UTC）</small><strong style='font-size:14px'>" + esc(data.updated_at || "尚未更新") + "</strong></div></div>" +
          "<p class='muted'>行情來源：Stooq 日線 CSV。此資料可能延遲、缺漏或無法取得，不保證即時；請獨立核對。行情狀態：" +
          esc(pstatus) + "；SEC 狀態：" + esc(sstatus) + "。</p>" +
          "<p class='muted'>資料檔：" + esc(dataUrl) + "。若首次更新尚未執行，請到 GitHub Actions 手動執行 Update US stock data。</p>";
        const f = item.financials || {};
        financialCard.innerHTML = "<h2>自動匯入財報（SEC）— " + esc(ticker) + "</h2>" +
          "<p class='muted'>SEC 公開申報資料；金額已換算為百萬美元顯示，EPS 為美元／股。欄位缺值表示來源未提供可對應數據，不代表零。季度資料僅取約 70–110 天的申報期間，個別公司財政季度可能不同。</p>" +
          "<h3 style='font-size:15px;color:var(--navy)'>年度資料</h3>" + table(f.annual, false) +
          "<h3 style='font-size:15px;color:var(--navy);margin-top:18px'>季度資料</h3>" + table(f.quarterly, true) +
          "<p class='muted'>來源：SEC Company Facts / XBRL。請以公司最新年報與季報核對，因為申報可能修訂且標籤映射不一定完整。</p>";
      };
      render();
      if (selected) selected.addEventListener("change", render);
    }).catch(error => {
      statusCard.innerHTML = "<h2>自動行情資料</h2><p class='muted'>無法讀取 data/market.json：" +
        esc(error.message) + "。請確認資料檔已存在且 GitHub Pages 已部署。</p>";
      financialCard.innerHTML = "<h2>自動匯入財報（SEC）</h2><p class='muted'>資料尚未載入。請確認 GitHub Actions 已成功執行。</p>";
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();