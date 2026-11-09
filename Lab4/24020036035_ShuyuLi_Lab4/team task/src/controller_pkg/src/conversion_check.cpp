#include <tf2_geometry_msgs/tf2_geometry_msgs.h>
#include <tf2_eigen/tf2_eigen.h>
#include <tf2/utils.h>
#include <Eigen/Dense>
#include <cassert>
#include <cmath>
#include <iostream>
int main() {
  geometry_msgs::Quaternion quat_msg;
  quat_msg.z=std::sin(M_PI/8); quat_msg.w=std::cos(M_PI/8);
  tf2::Quaternion quat_tf;
  tf2::fromMsg(quat_msg, quat_tf);
  geometry_msgs::Quaternion roundtrip=tf2::toMsg(quat_tf);
  Eigen::Quaterniond q_eigen;
  tf2::fromMsg(quat_msg,q_eigen);
  Eigen::Matrix3d R=q_eigen.normalized().toRotationMatrix();
  // Explicit checks survive Release builds (where assert would be disabled).
  if (std::abs(tf2::getYaw(quat_tf)-M_PI/4)>1e-12 ||
      std::abs(roundtrip.w-quat_msg.w)>1e-12 ||
      (R.transpose()*R-Eigen::Matrix3d::Identity()).norm()>1e-12 ||
      std::abs(R.determinant()-1)>1e-12) return 1;
  std::cout << "PASS: quaternion roundtrip, yaw pi/4, Eigen SO(3) matrix\n"
            << "scalar w=" << quat_tf.w() << " yaw=" << tf2::getYaw(quat_tf) << "\n" << R << "\n";
}
