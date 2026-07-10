"""Inspect and visualize metadata for each stream in an XDF file."""

import argparse
import html
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pyxdf

SCRIPT_DIR = Path(__file__).resolve().parent

# ============================================================
#  Settings — edit these paths, then run this script.
#  Example: python inspect_streams.py
# ============================================================
INPUT_XDF = SCRIPT_DIR / "newtest.xdf"
OUTPUT_HTML = ""  # leave blank for <recording>_metadata.html in this folder
# ============================================================


def normalize(value):
    """Convert pyxdf/numpy structures to JSON-serializable Python values."""
    if isinstance(value, defaultdict):
        value = dict(value)
    if isinstance(value, dict):
        return {str(k): normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return {
            "dtype": str(value.dtype),
            "shape": list(value.shape),
            "preview": value.flatten()[:5].tolist(),
        }
    return value


def summarize_arrays(stream):
    """Summarize sample arrays without dumping full recordings."""
    summary = {}

    data = stream.get("time_series")
    if data is not None:
        arr = np.asarray(data)
        summary["time_series"] = {
            "dtype": str(arr.dtype),
            "shape": list(arr.shape),
            "sample_count": int(arr.shape[0]) if arr.ndim >= 1 else int(arr.size),
        }

    timestamps = stream.get("time_stamps")
    if timestamps is not None:
        ts = np.asarray(timestamps)
        summary["time_stamps"] = {
            "count": int(len(ts)),
            "first": float(ts[0]) if len(ts) else None,
            "last": float(ts[-1]) if len(ts) else None,
            "duration_s": float(ts[-1] - ts[0]) if len(ts) > 1 else 0.0,
        }

    clock_times = stream.get("clock_times")
    clock_values = stream.get("clock_values")
    if clock_times is not None and len(clock_times) > 0:
        summary["clock_times"] = normalize(clock_times)
        summary["clock_values"] = normalize(clock_values)

    return summary


def unwrap_lsl_value(value):
    """LSL metadata fields are often single-element lists."""
    if isinstance(value, list) and len(value) == 1:
        return value[0]
    return value


def format_display_value(value):
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if abs(value) >= 1000 or (0 < abs(value) < 0.001):
            return f"{value:.6g}"
        return f"{value:.6f}".rstrip("0").rstrip(".")
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        if all(not isinstance(item, (dict, list)) for item in value):
            return ", ".join(format_display_value(item) for item in value)
    if isinstance(value, dict):
        return f"{{ {len(value)} fields }}"
    return str(value)


def render_metadata_rows(data, prefix=""):
    rows = []

    if isinstance(data, dict):
        for key in sorted(data.keys(), key=str):
            full_key = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(render_metadata_rows(data[key], full_key))
        return rows

    if isinstance(data, list):
        if not data:
            rows.append((prefix, "[]"))
            return rows

        if all(isinstance(item, dict) for item in data):
            for index, item in enumerate(data):
                item_prefix = f"{prefix}[{index}]"
                rows.extend(render_metadata_rows(item, item_prefix))
            return rows

        rows.append((prefix, format_display_value(data)))
        return rows

    rows.append((prefix, format_display_value(data)))
    return rows


def render_metadata_table(data, table_class="meta-table"):
    rows = render_metadata_rows(data)
    if not rows:
        return '<p class="empty">No metadata.</p>'

    body = "\n".join(
        f"<tr><th>{html.escape(key)}</th><td>{html.escape(value)}</td></tr>"
        for key, value in rows
    )
    return (
        f'<table class="{table_class}">'
        "<thead><tr><th>Field</th><th>Value</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def stream_title(stream):
    info = stream.get("info", {})
    return str(unwrap_lsl_value(info.get("name", f"Stream {stream['index']}")))


def stream_badges(stream):
    info = stream.get("info", {})
    summary = stream.get("data_summary", {})
    badges = [
        ("Type", unwrap_lsl_value(info.get("type", "—"))),
        ("Channels", unwrap_lsl_value(info.get("channel_count", "—"))),
        (
            "Sample rate",
            f"{format_display_value(unwrap_lsl_value(info.get('nominal_srate', '—')))} Hz",
        ),
        (
            "Samples",
            summary.get("time_stamps", {}).get("count", "—"),
        ),
    ]

    effective_srate = info.get("effective_srate")
    if effective_srate not in (None, 0, "0"):
        badges.append(("Effective rate", f"{format_display_value(effective_srate)} Hz"))

    duration = summary.get("time_stamps", {}).get("duration_s")
    if duration:
        badges.append(("Duration", f"{duration:.2f} s"))

    return badges


def render_stream_section(stream):
    index = stream["index"]
    title = stream_title(stream)
    badges = stream_badges(stream)
    badge_html = "".join(
        f'<span class="badge"><span class="badge-label">{html.escape(str(label))}</span>'
        f'<span class="badge-value">{html.escape(str(value))}</span></span>'
        for label, value in badges
    )

    return f"""
    <section class="stream-card" id="stream-{index}" data-name="{html.escape(title.lower())}">
      <div class="stream-header">
        <div>
          <p class="stream-index">Stream {index}</p>
          <h2>{html.escape(title)}</h2>
        </div>
        <div class="badge-row">{badge_html}</div>
      </div>

      <details open>
        <summary>Stream info</summary>
        {render_metadata_table(stream.get("info", {}))}
      </details>

      <details>
        <summary>Footer</summary>
        {render_metadata_table(stream.get("footer", {}))}
      </details>

      <details open>
        <summary>Data summary</summary>
        {render_metadata_table(stream.get("data_summary", {}))}
      </details>
    </section>
    """


def render_html_report(report):
    file_name = Path(report["file"]).name
    header_info = report.get("header", {}).get("info", {})
    xdf_version = format_display_value(unwrap_lsl_value(header_info.get("version", "—")))
    recorded_at = format_display_value(unwrap_lsl_value(header_info.get("datetime", "—")))
    header_table = render_metadata_table(report.get("header", {}))

    nav_links = "".join(
        f'<a href="#stream-{stream["index"]}" class="nav-link">'
        f'<span class="nav-index">{stream["index"]}</span>'
        f'<span class="nav-name">{html.escape(stream_title(stream))}</span>'
        f'<span class="nav-type">{html.escape(str(unwrap_lsl_value(stream["info"].get("type", ""))))}</span>'
        f"</a>"
        for stream in report["streams"]
    )

    stream_sections = "".join(render_stream_section(stream) for stream in report["streams"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>XDF Metadata · {html.escape(file_name)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --ink: #1f1d1a;
      --muted: #6f675d;
      --line: #ddd4c4;
      --accent: #9a3412;
      --accent-soft: #fde8d8;
      --shadow: 0 10px 30px rgba(31, 29, 26, 0.06);
    }}

    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #fff8ef 0, transparent 28%),
        linear-gradient(180deg, #efe7d7 0%, var(--bg) 24%, #f8f5ef 100%);
    }}

    .layout {{
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      min-height: 100vh;
    }}

    .sidebar {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      padding: 24px 18px;
      border-right: 1px solid var(--line);
      background: rgba(255, 253, 248, 0.92);
      backdrop-filter: blur(8px);
    }}

    .content {{
      padding: 28px 32px 48px;
      max-width: 1100px;
    }}

    h1, h2 {{
      margin: 0;
      font-weight: 600;
      letter-spacing: -0.02em;
    }}

    h1 {{ font-size: 2rem; }}
    h2 {{ font-size: 1.45rem; }}

    .eyebrow {{
      margin: 0 0 8px;
      font-size: 0.78rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
    }}

    .hero, .stream-card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }}

    .hero {{
      padding: 24px 26px;
      margin-bottom: 22px;
    }}

    .hero-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-top: 18px;
    }}

    .stat {{
      padding: 14px 16px;
      border-radius: 14px;
      background: #f7f1e7;
      border: 1px solid #eadfce;
    }}

    .stat-label {{
      display: block;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 6px;
    }}

    .stat-value {{
      font-size: 1.05rem;
      word-break: break-word;
    }}

    .search {{
      width: 100%;
      margin: 18px 0 14px;
      padding: 11px 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fff;
      font: inherit;
    }}

    .nav-link {{
      display: grid;
      grid-template-columns: 28px 1fr;
      gap: 2px 10px;
      padding: 10px 12px;
      margin-bottom: 8px;
      border-radius: 12px;
      text-decoration: none;
      color: inherit;
      border: 1px solid transparent;
    }}

    .nav-link:hover, .nav-link.active {{
      background: var(--accent-soft);
      border-color: #f5c7a8;
    }}

    .nav-index {{
      grid-row: span 2;
      display: grid;
      place-items: center;
      width: 28px;
      height: 28px;
      border-radius: 999px;
      background: #efe4d4;
      font-size: 0.82rem;
      font-weight: 700;
    }}

    .nav-name {{
      font-weight: 600;
      line-height: 1.2;
    }}

    .nav-type {{
      color: var(--muted);
      font-size: 0.86rem;
    }}

    .stream-card {{
      padding: 22px 24px;
      margin-bottom: 18px;
      scroll-margin-top: 24px;
    }}

    .stream-header {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: start;
      margin-bottom: 14px;
    }}

    .stream-index {{
      margin: 0 0 4px;
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}

    .badge-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
      max-width: 520px;
    }}

    .badge {{
      display: inline-flex;
      flex-direction: column;
      gap: 2px;
      padding: 8px 10px;
      border-radius: 12px;
      background: #f7f1e7;
      border: 1px solid #eadfce;
      min-width: 88px;
    }}

    .badge-label {{
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}

    .badge-value {{
      font-size: 0.92rem;
      font-weight: 600;
    }}

    details {{
      margin-top: 12px;
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
      background: #fff;
    }}

    summary {{
      cursor: pointer;
      list-style: none;
      padding: 12px 14px;
      font-weight: 600;
      background: #f8f2e8;
      border-bottom: 1px solid transparent;
    }}

    details[open] summary {{
      border-bottom-color: var(--line);
    }}

    summary::-webkit-details-marker {{ display: none; }}

    .meta-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.94rem;
    }}

    .meta-table th,
    .meta-table td {{
      padding: 10px 14px;
      border-top: 1px solid #eee4d7;
      vertical-align: top;
      text-align: left;
    }}

    .meta-table th {{
      width: 34%;
      color: var(--muted);
      font-weight: 600;
      background: #fcfaf6;
    }}

    .meta-table tr:first-child th,
    .meta-table tr:first-child td {{
      border-top: none;
    }}

    .empty {{
      margin: 0;
      padding: 14px;
      color: var(--muted);
    }}

    .hidden {{ display: none !important; }}

    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .sidebar {{
        position: static;
        height: auto;
        border-right: none;
        border-bottom: 1px solid var(--line);
      }}
      .stream-header {{ flex-direction: column; }}
      .badge-row {{ justify-content: flex-start; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <p class="eyebrow">XDF Explorer</p>
      <h1 style="font-size:1.35rem;">{html.escape(file_name)}</h1>
      <input id="search" class="search" type="search" placeholder="Filter streams...">
      <nav id="nav">{nav_links}</nav>
    </aside>

    <main class="content">
      <section class="hero">
        <p class="eyebrow">Recording</p>
        <h1>Stream metadata</h1>
        <div class="hero-grid">
          <div class="stat">
            <span class="stat-label">File</span>
            <span class="stat-value">{html.escape(report["file"])}</span>
          </div>
          <div class="stat">
            <span class="stat-label">Streams</span>
            <span class="stat-value">{report["stream_count"]}</span>
          </div>
          <div class="stat">
            <span class="stat-label">XDF version</span>
            <span class="stat-value">{html.escape(xdf_version)}</span>
          </div>
          <div class="stat">
            <span class="stat-label">Recorded at</span>
            <span class="stat-value">{html.escape(recorded_at)}</span>
          </div>
        </div>
        <details style="margin-top:18px;border:none;box-shadow:none;background:transparent;">
          <summary style="background:transparent;padding-left:0;">File header</summary>
          {header_table}
        </details>
      </section>

      <div id="streams">{stream_sections}</div>
    </main>
  </div>

  <script>
    const search = document.getElementById("search");
    const cards = [...document.querySelectorAll(".stream-card")];
    const navLinks = [...document.querySelectorAll(".nav-link")];

    search.addEventListener("input", () => {{
      const query = search.value.trim().toLowerCase();
      cards.forEach((card, index) => {{
        const visible = !query || card.dataset.name.includes(query);
        card.classList.toggle("hidden", !visible);
        navLinks[index].classList.toggle("hidden", !visible);
      }});
    }});

    const observer = new IntersectionObserver(
      (entries) => {{
        entries.forEach((entry) => {{
          if (!entry.isIntersecting) return;
          const id = entry.target.id;
          navLinks.forEach((link) => {{
            link.classList.toggle("active", link.getAttribute("href") === `#${{id}}`);
          }});
        }});
      }},
      {{ rootMargin: "-20% 0px -70% 0px", threshold: 0 }}
    );

    cards.forEach((card) => observer.observe(card));
  </script>
</body>
</html>
"""


def default_html_path(xdf_file):
    if OUTPUT_HTML:
        return Path(OUTPUT_HTML)
    return SCRIPT_DIR / f"{Path(xdf_file).stem}_metadata.html"


def build_report(xdf_file):
    streams, header = pyxdf.load_xdf(xdf_file)

    return {
        "file": str(Path(xdf_file).resolve()),
        "header": normalize(header),
        "stream_count": len(streams),
        "streams": [
            {
                "index": i,
                "info": normalize(stream.get("info", {})),
                "footer": normalize(stream.get("footer", {})),
                "data_summary": summarize_arrays(stream),
            }
            for i, stream in enumerate(streams)
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Inspect all metadata contained in an XDF file."
    )
    parser.add_argument(
        "xdf_file",
        nargs="?",
        default=None,
        help=f"Path to the .xdf file (default: {INPUT_XDF.name})",
    )
    parser.add_argument(
        "--html",
        nargs="?",
        const="",
        metavar="PATH",
        help="HTML report path (default: <recording>_metadata.html in this folder)",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Do not write an HTML report",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional path to save the metadata as JSON",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print metadata JSON to the terminal",
    )
    args = parser.parse_args()

    xdf_path = Path(args.xdf_file) if args.xdf_file else INPUT_XDF
    if not xdf_path.is_file():
        print(f"File not found: {xdf_path.resolve()}", file=sys.stderr)
        print("Edit INPUT_XDF at the top of inspect_streams.py and try again.", file=sys.stderr)
        sys.exit(1)

    report = build_report(xdf_path)

    if not args.no_html:
        html_path = Path(args.html) if args.html else default_html_path(xdf_path)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(render_html_report(report), encoding="utf-8")
        print(f"Saved HTML report to {html_path.resolve()}")

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(report, indent=2, ensure_ascii=False)
        output_path.write_text(text + "\n", encoding="utf-8")
        print(f"Saved metadata to {output_path.resolve()}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
