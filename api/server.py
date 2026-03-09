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
PUBLIC_BASE    = os.environ.get("PUBLIC_BASE", "")
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
    import time, json
    rows = ""
    for f in files:
        # 缩略图
        if f["type"] == "image":
            thumb = f'<img src="{f["url"]}" class="thumb" onclick="openPreview({json.dumps(f["url"])},{json.dumps(f["name"])},{json.dumps(f["type"])})" onerror="this.outerHTML=\'🖼️\'">'
        elif f["type"] == "page":
            thumb = f'<span class="icon-btn" onclick="openPreview({json.dumps(f["url"])},{json.dumps(f["name"])},{json.dumps(f["type"])})">📄</span>'
        else:
            thumb = "📎"

        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(f["mtime"]))
        # URL 复制按钮
        url_cell = f'''<div class="url-row">
            <span class="url-text">{f["url"]}</span>
            <button class="copy-btn" onclick="copyUrl({json.dumps(f["url"])},this)" title="复制链接">⎘</button>
          </div>'''
        rows += f"""
        <tr>
          <td class="td-thumb">{thumb}</td>
          <td class="td-name">
            <a href="{f['url']}" target="_blank" class="fname">{f['name']}</a>
            {url_cell}
          </td>
          <td class="td-meta">{_fmt_size(f['size'])}</td>
          <td class="td-meta">{mtime}</td>
          <td class="td-action">
            <button onclick="openPreview({json.dumps(f['url'])},{json.dumps(f['name'])},{json.dumps(f['type'])})" class="btn-preview">预览</button>
            <button onclick="delFile({json.dumps(f['name'])})" class="btn-del">删除</button>
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
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0f0f1a;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh}}
  .header{{background:linear-gradient(135deg,#1e1b4b,#312e81);padding:24px 32px;border-bottom:1px solid #2a2a4a}}
  .header h1{{font-size:1.5rem;font-weight:700;color:#a5b4fc}}
  .header p{{color:#94a3b8;margin-top:4px;font-size:.9rem}}
  .container{{max-width:1200px;margin:0 auto;padding:24px}}
  .stats{{display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap}}
  .stat{{background:#1a1a2e;border:1px solid #2a2a4a;border-radius:10px;padding:16px 24px;flex:1;min-width:130px}}
  .stat .num{{font-size:2rem;font-weight:700;color:#a5b4fc}}
  .stat .label{{color:#64748b;font-size:.85rem;margin-top:2px}}
  .card{{background:#1a1a2e;border:1px solid #2a2a4a;border-radius:12px;overflow:hidden}}
  .card-header{{padding:16px 20px;border-bottom:1px solid #2a2a4a;display:flex;justify-content:space-between;align-items:center}}
  .card-header h2{{font-size:1rem;color:#cbd5e1}}
  .upload-btn{{background:#6366f1;color:#fff;border:none;padding:8px 18px;border-radius:8px;cursor:pointer;font-size:.9rem}}
  .upload-btn:hover{{background:#4f46e5}}
  table{{width:100%;border-collapse:collapse}}
  thead th{{padding:10px 8px;text-align:left;font-size:.75rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #2a2a4a}}
  tbody tr{{border-bottom:1px solid #1e1e30}}
  tbody tr:hover{{background:#1c1c32}}
  .td-thumb{{padding:8px;width:72px}}
  .td-name{{padding:8px 12px}}
  .td-meta{{padding:8px;color:#64748b;font-size:.85rem;white-space:nowrap}}
  .td-action{{padding:8px;white-space:nowrap}}
  .thumb{{width:60px;height:60px;object-fit:cover;border-radius:6px;cursor:zoom-in;border:1px solid #2a2a4a;transition:.2s;display:block}}
  .thumb:hover{{transform:scale(1.08);border-color:#6366f1}}
  .icon-btn{{font-size:1.8rem;cursor:pointer}}
  .fname{{color:#7dd3fc;text-decoration:none;font-size:.9rem;font-weight:500;display:block;margin-bottom:4px}}
  .fname:hover{{color:#bae6fd}}
  .url-row{{display:flex;align-items:center;gap:6px}}
  .url-text{{font-size:.75rem;color:#475569;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:420px}}
  .copy-btn{{background:transparent;border:1px solid #3a3a5a;color:#94a3b8;border-radius:5px;padding:2px 8px;cursor:pointer;font-size:.85rem;flex-shrink:0;transition:.15s}}
  .copy-btn:hover{{background:#6366f1;border-color:#6366f1;color:#fff}}
  .copy-btn.copied{{background:#22c55e;border-color:#22c55e;color:#fff}}
  .btn-preview{{background:transparent;border:1px solid #6366f1;color:#a5b4fc;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:.8rem;margin-right:4px}}
  .btn-preview:hover{{background:#6366f1;color:#fff}}
  .btn-del{{background:transparent;border:1px solid #ef4444;color:#f87171;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:.8rem}}
  .btn-del:hover{{background:#ef4444;color:#fff}}
  .empty{{text-align:center;padding:60px;color:#475569}}
  /* Upload modal */
  .modal{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:100;align-items:center;justify-content:center}}
  .modal.show{{display:flex}}
  .modal-box{{background:#1a1a2e;border:1px solid #2a2a4a;border-radius:12px;padding:28px;width:90%;max-width:420px}}
  .modal-box h3{{margin-bottom:16px;color:#e2e8f0}}
  .modal-box input[type=file]{{width:100%;padding:10px;background:#0f0f1a;border:1px solid #3a3a5a;border-radius:8px;color:#e2e8f0;margin-bottom:16px}}
  .btn-row{{display:flex;gap:8px;justify-content:flex-end}}
  .btn-cancel{{background:transparent;color:#94a3b8;border:1px solid #3a3a5a;padding:8px 16px;border-radius:8px;cursor:pointer}}
  .btn-upload{{background:#6366f1;color:#fff;border:none;padding:8px 16px;border-radius:8px;cursor:pointer}}
  /* Preview modal */
  .preview-modal{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:200;flex-direction:column;align-items:center;justify-content:center}}
  .preview-modal.show{{display:flex}}
  .preview-header{{position:absolute;top:0;left:0;right:0;padding:12px 20px;background:rgba(15,15,26,.9);display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #2a2a4a}}
  .preview-title{{color:#e2e8f0;font-size:.9rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:70%}}
  .preview-actions{{display:flex;gap:8px;align-items:center}}
  .preview-img{{max-width:90vw;max-height:85vh;border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,.8)}}
  .preview-iframe{{width:90vw;height:85vh;border:none;border-radius:8px;background:#fff;margin-top:52px}}
  .close-btn{{background:transparent;border:1px solid #4a4a6a;color:#94a3b8;border-radius:6px;padding:5px 14px;cursor:pointer;font-size:.85rem}}
  .close-btn:hover{{background:#ef4444;border-color:#ef4444;color:#fff}}
  .prev-copy-btn{{background:#6366f1;border:none;color:#fff;border-radius:6px;padding:5px 14px;cursor:pointer;font-size:.85rem}}
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
      <thead><tr><th>缩略图</th><th>文件名 / 访问地址</th><th>大小</th><th>时间</th><th>操作</th></tr></thead>
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

<!-- Preview Modal -->
<div class="preview-modal" id="previewModal" onclick="closePreviewIfBg(event)">
  <div class="preview-header">
    <span class="preview-title" id="previewTitle"></span>
    <div class="preview-actions">
      <button class="prev-copy-btn" id="previewCopyBtn" onclick="copyPreviewUrl()">⎘ 复制链接</button>
      <a id="previewOpenLink" href="#" target="_blank"><button class="prev-copy-btn" style="background:#0ea5e9">↗ 新窗口打开</button></a>
      <button class="close-btn" onclick="closePreview()">✕ 关闭</button>
    </div>
  </div>
  <div id="previewContent" style="margin-top:52px;display:flex;align-items:center;justify-content:center"></div>
</div>

<script>
let _previewUrl = '';

function openPreview(url, name, type) {{
  _previewUrl = url;
  document.getElementById('previewTitle').textContent = name;
  document.getElementById('previewOpenLink').href = url;
  document.getElementById('previewCopyBtn').textContent = '⎘ 复制链接';
  document.getElementById('previewCopyBtn').style.background = '#6366f1';
  const box = document.getElementById('previewContent');
  if (type === 'image') {{
    box.innerHTML = '<img class="preview-img" src="' + url + '" alt="' + name + '">';
  }} else if (type === 'page') {{
    box.innerHTML = '<iframe class="preview-iframe" src="' + url + '"></iframe>';
    box.firstChild.style.marginTop = '0';
    box.style.marginTop = '52px';
  }} else {{
    box.innerHTML = '<p style="color:#94a3b8">该文件类型暂不支持预览</p>';
  }}
  document.getElementById('previewModal').classList.add('show');
  document.body.style.overflow = 'hidden';
}}

function closePreview() {{
  document.getElementById('previewModal').classList.remove('show');
  document.getElementById('previewContent').innerHTML = '';
  document.body.style.overflow = '';
}}

function closePreviewIfBg(e) {{
  if (e.target === document.getElementById('previewModal')) closePreview();
}}

function copyPreviewUrl() {{
  navigator.clipboard.writeText(_previewUrl).then(() => {{
    const btn = document.getElementById('previewCopyBtn');
    btn.textContent = '✓ 已复制';
    btn.style.background = '#22c55e';
    setTimeout(() => {{ btn.textContent = '⎘ 复制链接'; btn.style.background = '#6366f1'; }}, 2000);
  }});
}}

function copyUrl(url, btn) {{
  navigator.clipboard.writeText(url).then(() => {{
    btn.textContent = '✓';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = '⎘'; btn.classList.remove('copied'); }}, 2000);
  }});
}}

async function delFile(name) {{
  if (!confirm('确认删除 ' + name + ' ?')) return;
  const r = await fetch('/admin/delete/' + name, {{method:'POST'}});
  const d = await r.json();
  if (d.ok) location.reload();
  else alert('删除失败: ' + (d.error || '未知'));
}}

async function doUpload() {{
  const input = document.getElementById('uploadInput');
  if (!input.files.length) {{ alert('请选择文件'); return; }}
  const fd = new FormData();
  fd.append('file', input.files[0]);
  const r = await fetch('/admin/upload', {{method:'POST', body:fd}});
  const d = await r.json();
  if (d.ok) location.reload();
  else alert('上传失败: ' + (d.error || '未知'));
}}

document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closePreview(); }});
</script>
</body>
</html>"""


if __name__ == "__main__":
    os.makedirs(IMAGE_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=1002, debug=False)
