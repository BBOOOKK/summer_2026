from glob import glob
from setuptools import find_packages, setup

package_name = 'robot_pick_place_sim'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/urdf', glob('urdf/*')),
        ('share/' + package_name + '/worlds', glob('worlds/*')),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='Robot Integration Group',
    maintainer_email='student@example.com',
    description='mechArm 270 fixed-point pick-and-place simulation',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'acceptance_runner = robot_pick_place_sim.acceptance_runner:main',
            'object_manager = robot_pick_place_sim.object_manager:main',
            'pick_place_node = robot_pick_place_sim.pick_place_node:main',
        ],
    },
)
