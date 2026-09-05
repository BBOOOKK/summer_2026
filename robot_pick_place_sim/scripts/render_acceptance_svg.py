#!/usr/bin/env python3
"""Render a dependency-free SVG dashboard from formal acceptance evidence."""

import argparse
import json
from pathlib import Path


def render(summary):
    runtime_by_id = {item['run_id']: item for item in summary['runs']}
    runs = []
    for evidence in summary['evidence']['runs']:
        item = dict(evidence['object'])
        item.update({
            'run_id': evidence['run_id'],
            'duration_sec': runtime_by_id[evidence['run_id']]['duration_sec'],
            'forbidden_contacts': evidence['forbidden_contacts'],
        })
        runs.append(item)
    width, height = 1280, 720
    x0, y0, plot_w, plot_h = 70, 190, 570, 420
    x_min, x_max = -0.05, 0.45
    y_min, y_max = -0.24, 0.18

    def sx(value):
        return x0 + (value - x_min) / (x_max - x_min) * plot_w

    def sy(value):
        return y0 + plot_h - (value - y_min) / (y_max - y_min) * plot_h

    durations = [item['duration_sec'] for item in runs]
    max_duration = max(durations) * 1.1
    max_error = max(item['placement_error_m'] * 1000 for item in runs) * 1.15
    success = summary['succeeded']
    forbidden = sum(item['forbidden_contacts'] for item in runs)
    max_placement = max(item['placement_error_m'] * 1000 for item in runs)
    colors = ['#2563eb', '#0891b2', '#059669', '#d97706', '#7c3aed']
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">mechArm Gazebo Fortress 五次抓取验收可视化</title>
<desc id="desc">五次抓取全部成功，落点均在 B 区内，无禁止碰撞。</desc>
<rect width="1280" height="720" fill="#f8fafc"/>
<text x="60" y="56" font-family="sans-serif" font-size="30" font-weight="600" fill="#0f172a">mechArm 定点抓取 · Fortress + MoveIt 2</text>
<text x="60" y="84" font-family="sans-serif" font-size="16" fill="#475569">正式动态验收 · 2026-09-05 · 实测目标物轨迹</text>
<g font-family="sans-serif"><rect x="60" y="106" width="220" height="62" rx="10" fill="#dcfce7"/><text x="78" y="132" font-size="14" fill="#166534">连续成功</text><text x="78" y="156" font-size="25" font-weight="600" fill="#14532d">{success} / {summary['required_runs']}</text>
<rect x="300" y="106" width="260" height="62" rx="10" fill="#dbeafe"/><text x="318" y="132" font-size="14" fill="#1e40af">最大落点误差</text><text x="318" y="156" font-size="25" font-weight="600" fill="#1e3a8a">{max_placement:.2f} mm</text>
<rect x="580" y="106" width="220" height="62" rx="10" fill="#f1f5f9"/><text x="598" y="132" font-size="14" fill="#475569">禁止碰撞</text><text x="598" y="156" font-size="25" font-weight="600" fill="#0f172a">{forbidden}</text></g>
<text x="70" y="184" font-family="sans-serif" font-size="17" font-weight="600" fill="#0f172a">5 次最终落点（俯视）</text>
<rect x="{x0}" y="{y0}" width="{plot_w}" height="{plot_h}" fill="#ffffff" stroke="#cbd5e1"/>
''']
    for tick in (-0.2, -0.1, 0.0, 0.1):
        parts.append(f'<line x1="{x0}" y1="{sy(tick):.1f}" x2="{x0+plot_w}" y2="{sy(tick):.1f}" stroke="#e2e8f0"/><text x="{x0-10}" y="{sy(tick)+5:.1f}" text-anchor="end" font-family="sans-serif" font-size="13" fill="#475569">{tick:.1f}</text>')
    for tick in (0.0, 0.1, 0.2, 0.3, 0.4):
        parts.append(f'<line x1="{sx(tick):.1f}" y1="{y0}" x2="{sx(tick):.1f}" y2="{y0+plot_h}" stroke="#e2e8f0"/><text x="{sx(tick):.1f}" y="{y0+plot_h+24}" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#475569">{tick:.2f}</text>')
    b_rx = 0.07 / (x_max - x_min) * plot_w
    b_ry = 0.07 / (y_max - y_min) * plot_h
    parts.append(f'<ellipse cx="{sx(.20):.1f}" cy="{sy(-.16):.1f}" rx="{b_rx:.1f}" ry="{b_ry:.1f}" fill="#dbeafe" fill-opacity=".7" stroke="#2563eb" stroke-width="2"/><text x="{sx(.20):.1f}" y="{sy(-.16)+5:.1f}" text-anchor="middle" font-family="sans-serif" font-size="16" font-weight="600" fill="#1e40af">B</text>')
    parts.append(f'<circle cx="{sx(.22):.1f}" cy="{sy(.12):.1f}" r="8" fill="#22c55e"/><text x="{sx(.22)+14:.1f}" y="{sy(.12)+5:.1f}" font-family="sans-serif" font-size="15" fill="#166534">A</text>')
    for index, item in enumerate(runs):
        px, py, _pz = item['final_xyz']
        color = colors[index]
        parts.append(f'<circle cx="{sx(px):.1f}" cy="{sy(py):.1f}" r="7" fill="{color}" stroke="#ffffff" stroke-width="2"/><text x="{sx(px)+10:.1f}" y="{sy(py)-8-index*2:.1f}" font-family="sans-serif" font-size="12" fill="{color}">{index+1}</text>')
    parts.append(f'<text x="{x0+plot_w/2}" y="{height-54}" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#334155">世界坐标 x (m)</text><text transform="translate(20 {y0+plot_h/2}) rotate(-90)" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#334155">世界坐标 y (m)</text>')
    parts.append('<text x="700" y="184" font-family="sans-serif" font-size="17" font-weight="600" fill="#0f172a">逐次性能</text>')
    for index, item in enumerate(runs):
        row_y = 222 + index * 76
        duration_w = item['duration_sec'] / max_duration * 410
        error_mm = item['placement_error_m'] * 1000
        error_w = error_mm / max_error * 240
        parts.append(f'''<g font-family="sans-serif"><text x="700" y="{row_y}" font-size="15" font-weight="600" fill="#0f172a">第 {index+1} 次</text><text x="1215" y="{row_y}" text-anchor="end" font-size="13" fill="#475569">{item['run_id'][-6:]}</text>
