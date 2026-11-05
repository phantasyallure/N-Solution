"use strict";
// Run the Vercel dashboard on your own computer to test before deploying:  npm run dev  -> http://localhost:3000
const http = require("http");
const fs = require("fs");
const path = require("path");

try {  // minimal .env loader (real environment variables win)
  for (const line of fs.readFileSync(path.join(__dirname, ".env"), "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Za-z_][\w]*)\s*=\s*(.*?)\s*$/);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^['"]|['"]$/g, "");
  }
} catch {}

const { createHandler } = require("./lib/core");
const api = createHandler({ env: process.env, fetch: globalThis.fetch });
const PUB = path.join(__dirname, "public");
const TYPES = { ".html": "text/html; charset=utf-8", ".png": "image/png", ".json": "application/json", ".js": "text/javascript", ".css": "text/css", ".jpg": "image/jpeg" };

http.createServer((req, res) => {
  const p = new URL(req.url, "http://x").pathname;
  if (p === "/api") return api(req, res);
  let file = path.join(PUB, p === "/" ? "index.html" : p);
  if (!path.extname(file) && fs.existsSync(file + ".html")) file += ".html";   // clean URLs: /admin -> admin.html
  if (!file.startsWith(PUB) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.statusCode = 404; return res.end("not found"); }
  res.setHeader("Content-Type", TYPES[path.extname(file)] || "application/octet-stream");
  fs.createReadStream(file).pipe(res);
}).listen(process.env.PORT || 3000, () => console.log(`Nardjis dashboard -> http://localhost:${process.env.PORT || 3000}`));
