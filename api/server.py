#!/usr/bin/env python3
"""
Image Generation API  +  Document → Webpage API
Wraps Gemini, saves results and returns public URLs.
"""

import os
import uuid
import base64
import subprocess
import tempfile
import requests
import markdown as md_lib
import docx as docx_lib
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_BASE    = "https://generativelanguage.googleapis.com"
IMAGE_DIR      = "/var/www/images"
PUBLIC_BASE    = os.environ.get("PUBLIC_BASE", "https://images-mvac6g.vyibc.com")
# ─────────────────────────────────────────────────────────────────────────────


@app.route("/v1beta/models/<path:model>:generateContent", methods=["POST"])
def generate_content(model):
    """
    Proxy to Gemini generateContent.
    If the response contains an image, saves it to disk and replaces
    inlineData with a public { "imageUrl": "..." } field.
    """
    body = request.get_json(force=True, silent=True)
    if not body:
        return jsonify({"error": {"code": 400, "message": "Invalid JSON body"}}), 400

    # Forward to Gemini
    gemini_url = f"{GEMINI_BASE}/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    try:
        resp = requests.post(gemini_url, json=body, timeout=60)
    except requests.exceptions.RequestException as e:
        return jsonify({"error": {"code": 502, "message": str(e)}}), 502

    data = resp.json()

    if "error" in data:
        return jsonify(data), resp.status_code

    # Extract image(s) and replace inlineData with public URL
    image_urls = []
    candidates = data.get("candidates", [])
    for candidate in candidates:
        parts = candidate.get("content", {}).get("parts", [])
        for part in parts:
            if "inlineData" in part:
                inline   = part.pop("inlineData")
                mime     = inline.get("mimeType", "image/png")
                ext      = "jpg" if "jpeg" in mime else "png"
                filename = f"{uuid.uuid4().hex}.{ext}"
                filepath = os.path.join(IMAGE_DIR, filename)

                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(inline["data"]))

                public_url = f"{PUBLIC_BASE}/{filename}"
                part["imageUrl"] = public_url
                image_urls.append(public_url)

    # Convenience: top-level image_urls list
    data["image_urls"] = image_urls

    return jsonify(data), 200


# ── Document helpers ──────────────────────────────────────────────────────────

def extract_text(filepath, filename):
    """Extract plain text from .txt / .md / .pdf / .docx"""
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".txt", ".md"):
        with open(filepath, "r", errors="replace") as f:
            return f.read(), ext
    if ext == ".pdf":
        result = subprocess.run(
            ["pdftotext", filepath, "-"],
            capture_output=True, text=True
        )
        return result.stdout, ext
    if ext == ".docx":
        doc = docx_lib.Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs), ext
    raise ValueError(f"Unsupported file type: {ext}")


HTML_PROMPT = """You are an expert web developer.
Convert the following document content into a beautiful, modern, self-contained HTML page.
Requirements:
- Single HTML file with embedded CSS (no external dependencies)
- Clean, readable typography with proper headings/paragraphs
- Responsive design (mobile-friendly)
- Light background, good contrast
- Preserve all content and structure from the original document
- Add a styled header with the document title

Document content:
---
{content}
---

Return ONLY the complete HTML code starting with <!DOCTYPE html>, no explanations."""


def content_to_html(text, gemini_api_key):
    """Ask Gemini to turn raw text into a styled HTML page."""
    url = (
        f"https://generativelanguage.googleapis.com"
        f"/v1beta/models/gemini-2.5-flash:generateContent"
        f"?key={gemini_api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": HTML_PROMPT.format(content=text[:30000])}]}]
    }
    resp = requests.post(url, json=payload, timeout=60)
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "Gemini error"))
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    # Strip possible markdown code fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    return raw.strip()


# ── Document → Webpage endpoint ───────────────────────────────────────────────