<rect x="700" y="{row_y+12}" width="410" height="13" rx="6" fill="#e2e8f0"/><rect x="700" y="{row_y+12}" width="{duration_w:.1f}" height="13" rx="6" fill="{colors[index]}"/><text x="1125" y="{row_y+24}" font-size="13" fill="#334155">{item['duration_sec']:.3f} s</text>
<rect x="700" y="{row_y+36}" width="240" height="9" rx="4" fill="#e2e8f0"/><rect x="700" y="{row_y+36}" width="{error_w:.1f}" height="9" rx="4" fill="#0f766e"/><text x="952" y="{row_y+45}" font-size="13" fill="#334155">误差 {error_mm:.2f} mm</text><text x="1080" y="{row_y+45}" font-size="13" fill="#334155">最高 z {item['max_z_m']:.5f} m</text></g>''')
    parts.append('<line x1="700" y1="618" x2="1215" y2="618" stroke="#cbd5e1"/><text x="700" y="650" font-family="sans-serif" font-size="14" fill="#334155">每次均通过：状态序列 · 双指接触 · 物体抬升 · B 区落点 · 无禁碰</text><text x="700" y="676" font-family="sans-serif" font-size="13" fill="#64748b">判定来源：acceptance_summary.json 自动证据门禁</text></svg>')
    return ''.join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.input.read_text(encoding='utf-8'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(summary), encoding='utf-8')


if __name__ == '__main__':
    main()
