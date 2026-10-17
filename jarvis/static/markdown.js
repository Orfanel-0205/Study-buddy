/* A small, safe Markdown renderer for Jarvis chat messages.
 *
 * Safety: all text is HTML-escaped first and only the tags generated here are
 * produced, so model output can never inject scripts or HTML. Links are only
 * allowed for http(s) and mailto URLs.
 *
 * It also detects which file a code block belongs to ("File: src/app.py" on
 * the line above, or ```python src/app.py) so Jarvis can offer to apply it.
 */
(function (root) {
  "use strict";

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  var PATH_RE = /^[\w@.\-\/\\ ]*[\w\-]\.[\w]+$|^[\w@.\-\/\\]*(?:Dockerfile|Makefile|Procfile|Gemfile|Rakefile|\.gitignore|\.env\.example)$/;

  function cleanPath(p) {
    if (!p) return "";
    p = p.trim().replace(/^[`*_"']+|[`*_"':]+$/g, "").trim().replace(/\\/g, "/").replace(/^\.\//, "");
    if (!p || p.length > 200 || /\s/.test(p) || p.indexOf("..") !== -1 || /^[a-z]+:\/\//i.test(p)) return "";
    return PATH_RE.test(p) ? p : "";
  }

  /* Look at the line right above a code block for a file path. */
  function pathFromLine(line) {
    if (!line) return "";
    var m = line.match(/^\s*(?:[#>*\-\s]*)?(?:\*\*|__)?\s*(?:File|Filename|Path|Create|Update|Modify|Save as)\s*(?:name)?\s*:?\s*(?:\*\*|__)?\s*:?\s*(.+?)\s*$/i);
    if (m) {
      var p = cleanPath(m[1]);
      if (p) return p;
    }
    m = line.match(/^\s*(?:#{1,6}\s*)?(?:\d+\.\s*)?(?:\*\*|__|`)+\s*([^`*]+?)\s*(?:\*\*|__|`)+\s*:?\s*$/);
    if (m) return cleanPath(m[1]);
    return "";
  }

  function pathFromInfo(info) {
    // ```python src/app.py   ```python:src/app.py   ```python title="src/app.py"
    var m = info.match(/(?:title|file|filename|path)\s*=\s*["']?([^"'\s]+)/i);
    if (m) return cleanPath(m[1]);
    var rest = info.replace(/^[\w+#.\-]+[:\s]?/, "");
    return cleanPath(rest);
  }

  function renderInline(text) {
    var codes = [];
    var s = escapeHtml(text).replace(/`([^`\n]+)`/g, function (_, c) {
      codes.push("<code>" + c + "</code>");
      return "\u0000" + (codes.length - 1) + "\u0000";
    });
    s = s.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, function (all, label, url) {
      var decoded = url.replace(/&amp;/g, "&");
      if (!/^(https?:\/\/|mailto:)/i.test(decoded)) return label;
      return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + label + "</a>";
    });
    s = s.replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[\s(])__([^_\n]+?)__(?=[\s).,;:!?]|$)/g, "$1<strong>$2</strong>");
    s = s.replace(/(^|[^*\w])\*([^*\s][^*\n]*?)\*(?!\*)/g, "$1<em>$2</em>");
    s = s.replace(/(^|[\s(])_([^_\s][^_\n]*?)_(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>");
    s = s.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
    s = s.replace(/\u0000(\d+)\u0000/g, function (_, i) { return codes[+i]; });
    return s;
  }

  function codeBlock(code, lang, path, open) {
    var safeLang = /^[\w+#.\-]{1,20}$/.test(lang) ? lang.toLowerCase() : "";
    var shell = /^(bash|sh|shell|zsh|console|powershell|ps1|pwsh|cmd|bat|terminal)$/.test(safeLang);
    var attrs = ' data-lang="' + escapeHtml(safeLang) + '"' + (path ? ' data-path="' + escapeHtml(path) + '"' : "") +
      (shell ? ' data-shell="1"' : "") + (open ? ' data-open="1"' : "");
    return '<div class="codeblock"' + attrs + '><div class="codebar"><span class="codelang">' +
      escapeHtml(path || safeLang || "code") + '</span><span class="codeactions"></span></div><pre><code' +
      (safeLang ? ' class="lang-' + escapeHtml(safeLang) + '"' : "") + ">" + escapeHtml(code) + "</code></pre></div>";
  }

  function isTableSep(line) {
    return /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line) && line.indexOf("-") !== -1;
  }

  function splitRow(line) {
    var t = line.trim().replace(/^\|/, "").replace(/\|$/, "");
    return t.split("|").map(function (c) { return c.trim(); });
  }

  function renderList(lines) {
    // lines: [{indent, ordered, text}] -> nested lists by indentation
    var html = "";
    var stack = [];
    lines.forEach(function (item) {
      while (stack.length && item.indent < stack[stack.length - 1].indent) {
        html += "</li></" + stack.pop().tag + ">";
      }
      var top = stack[stack.length - 1];
      if (top && item.indent === top.indent && top.tag !== (item.ordered ? "ol" : "ul")) {
        html += "</li></" + stack.pop().tag + ">"; // bullets followed by numbers: start a new list
        top = stack[stack.length - 1];
      }
      if (!top || item.indent > top.indent) {
        var tag = item.ordered ? "ol" : "ul";
        var start = item.ordered && item.num > 1 ? ' start="' + item.num + '"' : "";
        html += "<" + tag + start + "><li>";
        stack.push({ indent: item.indent, tag: tag });
      } else {
        html += "</li><li>";
      }
      html += renderInline(item.text);
    });
    while (stack.length) html += "</li></" + stack.pop().tag + ">";
    return html;
  }

  function renderMarkdown(src) {
    var lines = String(src || "").replace(/\r\n?/g, "\n").split("\n");
    var out = [];
    var para = [];
    var i = 0;

    function flushPara() {
      if (para.length) {
        out.push("<p>" + para.map(renderInline).join("<br>") + "</p>");
        para = [];
      }
    }
    function prevTextLine() {
      // the last non-empty source line before the fence (for "File: x" hints)
      for (var j = i - 1; j >= 0; j--) {
        if (lines[j].trim()) return lines[j];
      }
      return "";
    }

    while (i < lines.length) {
      var line = lines[i];
      var fence = line.match(/^\s*(`{3,}|~{3,})\s*(.*)$/);
      if (fence) {
        flushPara();
        var marker = fence[1];
        var info = fence[2].trim();
        var lang = (info.split(/[\s:{]/)[0] || "").trim();
        var path = pathFromInfo(info) || pathFromLine(prevTextLine());
        var body = [];
        i++;
        var closed = false;
        while (i < lines.length) {
          var closeRe = new RegExp("^\\s*" + marker[0] + "{" + marker.length + ",}\\s*$");
          if (closeRe.test(lines[i])) { closed = true; i++; break; }
          body.push(lines[i]);
          i++;
        }
        out.push(codeBlock(body.join("\n"), lang, path, !closed));
        continue;
      }
      if (!line.trim()) { flushPara(); i++; continue; }

      var h = line.match(/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/);
      if (h) {
        flushPara();
        var level = Math.min(h[1].length + 1, 6); // h1 in a message would be too loud
        out.push("<h" + level + ">" + renderInline(h[2]) + "</h" + level + ">");
        i++;
        continue;
      }
      if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) { flushPara(); out.push("<hr>"); i++; continue; }

      if (/^\s*>/.test(line)) {
        flushPara();
        var quote = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) {
          quote.push(lines[i].replace(/^\s*>\s?/, ""));
          i++;
        }
        out.push("<blockquote>" + renderMarkdown(quote.join("\n")) + "</blockquote>");
        continue;
      }

      if (line.indexOf("|") !== -1 && i + 1 < lines.length && isTableSep(lines[i + 1])) {
        flushPara();
        var head = splitRow(line);
        var rows = [];
        i += 2;
        while (i < lines.length && lines[i].indexOf("|") !== -1 && lines[i].trim()) {
          rows.push(splitRow(lines[i]));
          i++;
        }
        var t = '<div class="tablewrap"><table><thead><tr>' + head.map(function (c) { return "<th>" + renderInline(c) + "</th>"; }).join("") + "</tr></thead><tbody>";
        rows.forEach(function (r) {
          t += "<tr>" + head.map(function (_, k) { return "<td>" + renderInline(r[k] || "") + "</td>"; }).join("") + "</tr>";
        });
        out.push(t + "</tbody></table></div>");
        continue;
      }

      var li = line.match(/^(\s*)([-*+]|(\d+)[.)])\s+(.*)$/);
      if (li) {
        flushPara();
        var items = [];
        while (i < lines.length) {
          var m = lines[i].match(/^(\s*)([-*+]|(\d+)[.)])\s+(.*)$/);
          if (m) {
            var task = m[4].match(/^\[( |x|X)\]\s+(.*)$/);
            var text = task ? (task[1] === " " ? "☐ " : "☑ ") + task[2] : m[4];
            items.push({ indent: m[1].replace(/\t/g, "    ").length, ordered: !!m[3], num: m[3] ? +m[3] : 0, text: text });
            i++;
          } else if (lines[i].trim() && /^\s{2,}\S/.test(lines[i]) && items.length) {
            items[items.length - 1].text += " " + lines[i].trim(); // continuation line
            i++;
          } else {
            break;
          }
        }
        out.push(renderList(items));
        continue;
      }

      para.push(line.trim());
      i++;
    }
    flushPara();
    return out.join("\n");
  }

  /* Plain text for "read aloud": drop code blocks and markup. */
  function toSpeech(src) {
    return String(src || "")
      .replace(/```[\s\S]*?(```|$)/g, " (code block omitted) ")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/[#*_>|~]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  var api = { renderMarkdown: renderMarkdown, escapeHtml: escapeHtml, pathFromLine: pathFromLine, toSpeech: toSpeech };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisMarkdown = api;
})(this);
