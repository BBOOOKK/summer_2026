"""Configuration checks shared by runtime code and dependency-free tests."""

from math import hypot


ARM_POSES = (
    'home_joints', 'pick_above_joints', 'pick_joints',
    'place_above_joints', 'place_joints',
)


class SafetyError(ValueError):
    """A command is unsafe or does not have a usable taught solution."""


def validate_task(config):
    """Validate reach, safe height, taught solutions, and joint limits."""
    for name in ('pick_point_xyz', 'place_point_xyz'):
        point = config.get(name)
        if not isinstance(point, (list, tuple)) or len(point) != 3:
            raise SafetyError(f'{name}: missing or malformed Cartesian target')
        radial = hypot(float(point[0]), float(point[1]))
        if radial < config['reach_min_m'] or radial > config['reach_max_m']:
            raise SafetyError(
                f'{name}: unreachable radius {radial:.3f} m; allowed '
                f"[{config['reach_min_m']:.3f}, {config['reach_max_m']:.3f}] m")

    if config['safe_height_m'] < 0.10:
        raise SafetyError('safe_height_m must be at least 0.10 m')

    lower = config.get('joint_lower_limits', [])
    upper = config.get('joint_upper_limits', [])
    if len(lower) != 6 or len(upper) != 6:
        raise SafetyError('six lower and upper joint limits are required')
    for pose_name in ARM_POSES:
        pose = config.get(pose_name)
        if not isinstance(pose, (list, tuple)) or len(pose) != 6:
            raise SafetyError(f'{pose_name}: no six-joint IK/teaching solution')
        for index, (value, low, high) in enumerate(zip(pose, lower, upper), 1):
            if not low <= value <= high:
                raise SafetyError(
                    f'{pose_name}: joint{index}={value:.3f} exceeds '
                    f'[{low:.3f}, {high:.3f}]')
    return True
