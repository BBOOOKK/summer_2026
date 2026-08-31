from setuptools import find_packages, setup

package_name = "object_detector"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Student",
    maintainer_email="student@example.com",
    description="YOLO desktop-object detector for ROS2.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "detector_node = object_detector.detector_node:main",
        ],
    },
)

