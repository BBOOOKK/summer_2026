cmake_minimum_required(VERSION 3.8)
project(robot_grasp_joint)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(gazebo_dev REQUIRED)
find_package(gazebo_msgs REQUIRED)
find_package(gazebo_ros REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)

add_library(${PROJECT_NAME} SHARED
  src/grasp_joint_plugin.cpp
)
target_include_directories(${PROJECT_NAME}
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
    ${gazebo_dev_INCLUDE_DIRS}
)
target_link_directories(${PROJECT_NAME} PRIVATE ${gazebo_dev_LIBRARY_DIRS})
target_link_libraries(${PROJECT_NAME} ${gazebo_dev_LIBRARIES})
ament_target_dependencies(${PROJECT_NAME}
  gazebo_msgs
  gazebo_ros
  rclcpp
  std_msgs
  std_srvs
)

install(
  TARGETS ${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)
install(DIRECTORY include/ DESTINATION include)
install(DIRECTORY launch models worlds DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/verify_grasp_joint.py DESTINATION lib/${PROJECT_NAME})
install(FILES README.md NOTICE DESTINATION share/${PROJECT_NAME})

ament_export_include_directories(include)
ament_export_dependencies(gazebo_dev gazebo_msgs gazebo_ros rclcpp std_msgs std_srvs)
ament_package()
