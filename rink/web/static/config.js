/* Where the API lives.
   - Served by the Python process itself (localhost, or a LAN IP such as
     192.168.x.x from a phone): same origin, so empty.
   - Served from static hosting (Cloudflare Pages): the Render service.
   - ?api=https://... on the URL overrides either, for one-off testing. */
window.RINK_API = (
  location.hostname === "localhost" ||
  location.hostname === "127.0.0.1" ||
  /^\d+\.\d+\.\d+\.\d+$/.test(location.hostname)
) ? "" : "https://rink.onrender.com";
