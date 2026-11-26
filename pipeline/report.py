"""Step 3 of the pipeline: silver -> gold, then charts and findings.

Run from the project folder (after pipeline.silver):

    python -m pipeline.report

It:
  1. runs every SQL file in sql/gold/ (the reporting tables)
  2. checks gold adds back up to silver (no rows or money lost)
  3. draws charts into reports/
  4. writes reports/findings.md
  5. refreshes the Key findings section of README.md

Nothing in the findings is typed by hand: every number comes from the data.
"""

import re
import sys
from pathlib import Path

import duckdb
import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")  # draw to files, no window needed
import matplotlib.pyplot as plt  # noqa: E402

from pipeline.config import load_config  # noqa: E402

SQL_DIR = Path("sql/gold")
REPORTS_DIR = Path("reports")
README = Path("README.md")
START, END = "<!-- findings:start -->", "<!-- findings:end -->"

BLUE, GREY = "#2E74B5", "#9AA5B1"


class ReconciliationError(Exception):
    """Gold does not add back up to silver."""


def build_gold(con, sql_dir: Path = SQL_DIR) -> None:
    files = sorted(Path(sql_dir).glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"No .sql files found in {sql_dir}")
    for path in files:
        con.execute(path.read_text(encoding="utf-8"))


def reconcile(con) -> dict:
    """Totals in every gold table must match silver exactly."""
    silver = con.execute(
        "SELECT COUNT(*), SUM(items), ROUND(SUM(actual_cost_gbp), 2) FROM silver.prescribing"
    ).fetchall()[0]
    checks = {
        "monthly_summary": "SELECT SUM(prescription_lines), SUM(items), ROUND(SUM(cost_gbp), 2) FROM gold.monthly_summary",
        "substance_summary": "SELECT NULL, SUM(items), ROUND(SUM(cost_gbp), 2) FROM gold.substance_summary",
        "practice_summary": "SELECT NULL, SUM(items), ROUND(SUM(cost_gbp), 2) FROM gold.practice_summary",
    }
    for table, sql in checks.items():
        lines, items, cost = con.execute(sql).fetchall()[0]
        if lines is not None and lines != silver[0]:
            raise ReconciliationError(f"{table}: {lines} lines, silver has {silver[0]}")
        if items != silver[1]:
            raise ReconciliationError(f"{table}: {items} items, silver has {silver[1]}")
        if abs((cost or 0) - (silver[2] or 0)) > 0.05:  # allow for rounding per row
            raise ReconciliationError(f"{table}: GBP {cost}, silver has GBP {silver[2]}")
    return {"lines": silver[0], "items": silver[1], "cost": silver[2]}


def gather(con) -> dict:
    """Pull every number the findings need, straight from gold."""
    monthly = con.execute(
        "SELECT month_start, items, cost_gbp, cost_per_item_gbp, practices "
        "FROM gold.monthly_summary ORDER BY month_start"
    ).fetchall()
    substances = con.execute(
        "SELECT antibiotic, items, share_of_items_pct, cost_gbp, cost_per_item_gbp "
        "FROM gold.substance_summary ORDER BY items DESC"
    ).fetchall()
    unusual = con.execute(
        "SELECT practice_code, practice_name, months_active, items "
        "FROM gold.practice_summary WHERE NOT standard_code_format ORDER BY items DESC"
    ).fetchall()
    unusual_lines = con.execute(
        "SELECT COUNT(*) FROM silver.prescribing "
        "WHERE NOT regexp_full_match(practice_code, '[A-Z][0-9]{5}')"
    ).fetchall()[0][0]
    dq = con.execute(
        """
        SELECT status, COUNT(*) FROM silver.dq_results
        WHERE run_id = (SELECT run_id FROM silver.dq_results ORDER BY checked_at DESC LIMIT 1)
        GROUP BY status
        """
    ).fetchall()
    return {
        "monthly": monthly,
        "substances": substances,
        "unusual": unusual,
        "unusual_lines": unusual_lines,
        "dq": dict(dq),
    }


def draw_charts(facts: dict, out_dir: Path = REPORTS_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    # 1. Monthly trend
    months = [m[0].strftime("%b %y") for m in facts["monthly"]]
    items = [m[1] for m in facts["monthly"]]
    peak = items.index(max(items))
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(months, items, color=BLUE, linewidth=2.2, marker="o")
    ax.annotate(f"Peak: {items[peak]:,}", (peak, items[peak]), textcoords="offset points",
                xytext=(0, 10), ha="center", fontsize=9, color=BLUE)
    ax.set_title("Antibiotic items prescribed per month, Newcastle Gateshead", loc="left", fontsize=12)
    ax.set_ylabel("Items")
    ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
    ax.set_ylim(0, max(items) * 1.15)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    fig.text(0.01, 0.01, "Source: NHSBSA English Prescribing Dataset, BNF 5.1, sub-ICB 13T00", fontsize=7, color=GREY)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path = out_dir / "monthly_items.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    # 2. Top antibiotics
    top = facts["substances"][:10][::-1]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    bars = ax.barh([t[0] for t in top], [t[1] for t in top], color=BLUE)
    for bar, t in zip(bars, top):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f"  {t[2]}%",
                va="center", fontsize=8, color="#333333")
    period = f"{facts['monthly'][0][0]:%b %Y} to {facts['monthly'][-1][0]:%b %Y}"
    ax.set_title(f"Top 10 antibiotics by items, {period} (share of all items)", loc="left", fontsize=12)
    ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.3)
    fig.text(0.01, 0.01, "Source: NHSBSA English Prescribing Dataset, BNF 5.1, sub-ICB 13T00", fontsize=7, color=GREY)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path = out_dir / "top_antibiotics.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)
    return paths


