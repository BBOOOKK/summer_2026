//
// Created by stewart on 9/20/20.
//

#include <algorithm>
#include <cmath>
#include <eigen_conversions/eigen_msg.h>
#include <geometry_msgs/PoseArray.h>
#include <nav_msgs/Odometry.h>
#include <ros/ros.h>
#include <trajectory_msgs/MultiDOFJointTrajectory.h>

#include <mav_trajectory_generation/polynomial_optimization_linear.h>
#include <mav_trajectory_generation/trajectory.h>

#include <tf/transform_datatypes.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.h>
#include <eigen3/Eigen/Dense>

class WaypointFollower {
  [[maybe_unused]] ros::Subscriber currentStateSub;
  [[maybe_unused]] ros::Subscriber poseArraySub;
  ros::Publisher desiredStatePub;

  // Current state
  bool state_received = false;
  double current_yaw = 0.0;
  Eigen::Vector3d x;  // current position of the UAV's c.o.m. in the world frame

  ros::Timer desiredStateTimer;

  ros::Time trajectoryStartTime;
  mav_trajectory_generation::Trajectory trajectory;
  mav_trajectory_generation::Trajectory yaw_trajectory;

  void onCurrentState(nav_msgs::Odometry const& cur_state) {
    // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    //  PART 1.1 |  16.485 - Fall 2021  - Lab 4 coding assignment (5 pts)
    // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
    // ~
    //
    //  Populate the variable x, which encodes the current world position of the
    //  UAV
    // ~~~~ begin solution
    x << cur_state.pose.pose.position.x, cur_state.pose.pose.position.y,
         cur_state.pose.pose.position.z;
    current_yaw = tf::getYaw(cur_state.pose.pose.orientation);
    state_received = true;
    // ~~~~ end solution
    // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
    // ~
    //                                 end part 1.1
    // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  }

  void generateOptimizedTrajectory(geometry_msgs::PoseArray const& poseArray) {
    if (!state_received) { ROS_WARN("Waiting for current state"); return; }
    if (poseArray.poses.size() < 1) {
      ROS_ERROR("Must have at least one pose to generate trajectory!");
      trajectory.clear();
      yaw_trajectory.clear();
      return;
    }

    if (!trajectory.empty()) return;

    // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    //  PART 1.2 |  16.485 - Fall 2021  - Lab 4 coding assignment (35 pts)
    // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
    // ~
    //
    //  We are using the mav_trajectory_generation library
    //  (https://github.com/ethz-asl/mav_trajectory_generation) to perform
    //  trajectory optimization given the waypoints (based on the position and
    //  orientation of the gates on the race course).
    //  We will be finding the trajectory for the position and the trajectory
    //  for the yaw in a decoupled manner.
    //  In this section:
    //  1. Fill in the correct number for D, the dimension we should apply to
    //  the solver to find the positional trajectory
    //  2. Correctly populate the Vertex::Vector structure below (vertices,
    //  yaw_vertices) using the position of the waypoints and the yaw of the
    //  waypoints respectively
    //
    //  Hints:
    //  1. Use vertex.addConstraint(POSITION, position) where position is of
    //  type Eigen::Vector3d to enforce a waypoint position.
    //  2. Use vertex.addConstraint(ORIENTATION, yaw) where yaw is a double
    //  to enforce a waypoint yaw.
    //  3. Remember angle wraps around 2 pi. Be careful!
    //  4. For the ending waypoint for position use .makeStartOrEnd as seen with
    //  the starting waypoint instead of .addConstraint as you would do for the
    //  other waypoints.
    //
    // ~~~~ begin solution

    const int D = 3;  // dimension of each vertex in the trajectory
    mav_trajectory_generation::Vertex start_position(D), end_position(D);
    mav_trajectory_generation::Vertex::Vector vertices;
    mav_trajectory_generation::Vertex start_yaw(1), end_yaw(1);
    mav_trajectory_generation::Vertex::Vector yaw_vertices;

    // ============================================
    // Convert the pose array to a list of vertices
    // ============================================

    // Start from the current position and zero orientation
    using namespace mav_trajectory_generation::derivative_order;
    start_position.makeStartOrEnd(x, SNAP);
    vertices.push_back(start_position);
    start_yaw.makeStartOrEnd(Eigen::VectorXd::Constant(1, current_yaw), SNAP);
    yaw_vertices.push_back(start_yaw);

    double last_yaw = current_yaw;
    for (auto i = 0; i < poseArray.poses.size(); ++i) {
      const auto& pose = poseArray.poses[i];
      Eigen::Vector3d position(pose.position.x, pose.position.y, pose.position.z);
      mav_trajectory_generation::Vertex vertex(D), yaw_vertex(1);
      const double raw_yaw = tf::getYaw(pose.orientation);
      const double yaw = last_yaw + std::atan2(std::sin(raw_yaw - last_yaw),
                                             std::cos(raw_yaw - last_yaw));
      if (i + 1 == poseArray.poses.size()) {
        vertex.makeStartOrEnd(position, SNAP);
        yaw_vertex.makeStartOrEnd(Eigen::VectorXd::Constant(1, yaw), SNAP);
      } else {
        vertex.addConstraint(POSITION, position);
        yaw_vertex.addConstraint(ORIENTATION, yaw);
      }
      vertices.push_back(vertex);
      yaw_vertices.push_back(yaw_vertex);
      last_yaw = yaw;
    }

    // ~~~~ end solution
    // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
    // ~
    //                                 end part 1.2
    // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    // ============================================================
    // Estimate the time to complete each segment of the trajectory
    // ============================================================

    // HINT: play with these segment times and see if you can finish
    // the race course faster!
    std::vector<double> segment_times;
    const double v_max = 8.0;
    const double a_max = 4.0;
    segment_times = estimateSegmentTimes(vertices, v_max, a_max);

    // =====================================================
    // Solve for the optimized trajectory (linear optimizer)
    // =====================================================
    // Position
    const int N = 10;
    mav_trajectory_generation::PolynomialOptimization<N> opt(D);
    opt.setupFromVertices(vertices, segment_times, SNAP);
    opt.solveLinear();

    // Yaw
    mav_trajectory_generation::PolynomialOptimization<N> yaw_opt(1);
    yaw_opt.setupFromVertices(yaw_vertices, segment_times, SNAP);
    yaw_opt.solveLinear();

    // ============================
    // Get the optimized trajectory
    // ============================
    mav_trajectory_generation::Segment::Vector segments;
    //        opt.getSegments(&segments); // Unnecessary?
    opt.getTrajectory(&trajectory);
    yaw_opt.getTrajectory(&yaw_trajectory);
    trajectoryStartTime = ros::Time::now();

    ROS_INFO("Generated optimizes trajectory from %d waypoints",
             vertices.size());
  }

  void publishDesiredState(ros::TimerEvent const& ev) {
    if (trajectory.empty()) return;

    // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    //  PART 1.3 |  16.485 - Fall 2021  - Lab 4 coding assignment (15 pts)
    // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
    // ~
    //
    //  Finally we get to send commands to our controller! First fill in
    //  properly the value for 'nex_point.time_from_start' and 'sampling_time'
    //  (hint: not 0) and after extracting the state information from our
    //  optimized trajectory, finish populating next_point.
    //
    // ~~~~ begin solution
    trajectory_msgs::MultiDOFJointTrajectoryPoint next_point;
    double sampling_time = std::max(0.0, (ros::Time::now() - trajectoryStartTime).toSec());
    if (sampling_time > trajectory.getMaxTime())
      sampling_time = trajectory.getMaxTime();

    // Getting the desired state based on the optimized trajectory we found.
    using namespace mav_trajectory_generation::derivative_order;
    Eigen::Vector3d des_position = trajectory.evaluate(sampling_time, POSITION);
    Eigen::Vector3d des_velocity = trajectory.evaluate(sampling_time, VELOCITY);
    Eigen::Vector3d des_accel =
        trajectory.evaluate(sampling_time, ACCELERATION);
    Eigen::VectorXd des_orientation =
        yaw_trajectory.evaluate(sampling_time, ORIENTATION);
    ROS_INFO("Traversed %f percent of the trajectory.",
             sampling_time / trajectory.getMaxTime() * 100);

    next_point.time_from_start = ros::Duration(sampling_time);
    next_point.transforms.resize(1);
    next_point.velocities.resize(1);
    next_point.accelerations.resize(1);
    auto& transform = next_point.transforms[0];
    transform.translation.x = des_position.x();
    transform.translation.y = des_position.y();
    transform.translation.z = des_position.z();
    transform.rotation = tf::createQuaternionMsgFromYaw(des_orientation[0]);
    auto& velocity = next_point.velocities[0];
    velocity.linear.x = des_velocity.x();
    velocity.linear.y = des_velocity.y();
    velocity.linear.z = des_velocity.z();
    velocity.angular.z = yaw_trajectory.evaluate(sampling_time, VELOCITY)[0];
    auto& acceleration = next_point.accelerations[0];
    acceleration.linear.x = des_accel.x();
    acceleration.linear.y = des_accel.y();
    acceleration.linear.z = des_accel.z();
    acceleration.angular.z = yaw_trajectory.evaluate(sampling_time, ACCELERATION)[0];
    desiredStatePub.publish(next_point);

    // ~~~~ end solution
    // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
    // ~
    //                                 end part 1.3
    // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  }

 public:
  explicit WaypointFollower(ros::NodeHandle& nh) {
    currentStateSub = nh.subscribe(
        "/current_state", 1, &WaypointFollower::onCurrentState, this);
    poseArraySub = nh.subscribe("/desired_traj_vertices",
                                1,
                                &WaypointFollower::generateOptimizedTrajectory,
                                this);
    desiredStatePub =
        nh.advertise<trajectory_msgs::MultiDOFJointTrajectoryPoint>(
            "/desired_state", 1);
    desiredStateTimer = nh.createTimer(
        ros::Rate(5), &WaypointFollower::publishDesiredState, this);
    desiredStateTimer.start();
  }
};

int main(int argc, char** argv) {
  ros::init(argc, argv, "trajectory_generation_node");
  ros::NodeHandle nh;

  WaypointFollower waypointFollower(nh);

  ros::spin();
  return 0;
}
