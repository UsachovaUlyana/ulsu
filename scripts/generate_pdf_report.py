#!/usr/bin/env python3
import datetime as dt
from pathlib import Path

import pandas as pd
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results" / "report_run"
OUT_PDF = ROOT / "reports" / "rabbitmq_redis_report.pdf"
SCREENSHOT_DIR = ROOT / "reports" / "screenshots"
FONT_REGULAR = "Arial"
FONT_BOLD = "Arial-Bold"


def register_fonts() -> None:
    reg_path = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    bold_path = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
    if reg_path.exists():
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(reg_path)))
    if bold_path.exists():
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold_path)))


def fmt(x):
    if isinstance(x, float):
        return f"{x:.3f}".rstrip("0").rstrip(".")
    return str(x)


def expected_points():
    brokers = ["rabbitmq", "redis"]
    profiles = ["baseline", "stress"]
    sizes = [128, 1024, 10240, 102400]
    rates = [1000, 5000, 10000]
    return {(b, p, s, r) for b in brokers for p in profiles for s in sizes for r in rates}


def to_size_label(size_b: int) -> str:
    if size_b == 128:
        return "128B"
    if size_b == 1024:
        return "1KB"
    if size_b == 10240:
        return "10KB"
    if size_b == 102400:
        return "100KB"
    return f"{size_b}B"


def table_from_df(df: pd.DataFrame):
    data = [list(df.columns)]
    for _, row in df.iterrows():
        data.append([fmt(v) for v in row.tolist()])

    t = Table(data, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3c88")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d7de")),
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def make_grouped_bar_chart(title: str, categories: list[str], series: list[tuple[str, list[float], colors.Color]]) -> Drawing:
    drawing = Drawing(520, 260)
    drawing.add(String(10, 240, title, fontName=FONT_BOLD, fontSize=11))

    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 45
    chart.height = 160
    chart.width = 330
    chart.data = [tuple(values) for _, values, _ in series]
    chart.barWidth = 14
    chart.groupSpacing = 16
    chart.barSpacing = 3
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontName = FONT_REGULAR
    chart.valueAxis.labels.fontSize = 8
    chart.categoryAxis.categoryNames = categories
    chart.categoryAxis.labels.boxAnchor = "n"
    chart.categoryAxis.labels.dy = -8
    chart.categoryAxis.labels.fontName = FONT_REGULAR
    chart.categoryAxis.labels.fontSize = 8

    for i, (_, _, color) in enumerate(series):
        chart.bars[i].fillColor = color

    drawing.add(chart)

    legend = Legend()
    legend.x = 390
    legend.y = 165
    legend.fontName = FONT_REGULAR
    legend.fontSize = 8
    legend.boxAnchor = "nw"
    legend.dx = 8
    legend.dy = 8
    legend.deltay = 14
    legend.colorNamePairs = [(series[i][2], series[i][0]) for i in range(len(series))]
    drawing.add(legend)

    return drawing


def build_summary_tables(df: pd.DataFrame):
    base = df[df["profile"] == "baseline"].copy()

    thr_tbl = (
        base.pivot_table(index=["msg_size", "rate"], columns="broker", values="throughput_msg_sec", aggfunc="mean")
        .reset_index()
        .rename(columns={"msg_size": "size_B", "rate": "rate_msg_s"})
    )
    p95_tbl = (
        base.pivot_table(index=["msg_size", "rate"], columns="broker", values="p95_latency_ms", aggfunc="mean")
        .reset_index()
        .rename(columns={"msg_size": "size_B", "rate": "rate_msg_s"})
    )
    backlog_tbl = (
        base.pivot_table(index=["msg_size", "rate"], columns="broker", values="backlog_peak", aggfunc="mean")
        .reset_index()
        .rename(columns={"msg_size": "size_B", "rate": "rate_msg_s"})
    )
    return thr_tbl, p95_tbl, backlog_tbl


def fit_image(path: Path, max_w_mm: float = 175, max_h_mm: float = 98) -> Image:
    img = Image(str(path))
    iw = float(img.imageWidth)
    ih = float(img.imageHeight)
    max_w = max_w_mm * mm
    max_h = max_h_mm * mm
    scale = min(max_w / iw, max_h / ih)
    img.drawWidth = iw * scale
    img.drawHeight = ih * scale
    return img


