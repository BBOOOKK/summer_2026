#!/usr/bin/env python3
"""Dependency-light validation for hosts without ROS 2/Gazebo."""

import importlib.util
from pathlib import Path
import py_compile
import sys
import unittest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))


def main():
    failures = []
    for path in ROOT.rglob('*.py'):
        if any(part in ('build', 'install') for part in path.parts):
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failures.append(str(exc))

    spec = importlib.util.spec_from_file_location(
        'test_assets', ROOT / 'test' / 'test_assets.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in sorted(item for item in dir(module) if item.startswith('test_')):
        try:
            getattr(module, name)()
            print(f'PASS {name}')
        except Exception as exc:  # report all asset failures together
            failures.append(f'{name}: {exc}')

    suite = unittest.defaultTestLoader.discover(
        str(ROOT / 'test'), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        failures.append('pure Python unit tests failed')

    if failures:
        print('\n'.join(f'FAIL {item}' for item in failures), file=sys.stderr)
        return 1
    print('PASS static simulation validation')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