@app.route("/v1beta/documents:toPage", methods=["POST"])
def document_to_page():
    """
    Convert a document to a publicly accessible HTML webpage.

    Accepts either:
      - multipart/form-data  with field `file`  (txt / md / pdf / docx)
      - application/json     with field `content` (raw text/markdown string)
        and optional field   `title`

    Returns:
      { "page_url": "https://...", "title": "..." }
    """
    text = ""
    title = "Document"

    content_type = request.content_type or ""

    if "multipart/form-data" in content_type:
        if "file" not in request.files:
            return jsonify({"error": {"code": 400, "message": "Missing `file` field"}}), 400
        f = request.files["file"]
        title = os.path.splitext(f.filename)[0] or "Document"
        suffix = os.path.splitext(f.filename)[1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            f.save(tmp.name)
            try:
                text, _ = extract_text(tmp.name, f.filename)
            except ValueError as e:
                return jsonify({"error": {"code": 400, "message": str(e)}}), 400
            finally:
                os.unlink(tmp.name)
    else:
        body = request.get_json(force=True, silent=True) or {}
        if not body.get("content"):
            return jsonify({"error": {"code": 400, "message": "Missing `content` field"}}), 400
        text  = body["content"]
        title = body.get("title", "Document")

    if not text.strip():
        return jsonify({"error": {"code": 400, "message": "Document is empty"}}), 400

    try:
        html = content_to_html(text, GEMINI_API_KEY)
    except RuntimeError as e:
        return jsonify({"error": {"code": 502, "message": str(e)}}), 502

    filename = f"{uuid.uuid4().hex}.html"
    filepath = os.path.join(IMAGE_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as out:
        out.write(html)

    page_url = f"{PUBLIC_BASE}/{filename}"
    return jsonify({"page_url": page_url, "title": title}), 200


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# ── File Management UI ────────────────────────────────────────────────────────

@app.route("/admin", methods=["GET"])
def admin_ui():
    """File management dashboard."""
    files = []
    if os.path.isdir(IMAGE_DIR):
        for fname in sorted(os.listdir(IMAGE_DIR), key=lambda f: os.path.getmtime(os.path.join(IMAGE_DIR, f)), reverse=True):
            fpath = os.path.join(IMAGE_DIR, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                ext = os.path.splitext(fname)[1].lower()
                ftype = "image" if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp") else "page" if ext == ".html" else "other"
                files.append({
                    "name": fname,
                    "url": f"{PUBLIC_BASE}/{fname}",
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "type": ftype,
                })
    html = _render_admin(files)
    from flask import Response
    return Response(html, mimetype="text/html")


@app.route("/admin/delete/<filename>", methods=["POST"])
def admin_delete(filename):
    """Delete a file."""
    safe = os.path.basename(filename)
    fpath = os.path.join(IMAGE_DIR, safe)
    if os.path.isfile(fpath):
        os.remove(fpath)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Not found"}), 404


@app.route("/admin/upload", methods=["POST"])
def admin_upload():
    """Upload a file directly to IMAGE_DIR."""
    if "file" not in request.files:
        return jsonify({"error": "Missing file"}), 400
    f = request.files["file"]
    safe = f.filename.replace("..", "").replace("/", "")
    if not safe:
        return jsonify({"error": "Invalid filename"}), 400
    f.save(os.path.join(IMAGE_DIR, safe))
    return jsonify({"ok": True, "url": f"{PUBLIC_BASE}/{safe}"})


def _fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _render_admin(files):
    import time
    rows = ""
    for f in files:
        icon = "🖼️" if f["type"] == "image" else "📄" if f["type"] == "page" else "📎"
        preview = f'<img src="{f["url"]}" style="max-height:48px;max-width:80px;border-radius:4px;object-fit:cover;" onerror="this.style.display=\'none\'">' if f["type"] == "image" else ""
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(f["mtime"]))
        rows += f"""
        <tr>
          <td style="padding:10px 8px;border-bottom:1px solid #2a2a3a">{preview or icon}</td>
          <td style="padding:10px 8px;border-bottom:1px solid #2a2a3a;word-break:break-all">
            <a href="{f['url']}" target="_blank" style="color:#7dd3fc;text-decoration:none">{f['name']}</a>
          </td>
          <td style="padding:10px 8px;border-bottom:1px solid #2a2a3a;color:#94a3b8;white-space:nowrap">{_fmt_size(f['size'])}</td>
          <td style="padding:10px 8px;border-bottom:1px solid #2a2a3a;color:#94a3b8;white-space:nowrap">{mtime}</td>
          <td style="padding:10px 8px;border-bottom:1px solid #2a2a3a">
            <button onclick="delFile('{f['name']}')" style="background:#ef4444;color:#fff;border:none;padding:4px 12px;border-radius:6px;cursor:pointer;font-size:12px">删除</button>
          </td>
        </tr>"""

    total = len(files)
    images = sum(1 for f in files if f["type"] == "image")
    pages = sum(1 for f in files if f["type"] == "page")

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>文件管理 - Media Hosting Suite</title>
<style>
  * {{ box-sizing:border-box;margin:0;padding:0 }}
  body {{ background:#0f0f1a;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh }}
  .header {{ background:linear-gradient(135deg,#1e1b4b,#312e81);padding:24px 32px;border-bottom:1px solid #2a2a4a }}
  .header h1 {{ font-size:1.6rem;font-weight:700;color:#a5b4fc }}
  .header p {{ color:#94a3b8;margin-top:4px;font-size:.9rem }}
  .container {{ max-width:1100px;margin:0 auto;padding:24px }}
  .stats {{ display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap }}
  .stat {{ background:#1a1a2e;border:1px solid #2a2a4a;border-radius:10px;padding:16px 24px;flex:1;min-width:140px }}
  .stat .num {{ font-size:2rem;font-weight:700;color:#a5b4fc }}
  .stat .label {{ color:#64748b;font-size:.85rem;margin-top:2px }}
  .card {{ background:#1a1a2e;border:1px solid #2a2a4a;border-radius:12px;overflow:hidden }}
  .card-header {{ padding:16px 20px;border-bottom:1px solid #2a2a4a;display:flex;justify-content:space-between;align-items:center }}
  .card-header h2 {{ font-size:1rem;color:#cbd5e1 }}
  .upload-btn {{ background:#6366f1;color:#fff;border:none;padding:8px 18px;border-radius:8px;cursor:pointer;font-size:.9rem }}
  .upload-btn:hover {{ background:#4f46e5 }}
  table {{ width:100%;border-collapse:collapse }}
  thead th {{ padding:10px 8px;text-align:left;font-size:.8rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #2a2a4a }}
  tbody tr:hover {{ background:#1f1f35 }}
  .empty {{ text-align:center;padding:60px;color:#475569 }}
  .modal {{ display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:100;align-items:center;justify-content:center }}
  .modal.show {{ display:flex }}
  .modal-box {{ background:#1a1a2e;border:1px solid #2a2a4a;border-radius:12px;padding:28px;max-width:400px;width:90% }}
  .modal-box h3 {{ margin-bottom:16px;color:#e2e8f0 }}
  .modal-box input[type=file] {{ width:100%;padding:10px;background:#0f0f1a;border:1px solid #3a3a5a;border-radius:8px;color:#e2e8f0;margin-bottom:16px }}
  .btn-row {{ display:flex;gap:8px;justify-content:flex-end }}
  .btn-cancel {{ background:transparent;color:#94a3b8;border:1px solid #3a3a5a;padding:8px 16px;border-radius:8px;cursor:pointer }}
  .btn-upload {{ background:#6366f1;color:#fff;border:none;padding:8px 16px;border-radius:8px;cursor:pointer }}
</style>
</head>
<body>
<div class="header">
  <h1>📁 Media Hosting Suite — 文件管理</h1>
  <p>管理所有生成的图片和网页文件 · <a href="{PUBLIC_BASE}" target="_blank" style="color:#7dd3fc">访问静态根目录 ↗</a></p>
</div>
<div class="container">
  <div class="stats">
    <div class="stat"><div class="num">{total}</div><div class="label">文件总数</div></div>
    <div class="stat"><div class="num">{images}</div><div class="label">图片</div></div>
    <div class="stat"><div class="num">{pages}</div><div class="label">HTML 页面</div></div>
  </div>
  <div class="card">
    <div class="card-header">
      <h2>所有文件</h2>
      <button class="upload-btn" onclick="document.getElementById('uploadModal').classList.add('show')">⬆ 上传文件</button>
    </div>
    <table>
      <thead><tr><th>预览</th><th>文件名</th><th>大小</th><th>时间</th><th>操作</th></tr></thead>
      <tbody>{"<tr><td colspan='5' class='empty'>暂无文件</td></tr>" if not rows else rows}</tbody>
    </table>
  </div>
</div>

<!-- Upload Modal -->
<div class="modal" id="uploadModal">
  <div class="modal-box">
    <h3>上传文件</h3>
    <input type="file" id="uploadInput" accept="image/*,.html,.pdf,.docx,.txt,.md">
    <div class="btn-row">
      <button class="btn-cancel" onclick="document.getElementById('uploadModal').classList.remove('show')">取消</button>
      <button class="btn-upload" onclick="doUpload()">上传</button>
    </div>
  </div>
</div>

<script>
async function delFile(name) {{
  if (!confirm('确认删除 ' + name + ' ?')) return;
  const r = await fetch('/admin/delete/' + name, {{method:'POST'}});
  const d = await r.json();
  if (d.ok) location.reload();
  else alert('删除失败: ' + (d.error||'未知错误'));
}}
async function doUpload() {{
  const input = document.getElementById('uploadInput');
  if (!input.files.length) {{ alert('请选择文件'); return; }}
  const fd = new FormData();
  fd.append('file', input.files[0]);
  const r = await fetch('/admin/upload', {{method:'POST', body:fd}});
  const d = await r.json();
  if (d.ok) {{ location.reload(); }}
  else alert('上传失败: ' + (d.error||'未知'));
}}
</script>
</body>
</html>"""


if __name__ == "__main__":
    os.makedirs(IMAGE_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=1002, debug=False)