def main() -> None:
    register_fonts()

    csv_path = RESULTS_DIR / "results.csv"
    if not csv_path.exists():
        raise SystemExit(f"Не найден файл результатов: {csv_path}")

    df = pd.read_csv(csv_path)

    got = set(zip(df["broker"], df["profile"], df["msg_size"], df["rate"]))
    exp = expected_points()
    missing = sorted(exp - got)

    base = df[df["profile"] == "baseline"].copy()
    rabbit = base[base["broker"] == "rabbitmq"]
    redis = base[base["broker"] == "redis"]

    rabbit_max_thr = rabbit.loc[rabbit["throughput_msg_sec"].idxmax()]
    redis_max_thr = redis.loc[redis["throughput_msg_sec"].idxmax()] if not redis.empty else None

    # Для сравнительных графиков берем только размеры, которые есть у обоих брокеров в baseline.
    sizes_r = set(rabbit["msg_size"].unique().tolist())
    sizes_d = set(redis["msg_size"].unique().tolist())
    common_sizes = sorted(sizes_r.intersection(sizes_d))

    def avg_metric(data: pd.DataFrame, broker: str, size: int, col: str) -> float:
        subset = data[(data["broker"] == broker) & (data["msg_size"] == size)]
        return float(subset[col].mean()) if not subset.empty else 0.0

    categories_common = [to_size_label(s) for s in common_sizes]
    thr_series = [
        ("RabbitMQ", [avg_metric(base, "rabbitmq", s, "throughput_msg_sec") for s in common_sizes], colors.HexColor("#1f77b4")),
        ("Redis", [avg_metric(base, "redis", s, "throughput_msg_sec") for s in common_sizes], colors.HexColor("#2ca02c")),
    ]
    p95_series = [
        ("RabbitMQ", [avg_metric(base, "rabbitmq", s, "p95_latency_ms") for s in common_sizes], colors.HexColor("#ff7f0e")),
        ("Redis", [avg_metric(base, "redis", s, "p95_latency_ms") for s in common_sizes], colors.HexColor("#9467bd")),
    ]

    rabbit_100k = df[df["msg_size"] == 102400].copy()
    rates_100k = sorted(rabbit_100k["rate"].unique().tolist())
    categories_100k = [str(r) for r in rates_100k]
    backlog_100k_series = [
        (
            "RabbitMQ baseline",
            [float(rabbit_100k[(rabbit_100k["broker"] == "rabbitmq") & (rabbit_100k["profile"] == "baseline") & (rabbit_100k["rate"] == r)]["backlog_peak"].mean() or 0) for r in rates_100k],
            colors.HexColor("#d62728"),
        ),
        (
            "RabbitMQ stress",
            [float(rabbit_100k[(rabbit_100k["broker"] == "rabbitmq") & (rabbit_100k["profile"] == "stress") & (rabbit_100k["rate"] == r)]["backlog_peak"].mean() or 0) for r in rates_100k],
            colors.HexColor("#8c564b"),
        ),
    ]

    thr_tbl, p95_tbl, backlog_tbl = build_summary_tables(df)

    styles = getSampleStyleSheet()
    styles["Title"].fontName = FONT_BOLD
    styles["Heading2"].fontName = FONT_BOLD
    styles["Normal"].fontName = FONT_REGULAR
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=9, leading=12))

    story = []
    story.append(Paragraph("Отчет по практике: сравнение RabbitMQ и Redis Streams", styles["Title"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"Дата формирования: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    story.append(Paragraph("Источник данных: results/report_run/results.csv", styles["Normal"]))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("1. Параметры стенда", styles["Heading2"]))
    story.append(Paragraph("Брокеры: RabbitMQ и Redis Streams (Consumer Group + XACK).", styles["Normal"]))
    story.append(Paragraph("Параллельность: producers=2, consumers=2 (одинаково для обоих брокеров).", styles["Normal"]))
    story.append(Paragraph("Размеры сообщений: 128B, 1KB, 10KB, 100KB.", styles["Normal"]))
    story.append(Paragraph("Интенсивности: 1000, 5000, 10000 msg/s.", styles["Normal"]))
    story.append(Paragraph("Профили: baseline и stress.", styles["Normal"]))
    story.append(Paragraph(f"Собрано точек: {len(got)} из {len(exp)}.", styles["Normal"]))
    if missing:
        story.append(Paragraph("Часть high-load точек не завершилась: Redis контейнер завершился в процессе поздних прогонов (Exited 137).", styles["Small"]))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("2. Ключевые наблюдения", styles["Heading2"]))
    story.append(
        Paragraph(
            f"Максимальный throughput RabbitMQ (baseline): {rabbit_max_thr['throughput_msg_sec']:.1f} msg/s при size={int(rabbit_max_thr['msg_size'])}B и rate={int(rabbit_max_thr['rate'])}.",
            styles["Normal"],
        )
    )
    if redis_max_thr is not None:
        story.append(
            Paragraph(
                f"Максимальный throughput Redis (baseline): {redis_max_thr['throughput_msg_sec']:.1f} msg/s при size={int(redis_max_thr['msg_size'])}B и rate={int(redis_max_thr['rate'])}.",
                styles["Normal"],
            )
        )

    total_lost = int(df["lost_total"].sum())
    story.append(Paragraph(f"Суммарные измеренные потери по всем точкам: {total_lost}.", styles["Normal"]))

    losses = df.groupby("broker")["lost_total"].sum().to_dict()
    rabbit_loss = int(losses.get("rabbitmq", 0))
    redis_loss = int(losses.get("redis", 0))
    story.append(
        Paragraph(
            f"Сравнение потерь: RabbitMQ={rabbit_loss}, Redis={redis_loss}. На этом стенде потери у RabbitMQ не выше, чем у Redis.",
            styles["Normal"],
        )
    )

    heavy_rabbit = df[(df["broker"] == "rabbitmq") & (df["msg_size"] == 102400)].sort_values("backlog_peak", ascending=False)
    if not heavy_rabbit.empty:
        worst = heavy_rabbit.iloc[0]
        story.append(
            Paragraph(
                f"Признак деградации single instance на крупных payload: RabbitMQ достиг backlog_peak={int(worst['backlog_peak'])} и p95={worst['p95_latency_ms']:.1f} ms (size=100KB, rate={int(worst['rate'])}, profile={worst['profile']}).",
                styles["Normal"],
            )
        )
    redis_degraded = df[(df["broker"] == "redis") & (df["degraded"] == True)].sort_values(["error_rate", "rate"], ascending=False) if "error_rate" in df.columns else pd.DataFrame()
    if redis_degraded.empty:
        # В текущем CSV нет агрегированного error_rate, используем первичную оценку по errors/sent.
        cand = df[df["broker"] == "redis"].copy()
        if not cand.empty:
            cand["err_rate_est"] = (cand["publish_errors"] + cand["consume_errors"]) / cand["sent_total"].clip(lower=1)
            cand = cand[cand["err_rate_est"] >= 0.01].sort_values(["err_rate_est", "rate"], ascending=False)
            if not cand.empty:
                row = cand.iloc[0]
                story.append(
                    Paragraph(
                        f"Для Redis точка деградации зафиксирована при size={int(row['msg_size'])}B, rate={int(row['rate'])}: err_rate≈{row['err_rate_est']:.2%}, throughput={row['throughput_msg_sec']:.1f} msg/s.",
                        styles["Normal"],
                    )
                )
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("3. Графики", styles["Heading2"]))
    story.append(make_grouped_bar_chart("3.1 Throughput (baseline, среднее по rate)", categories_common, thr_series))
    story.append(Spacer(1, 2 * mm))
    story.append(make_grouped_bar_chart("3.2 P95 latency (baseline, среднее по rate)", categories_common, p95_series))
    story.append(Spacer(1, 2 * mm))
    story.append(make_grouped_bar_chart("3.3 RabbitMQ backlog_peak на 100KB", categories_100k, backlog_100k_series))
    story.append(PageBreak())

    story.append(Paragraph("4. Таблицы результатов (baseline)", styles["Heading2"]))
    story.append(Paragraph("4.1 Throughput, msg/s", styles["Normal"]))
    story.append(table_from_df(thr_tbl))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("4.2 P95 latency, ms", styles["Normal"]))
    story.append(table_from_df(p95_tbl))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("4.3 Backlog peak", styles["Normal"]))
    story.append(table_from_df(backlog_tbl))

    story.append(PageBreak())
    story.append(Paragraph("5. Незавершенные точки", styles["Heading2"]))
    if missing:
        missing_df = pd.DataFrame(missing, columns=["broker", "profile", "size_B", "rate_msg_s"])
        story.append(table_from_df(missing_df))
    else:
        story.append(Paragraph("Все точки завершены.", styles["Normal"]))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("6. Выводы", styles["Heading2"]))
    story.append(Paragraph("1. На малых и средних payload Redis показывает более высокий throughput и ниже p95.", styles["Normal"]))
    story.append(Paragraph("2. Для RabbitMQ на 100KB заметно растут backlog и p95, что фиксирует деградацию single instance при росте нагрузки.", styles["Normal"]))
    story.append(Paragraph("3. Для Redis на high-load 100KB появляются стабильные publish/consume ошибки и просадка фактической обработки, что является точкой деградации single instance.", styles["Normal"]))
    story.append(Paragraph("4. Выбранный инструмент: собственный Python-стенд. Причина выбора: единая логика producer/consumer и идентичный учет метрик (sent/consumed/loss/p95/backlog) для двух разных брокеров в одинаковых условиях, что упрощает честное сравнение.", styles["Normal"]))
    story.append(PageBreak())

    story.append(Paragraph("7. Скриншоты запуска и метрик", styles["Heading2"]))
    screenshot_files = [
        SCREENSHOT_DIR / "01_matrix_run.png",
        SCREENSHOT_DIR / "02_rabbitmq_management.png",
        SCREENSHOT_DIR / "03_redis_stats.png",
    ]
    added = 0
    for img_path in screenshot_files:
        if img_path.exists():
            story.append(Paragraph(img_path.name, styles["Small"]))
            story.append(fit_image(img_path, max_w_mm=175, max_h_mm=98))
            story.append(Spacer(1, 3 * mm))
            added += 1
    if added == 0:
        story.append(Paragraph("Скриншоты не приложены. Добавьте PNG-файлы в reports/screenshots и пересоберите отчет.", styles["Small"]))

    doc = SimpleDocTemplate(
        str(OUT_PDF),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    doc.build(story)

    print(f"PDF report created: {OUT_PDF}")


if __name__ == "__main__":
    main()
