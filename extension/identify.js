/* Pure URL parsing, shared by the popup and its node-based regression checks. */
function identifyTikTok(raw) {
  let url;
  try { url = new URL(raw); } catch { return null; }
  if (url.protocol !== "https:" || !/(^|\.)tiktok\.com$/i.test(url.hostname)) return null;
  const video = url.pathname.match(/^\/@[\w.]+\/(?:video|photo)\/(\d+)\/?$/);
  if (video) return {kind: "videos", query: video[1], label: "视频 / 图文"};
  const creator = url.pathname.match(/^\/@([\w.]+)\/?$/);
  if (creator) return {kind: "creators", query: creator[1], label: "达人"};
  const product = url.pathname.match(/\/(?:product|pdp)\/(?:[^/]+\/)?(\d+)\/?$/);
  if (product) return {kind: "products", query: product[1], label: "商品"};
  const item = url.searchParams.get("product_id");
  if (item && /^\d+$/.test(item) && /\/(shop|product)\b/.test(url.pathname)) {
    return {kind: "products", query: item, label: "商品"};
  }
  return null;
}
if (typeof module !== "undefined") module.exports = {identifyTikTok};
