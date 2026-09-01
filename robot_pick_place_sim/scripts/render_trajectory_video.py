#!/usr/bin/env python3
"""Render a reproducible two-view video from a recorded Gazebo trajectory."""

import argparse
from bisect import bisect_right
import csv
from math import cos, hypot, sin
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont


JOINTS = [f'joint{i}' for i in range(1, 7)] + [
    'left_finger_joint', 'right_finger_joint', 'gripper_joint',
]
POSES = {
    'HOME': [0.0] * 6,
    'ABOVE A': [0.499, -0.418, 2.196, 0.0, 0.0, -0.499],
    'PICK A': [0.499, 0.072, 2.178, 0.0, 0.0, -0.499],
    'ABOVE B': [-0.675, -0.367, 2.154, 0.0, 0.0, 0.675],
    'PLACE B': [-0.675, 0.112, 2.136, 0.0, 0.0, 0.675],
}


def font(size):
    candidates = (
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def load_samples(path):
    grouped = {}
    with path.open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            if row['name'] in JOINTS:
                grouped.setdefault(float(row['time']), {})[row['name']] = float(
                    row['position'])
    samples = []
    current = {name: 0.0 for name in JOINTS}
    for timestamp in sorted(grouped):
        current.update(grouped[timestamp])
        if all(name in current for name in JOINTS):
            samples.append((timestamp, [current[name] for name in JOINTS]))
    if len(samples) < 2:
        raise ValueError('trajectory does not contain enough joint samples')
    return samples


def interpolate(samples, timestamp):
    times = [item[0] for item in samples]
    index = max(0, min(len(samples) - 2, bisect_right(times, timestamp) - 1))
    before_time, before = samples[index]
    after_time, after = samples[index + 1]
    ratio = 0.0 if after_time == before_time else (
        timestamp - before_time) / (after_time - before_time)
    ratio = max(0.0, min(1.0, ratio))
    return [left + (right - left) * ratio for left, right in zip(before, after)]


def arm_points(joints):
    q1, q2, q3, _q4, q5, _q6 = joints[:6]
    radial = [0.0]
    heights = [0.165]
    angle = q2
    for length, delta in ((0.130, 0.0), (0.195, q3), (0.115, q5)):
        angle += delta
        radial.append(radial[-1] + length * sin(angle))
        heights.append(heights[-1] + length * cos(angle))
    top = [(value * cos(q1), value * sin(q1)) for value in radial]
    side = list(zip(radial, heights))
    return top, side


def nearest_pose(joints):
    return min(
        POSES,
        key=lambda name: sum(
            (actual - target) ** 2
            for actual, target in zip(joints[:6], POSES[name])),
    )


def map_point(point, origin, scale, invert_y=True):
    x = origin[0] + point[0] * scale
    y_delta = -point[1] * scale if invert_y else point[1] * scale
    return int(x), int(origin[1] + y_delta)


def draw_frame(joints, elapsed, duration, run_id, object_state):
    image = Image.new('RGB', (1280, 720), '#f3f5f7')
    draw = ImageDraw.Draw(image)
    title = font(32)
    body = font(21)
    small = font(17)
    draw.rectangle((0, 0, 1280, 74), fill='#17324d')
    draw.text((32, 18), 'mechArm 270 fixed-point pick-and-place',
              fill='white', font=title)
    draw.text((845, 25), f'Gazebo run {run_id}', fill='#b9daf5', font=small)

    top_box = (35, 105, 625, 625)
    side_box = (655, 105, 1245, 625)
    for box, label in ((top_box, 'TOP VIEW'), (side_box, 'SIDE VIEW')):
        draw.rounded_rectangle(box, radius=16, fill='white', outline='#b8c4ce', width=2)
        draw.text((box[0] + 18, box[1] + 14), label, fill='#38546c', font=body)

    top_origin, top_scale = (330, 370), 720
    draw.rectangle((top_origin[0] - 324, top_origin[1] - 252,
                    top_origin[0] + 324, top_origin[1] + 252),
                   outline='#986c42', width=4)
    point_a = map_point((0.22, 0.12), top_origin, top_scale)
    point_b = map_point((0.20, -0.16), top_origin, top_scale)
    draw.ellipse((point_a[0] - 22, point_a[1] - 22,
                  point_a[0] + 22, point_a[1] + 22),
                 outline='#e4572e', width=4)
    draw.text((point_a[0] + 25, point_a[1] - 18), 'A', fill='#e4572e', font=body)
    draw.ellipse((point_b[0] - 50, point_b[1] - 50,
                  point_b[0] + 50, point_b[1] + 50),
                 fill='#d8f2dc', outline='#2b9348', width=4)
    draw.text((point_b[0] + 54, point_b[1] - 18), 'B', fill='#2b9348', font=body)

    top, side = arm_points(joints)
    top_pixels = [map_point(point, top_origin, top_scale) for point in top]
    draw.line(top_pixels, fill='#2463a6', width=14, joint='curve')
    for point in top_pixels:
        draw.ellipse((point[0] - 9, point[1] - 9,
                      point[0] + 9, point[1] + 9), fill='#102a43')

    if object_state['held']:
        object_state['position'] = top[-1]
    object_pixel = map_point(object_state['position'], top_origin, top_scale)
    draw.rectangle((object_pixel[0] - 12, object_pixel[1] - 12,
                    object_pixel[0] + 12, object_pixel[1] + 12), fill='#f04a24')

    side_origin, side_scale = (780, 580), 800
    draw.line((690, side_origin[1], 1210, side_origin[1]), fill='#986c42', width=6)
    side_pixels = [map_point((r, z), side_origin, side_scale) for r, z in side]
    draw.line(side_pixels, fill='#2463a6', width=14, joint='curve')
    for point in side_pixels:
        draw.ellipse((point[0] - 9, point[1] - 9,
                      point[0] + 9, point[1] + 9), fill='#102a43')
    tool = side_pixels[-1]
    gap = int(8 + joints[6] * 380)
    draw.line((tool[0] - gap, tool[1], tool[0] - gap, tool[1] + 48),
              fill='#e4572e', width=7)
    draw.line((tool[0] + gap, tool[1], tool[0] + gap, tool[1] + 48),
              fill='#e4572e', width=7)

    pose = nearest_pose(joints)
    gripper = 'CLOSED / HOLDING' if object_state['held'] else (
        'OPEN' if joints[6] > 0.02 else 'CLOSED')
    draw.text((45, 649), f'State: {pose}', fill='#17324d', font=body)
    draw.text((300, 649), f'Gripper: {gripper}', fill='#17324d', font=body)
    draw.text((695, 649), 'Source: recorded Gazebo /joint_states',
              fill='#526a7c', font=small)
    bar_left, bar_right = 45, 1235
    draw.rectangle((bar_left, 689, bar_right, 701), fill='#d7dee5')
    progress = bar_left + int((bar_right - bar_left) * elapsed / duration)
    draw.rectangle((bar_left, 689, progress, 701), fill='#2b7fc0')
    return image


def render(input_path, output_path, fps):
    samples = load_samples(input_path)
    start, end = samples[0][0], samples[-1][0]
    duration = end - start
    run_id = input_path.stem.removeprefix('trajectory_')
    object_state = {'held': False, 'released': False, 'position': (0.22, 0.12)}
    with tempfile.TemporaryDirectory(prefix='pick_place_frames_') as directory:
        frame_dir = Path(directory)
        frame_count = int(duration * fps) + 1
        for index in range(frame_count):
            elapsed = min(duration, index / fps)
            joints = interpolate(samples, start + elapsed)
            if not object_state['released'] and not object_state['held'] and (
                    elapsed > 4.0 and joints[6] < 0.012):
                object_state['held'] = True
            if object_state['held'] and joints[6] > 0.025:
                object_state['held'] = False
                object_state['released'] = True
            frame = draw_frame(joints, elapsed, duration, run_id, object_state)
            frame.save(frame_dir / f'frame_{index:05d}.png')
        subprocess.run([
            'ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(fps),
            '-i', str(frame_dir / 'frame_%05d.png'), '-c:v', 'libx264',
            '-preset', 'medium', '-pix_fmt', 'yuv420p', str(output_path),
        ], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fps', type=int, default=15)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    render(args.input, args.output, args.fps)


if __name__ == '__main__':
    main()
