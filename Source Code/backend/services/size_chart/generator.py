import csv
from pathlib import Path
from html import escape

def generate_html(title, columns, rows, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    th = "".join(f"<th>{escape(str(c))}</th>" for c in columns)
    trs = []
    for row in rows:
        trs.append("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in row) + "</tr>")
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>
body{{font-family:Arial,sans-serif;margin:30px;background:#f7f7f7;color:#222}}
.card{{background:#fff;padding:24px;border-radius:12px;box-shadow:0 2px 12px #0001}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ddd;padding:9px;text-align:center}}
th{{background:#111;color:#fff}}
</style></head><body><div class="card">
<h2>{escape(title)}</h2><table><thead><tr>{th}</tr></thead><tbody>
{''.join(trs)}
</tbody></table></div></body></html>"""
    path.write_text(html, encoding="utf-8")
    return path