def findings_markdown(facts: dict, totals: dict) -> str:
    monthly = facts["monthly"]
    peak = max(monthly, key=lambda m: m[1])
    low = min(monthly, key=lambda m: m[1])
    first, last = monthly[0][0].strftime("%B %Y"), monthly[-1][0].strftime("%B %Y")
    top3 = facts["substances"][:3]
    top3_share = round(sum(s[2] for s in top3), 1)
    dq = facts["dq"]
    lines = [
        f"- **{totals['items']:,} antibiotic items** cost the NHS **GBP {totals['cost']:,.0f}** "
        f"across {len(monthly)} months ({first} to {last}), from {totals['lines']:,} prescription lines.",
        f"- **{'Winter peak' if peak[0].month in (11, 12, 1, 2) else 'Peak month'}:** "
        f"the busiest month was **{peak[0].strftime('%B %Y')}** with {peak[1]:,} items, "
        f"{round(100 * (peak[1] - low[1]) / low[1])}% more than the quietest, "
        f"**{low[0].strftime('%B %Y')}** ({low[1]:,}).",
        f"- **Concentration:** three antibiotics, {', '.join(s[0] for s in top3)}, "
        f"make up **{top3_share}%** of all items.",
        f"- **Data quality:** {dq.get('PASS', 0)} of {sum(dq.values())} checks passed. "
        f"{len(facts['unusual'])} {'prescriber' if len(facts['unusual']) == 1 else 'prescribers'} "
        f"({facts['unusual_lines']:,} lines) {'uses' if len(facts['unusual']) == 1 else 'use'} a non-standard "
        f"practice code; logged as [OBS-001](docs/defects/OBS-001-non-standard-practice-codes.md) for investigation.",
        "- **Limitation:** the dataset has no patient list sizes, so practices are compared on volume, "
        "not on prescribing per patient.",
    ]
    return "\n".join(lines)


def write_findings(facts: dict, totals: dict, out_dir: Path = REPORTS_DIR) -> Path:
    body = [
        "# Findings",
        "",
        "Generated by `python -m pipeline.report`. Every number below comes from the gold tables.",
        "",
        "## Key findings",
        "",
        findings_markdown(facts, totals),
        "",
        "![Monthly items](monthly_items.png)",
        "",
        "![Top antibiotics](top_antibiotics.png)",
        "",
        "## Monthly summary",
        "",
        "| Month | Practices | Items | Cost (GBP) | Cost per item (GBP) |",
        "|---|---:|---:|---:|---:|",
    ]
    for month, items, cost, per_item, practices in facts["monthly"]:
        body.append(f"| {month.strftime('%b %Y')} | {practices} | {items:,} | {cost:,.2f} | {per_item:.2f} |")
    body += ["", "## Top 10 antibiotics", "",
             "| Antibiotic | Items | Share of items | Cost (GBP) | Cost per item (GBP) |",
             "|---|---:|---:|---:|---:|"]
    for name, items, share, cost, per_item in facts["substances"][:10]:
        body.append(f"| {name} | {items:,} | {share}% | {cost:,.2f} | {per_item:.2f} |")
    body += ["", "## Prescribers with non-standard practice codes (OBS-001)", "",
             "| Code | Name | Months active | Items |", "|---|---|---:|---:|"]
    for code, name, months, items in facts["unusual"]:
        body.append(f"| {code} | {name} | {months} | {items:,} |")
    path = Path(out_dir) / "findings.md"
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


def update_readme(text: str, readme: Path = README) -> bool:
    """Replace whatever sits between the findings markers in the README."""
    content = readme.read_text(encoding="utf-8")
    if START not in content or END not in content:
        return False
    new = re.sub(re.escape(START) + r".*?" + re.escape(END),
                 lambda _: f"{START}\n{text}\n{END}", content, flags=re.DOTALL)
    readme.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    config = load_config()
    if not config.warehouse_path.exists():
        print("No warehouse yet. Run:  python -m pipeline.ingest  then  python -m pipeline.silver")
        return 1
    con = duckdb.connect(str(config.warehouse_path))
    try:
        build_gold(con)
        totals = reconcile(con)
        print(f"Gold built and reconciled to silver: {totals['lines']:,} lines, "
              f"{totals['items']:,} items, GBP {totals['cost']:,.2f}")
        facts = gather(con)
    except ReconciliationError as error:
        print(f"FAIL: gold does not add up to silver. {error}")
        return 1
    finally:
        con.close()

    for path in draw_charts(facts):
        print(f"Chart written: {path}")
    print(f"Findings written: {write_findings(facts, totals)}")
    print("README updated." if update_readme(findings_markdown(facts, totals)) else "README markers not found.")
    print("\n" + findings_markdown(facts, totals).replace("**", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
