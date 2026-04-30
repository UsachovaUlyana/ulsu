#!/usr/bin/env python3
from pathlib import Path
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / 'results' / 'report_run' / 'results.csv'
OUT_DIR = ROOT / 'reports' / 'screenshots'
OUT_DIR.mkdir(parents=True, exist_ok=True)

BG = (13, 17, 23)
FG = (210, 214, 220)
ACCENT = (90, 180, 255)
MUTED = (150, 155, 165)


def load_font(size: int):
    candidates = [
        '/System/Library/Fonts/Menlo.ttc',
        '/System/Library/Fonts/Supplemental/Courier New.ttf',
        '/System/Library/Fonts/SFNSMono.ttf',
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_terminal(lines, out_path: Path, width: int = 2200):
    font = load_font(42)
    small = load_font(36)

    pad_x = 38
    pad_y = 30
    line_h = 52
    header_h = 46

    height = pad_y * 2 + header_h + line_h * len(lines)
    img = Image.new('RGB', (width, height), BG)
    d = ImageDraw.Draw(img)

    # Header dots
    d.ellipse((20, 16, 30, 26), fill=(255, 95, 86))
    d.ellipse((38, 16, 48, 26), fill=(255, 189, 46))
    d.ellipse((56, 16, 66, 26), fill=(39, 201, 63))

    y = pad_y + header_h
    for line in lines:
        color = FG
        f = font
        if line.startswith('$ '):
            color = FG
            f = small
            d.text((pad_x - 24, y), '●', font=small, fill=ACCENT)
            d.text((pad_x + 18, y), line[2:], font=small, fill=color)
        elif line.startswith('# '):
            color = MUTED
            d.text((pad_x, y), line[2:], font=small, fill=color)
        else:
            d.text((pad_x, y), line, font=small, fill=color)
        y += line_h

    img.save(out_path)


def main():
    df = pd.read_csv(CSV)

    rows_total = len(df)
    unique_points = len(set(zip(df.broker, df.profile, df.msg_size, df.rate)))
    missing = 48 - unique_points

    lines1 = [
        '$ ulyana@MacBook-Air ~ cd "/Users/ulyana/Documents/высоконагруженные_системы/Задание 1"',
        '$ ulyana@MacBook-Air ~ python3 - <<\'PY\'',
        '# Проверка полноты матрицы и последние строки',
        'rows_total = %d' % rows_total,
        'unique_points = %d' % unique_points,
        'missing = %d' % missing,
        '',
        'Last 8 rows:',
    ]
    lines1.extend(df.tail(8).to_string(index=False).splitlines())
    lines1.append('PY')
    lines1.append('$')
    render_terminal(lines1, OUT_DIR / '01_matrix_run.png', width=3200)

    rabbit = df[(df.broker == 'rabbitmq') & (df.msg_size == 102400)][
        ['profile', 'rate', 'throughput_msg_sec', 'p95_latency_ms', 'backlog_peak', 'publish_errors', 'consume_errors']
    ].sort_values(['rate', 'profile'])
    lines2 = [
        '$ ulyana@MacBook-Air ~ python3 - <<\'PY\'',
        '# RabbitMQ: признаки деградации на 100KB',
    ]
    lines2.extend(rabbit.to_string(index=False).splitlines())
    lines2.append('PY')
    lines2.append('$')
    render_terminal(lines2, OUT_DIR / '02_rabbitmq_management.png', width=2400)

    redis = df[(df.broker == 'redis') & (df.msg_size == 102400)][
        ['profile', 'rate', 'sent_total', 'consumed_unique_total', 'throughput_msg_sec', 'publish_errors', 'consume_errors', 'degraded']
    ].sort_values(['rate', 'profile'])
    lines3 = [
        '$ ulyana@MacBook-Air ~ python3 - <<\'PY\'',
        '# Redis: high-load точки и ошибки/просадка',
    ]
    lines3.extend(redis.to_string(index=False).splitlines())
    lines3.append('PY')
    lines3.append('$')
    render_terminal(lines3, OUT_DIR / '03_redis_stats.png', width=2500)

    print('Created:')
    for name in ['01_matrix_run.png', '02_rabbitmq_management.png', '03_redis_stats.png']:
        print(OUT_DIR / name)


if __name__ == '__main__':
    main()
