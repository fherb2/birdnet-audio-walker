"""
CKEditor 5 – absolut minimale Test-App
=======================================
Keine externen Abhängigkeiten – nur Python 3 Bordmittel.

Starten:   python ckeditor_test.py
Browser:   http://localhost:8080
"""

from http.server import HTTPServer, BaseHTTPRequestHandler

HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>CKEditor Test</title>
  <link rel="stylesheet"
    href="https://cdn.ckeditor.com/ckeditor5/41.4.2/classic/ckeditor.css">
  <script
    src="https://cdn.ckeditor.com/ckeditor5/41.4.2/classic/ckeditor.js">
  </script>
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    .ck-editor__editable { min-height: 400px; }
    button {
      margin: 4px; padding: 8px 16px; color: white;
      border: none; border-radius: 4px; cursor: pointer; font-size: 14px;
    }
    #msg {
      margin: 8px 0; padding: 8px; background: #e8f5e9;
      border-radius: 4px; display: none;
    }
  </style>
</head>
<body>
  <h2>CKEditor 5 Test</h2>

  <div style="margin-bottom: 8px">
    <button style="background:#1976d2" onclick="zeigeHTML()">HTML anzeigen</button>
    <button style="background:#388e3c" onclick="exportHTML()">Export</button>
    <button style="background:#c62828" onclick="leereEditor()">Leeren</button>
  </div>

  <div id="msg"></div>
  <div id="editor">
    <h2>Testdokument</h2>
    <p>Hier tippen, Bilder einfügen, Tabellen anlegen...</p>
    <figure class="table"><table>
      <thead><tr><th>Vogelart</th><th>Anzahl</th><th>Uhrzeit</th></tr></thead>
      <tbody>
        <tr><td>Amsel</td><td>3</td><td>07:30</td></tr>
        <tr><td>Kohlmeise</td><td>5</td><td>08:15</td></tr>
      </tbody>
    </table></figure>
  </div>

  <script>
    var editor;
    var STORAGE_KEY = "birdnet_ck";

    ClassicEditor.create(document.getElementById("editor"), {
      licenseKey: "GPL",
      toolbar: {
        items: [
          "heading","|","bold","italic","underline","strikethrough","|",
          "bulletedList","numberedList","todoList","|",
          "insertTable","|","uploadImage","link","|",
          "blockQuote","code","codeBlock","|",
          "undo","redo","|","sourceEditing"
        ],
        shouldNotGroupWhenFull: true
      },
      table: {
        contentToolbar: ["tableColumn","tableRow","mergeTableCells"]
      }
    })
    .then(function(ed) {
      editor = ed;

      // localStorage wiederherstellen
      var saved = localStorage.getItem(STORAGE_KEY);
      if (saved) editor.setData(saved);

      // Autosave
      editor.model.document.on("change:data", function() {
        localStorage.setItem(STORAGE_KEY, editor.getData());
      });

      // Base64-Bilder direkt einbetten
      editor.plugins.get("FileRepository").createUploadAdapter = function(loader) {
        return { upload: function() {
          return loader.file.then(function(file) {
            return new Promise(function(res, rej) {
              var r = new FileReader();
              r.onload  = function(e) { res({ default: e.target.result }); };
              r.onerror = rej;
              r.readAsDataURL(file);
            });
          });
        }};
      };

      msg("✅ Editor bereit.", false);
    })
    .catch(function(e) { msg("❌ Fehler: " + e, true); });

    function msg(text, err) {
      var el = document.getElementById("msg");
      el.style.display = "block";
      el.style.background = err ? "#fdecea" : "#e8f5e9";
      el.textContent = text;
    }

    function zeigeHTML() {
      if (!editor) { msg("Editor nicht bereit.", true); return; }
      var html = editor.getData();
      msg("HTML (" + (html.length/1024).toFixed(1) + " KB): " + html.substring(0,200) + "...", false);
    }

    function exportHTML() {
      if (!editor) { msg("Editor nicht bereit.", true); return; }
      var html = editor.getData();
      var full = "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        + "<style>body{font-family:Arial;margin:2cm}"
        + "table{border-collapse:collapse;width:100%}"
        + "td,th{border:1px solid #aaa;padding:5pt}"
        + "img{max-width:100%}</style></head><body>"
        + html + "</body></html>";
      var blob = new Blob([full], {type:"text/html"});
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "beobachtung.html";
      a.click();
      msg("✅ Download gestartet. Datei öffnen → Strg+P → Als PDF speichern.", false);
    }

    function leereEditor() {
      if (!editor) { msg("Editor nicht bereit.", true); return; }
      localStorage.removeItem(STORAGE_KEY);
      editor.setData("<p>Geleert.</p>");
      msg("Geleert.", false);
    }
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Konsole sauber halten


print("Server läuft auf http://localhost:8080  –  Strg+C zum Beenden")
HTTPServer(("", 8080), Handler).serve_forever()