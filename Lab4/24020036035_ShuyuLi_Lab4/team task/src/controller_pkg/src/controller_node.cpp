#include <ros/ros.h>

#include <tf2_geometry_msgs/tf2_geometry_msgs.h>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/utils.h>
#include <mav_msgs/Actuators.h>
#include <nav_msgs/Odometry.h>
#include <trajectory_msgs/MultiDOFJointTrajectoryPoint.h>
#include <cmath>
#include <algorithm>
#include <std_msgs/Float64MultiArray.h>

#define PI M_PI

// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
//  PART 0 |  16.485 - Fall 2019  - Lab 3 coding assignment
// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
//
//  In this code, we ask you to implement a geometric controller for a
//  simulated UAV, following the publication:
//
//  [1] Lee, Taeyoung, Melvin Leoky, N. Harris McClamroch. "Geometric tracking
//      control of a quadrotor UAV on SE (3)." Decision and Control (CDC),
//      49th IEEE Conference on. IEEE, 2010
//
//  We use variable names as close as possible to the conventions found in the
//  paper, however, we have slightly different conventions for the aerodynamic
//  coefficients of the propellers (refer to the lecture notes for these).
//  Additionally, watch out for the different conventions on reference frames
//  (see Lab 3 Handout for more details).
//
//  The include below is strongly suggested [but not mandatory if you have
//  better alternatives in mind :)]. Eigen is a C++ library for linear algebra
//  that will help you significantly with the implementation. Check the
//  quick reference page to learn the basics:
//
//  https://eigen.tuxfamily.org/dox/group__QuickRefPage.html

#include <eigen3/Eigen/Dense>

// If you choose to use Eigen, tf2 provides useful functions to convert tf2
// messages to eigen types and vice versa.
#include <tf2_eigen/tf2_eigen.h>

// ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
//                                 end part 0
// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class controllerNode{
  ros::NodeHandle nh;

  // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  //  PART 1 |  Declare ROS callback handlers
  // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
  //
  // In this section, you need to declare:
  //   1. two subscribers (for the desired and current UAVStates)
  //   2. one publisher (for the propeller speeds)
  //   3. a timer for your main control loop
  //
  // ~~~~ begin solution
  //
  ros::Subscriber desired_sub, current_sub;
  ros::Publisher rotor_pub, diagnostic_pub;
  ros::Timer control_timer;
  bool have_desired = false, have_current = false;
  bool yaw_rate_feedforward = false, drag_compensation = false;
  bool attitude_rate_feedforward = false, have_nominal = false;
  Eigen::Matrix3d previous_nominal;
  Eigen::Vector3d nominal_rate_world = Eigen::Vector3d::Zero();
  Eigen::Vector3d nominal_accel_world = Eigen::Vector3d::Zero();
  double attitude_accel_feedforward = 0.0;
  double yaw_kr, yaw_komega;
  bool prioritize_thrust_tilt = false;
  bool feedback_attitude_rate = false, have_feedback_attitude = false;
  Eigen::Matrix3d previous_feedback_attitude;
  Eigen::Vector3d feedback_rate_world = Eigen::Vector3d::Zero();
  double previous_feedback_time = 0, kz, kvz;
  double minimum_vertical_force = 0.0;
  bool rate_tracking = false, state_control = false, reversible_thrust = false;
  bool thrust_axis_only = false;
  bool analytic_thrust_rate = false;
  Eigen::Vector3d desired_jerk = Eigen::Vector3d::Zero();
  double attitude_gain = 12.0, rate_gain = 20.0, max_body_rate = 6.8;
  Eigen::Matrix3d physical_inertia = Eigen::Vector3d(.1,.2,.1).asDiagonal();
  double previous_plan_time = 0;
  double drag_scale = 1.0;
  double yaw_rate = 0.0, max_rotor_speed = 200.0;
  //
  // ~~~~ end solution
  // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
  //                                 end part 1
  // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

  // Controller parameters
  double kx, kv, kr, komega; // controller gains - [1] eq (15), (16)

  // Physical constants (we will set them below)
  double m;              // mass of the UAV
  double g;              // gravity acceleration
  double d;              // distance from the center of propellers to the c.o.m.
  double cf,             // Propeller lift coefficient
         cd;             // Propeller drag coefficient
  Eigen::Matrix3d J;     // Inertia Matrix
  Eigen::Vector3d e3;    // [0,0,1]
  Eigen::MatrixXd F2W;   // Wrench-rotor speeds map

  // Controller internals (you will have to set them below)
  // Current state
  Eigen::Vector3d x;     // current position of the UAV's c.o.m. in the world frame
  Eigen::Vector3d v;     // current velocity of the UAV's c.o.m. in the world frame
  Eigen::Matrix3d R;     // current orientation of the UAV
  Eigen::Vector3d omega; // current angular velocity of the UAV's c.o.m. in the *body* frame

  // Desired state
  Eigen::Vector3d xd;    // desired position of the UAV's c.o.m. in the world frame
  Eigen::Vector3d vd;    // desired velocity of the UAV's c.o.m. in the world frame
  Eigen::Vector3d ad;    // desired acceleration of the UAV's c.o.m. in the world frame
  double yawd;           // desired yaw angle

  double hz;             // frequency of the main control loop


  static Eigen::Vector3d Vee(const Eigen::Matrix3d& in){
    Eigen::Vector3d out;
    out << in(2,1), in(0,2), in(1,0);
    return out;
  }

  static double signed_sqrt(double val){
    return val>0?sqrt(val):-sqrt(-val);
  }

public:
  controllerNode():e3(0,0,1),F2W(4,4),hz(1000.0){

      // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
      //  PART 2 |  Initialize ROS callback handlers
      // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
      //
      // In this section, you need to initialize your handlers from part 1.
      // Specifically:
      //  - bind controllerNode::onDesiredState() to the topic "desired_state"
      //  - bind controllerNode::onCurrentState() to the topic "current_state"
      //  - bind controllerNode::controlLoop() to the created timer, at frequency
      //    given by the "hz" variable
      //
      // Hints: 
      //  - use the nh variable already available as a class member
      //  - read the lab 3 handout to fnd the message type
      //
      // ~~~~ begin solution
      //
      desired_sub = nh.subscribe("desired_state", 1, &controllerNode::onDesiredState, this);
      current_sub = nh.subscribe("current_state", 1, &controllerNode::onCurrentState, this);
      rotor_pub = nh.advertise<mav_msgs::Actuators>("rotor_speed_cmds", 1);
      diagnostic_pub = nh.advertise<std_msgs::Float64MultiArray>("controller_diagnostics", 1);
      nh.param("control_hz", hz, 1000.0);
      nh.param("yaw_rate_feedforward", yaw_rate_feedforward, false);
      nh.param("drag_compensation", drag_compensation, false);
      nh.param("attitude_rate_feedforward", attitude_rate_feedforward, false);
      nh.param("attitude_accel_feedforward", attitude_accel_feedforward, 0.0);
      nh.param("drag_scale", drag_scale, 1.0);
      nh.param("max_rotor_speed", max_rotor_speed, 200.0);
      control_timer = nh.createTimer(ros::Duration(1.0/hz), &controllerNode::controlLoop, this);
      //
      // ~~~~ end solution

      // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
      //                                 end part 2
      // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


      // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
      //  PART 6 [NOTE: save this for last] |  Tune your gains!
      // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
      //
      // Live the life of a control engineer! Tune these parameters for a fast
      // and accurate controller.
      //
      // Controller gains
      //
      //
      // **** FIDDLE WITH THESE! ***
      // Change them in the provided launch file.
      nh.param("kx", kx, 6.0);
      nh.param("kv", kv, 4.0);
      nh.param("kr", kr, 12.0);
      nh.param("komega", komega, 6.0);
      nh.param("yaw_kr", yaw_kr, kr);
      nh.param("yaw_komega", yaw_komega, komega);
      nh.param("prioritize_thrust_tilt", prioritize_thrust_tilt, false);
      nh.param("feedback_attitude_rate", feedback_attitude_rate, false);
      nh.param("kz", kz, kx);
      nh.param("kvz", kvz, kv);
      nh.param("minimum_vertical_force", minimum_vertical_force, 0.0);
      nh.param("rate_tracking", rate_tracking, false);
      nh.param("state_control", state_control, false);
      nh.param("reversible_thrust", reversible_thrust, false);
      nh.param("thrust_axis_only", thrust_axis_only, false);
      nh.param("analytic_thrust_rate", analytic_thrust_rate, false);
      nh.param("attitude_gain", attitude_gain, 12.0);
      nh.param("rate_gain", rate_gain, 20.0);
      nh.param("max_body_rate", max_body_rate, 6.8);
      ROS_INFO("Gain values:\nkx: %f \nkv: %f \nkr: %f \nkomega: %f\n", kx, kv, kr, komega);

      //
      // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
      //                                 end part 6
      // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

      // Initialize constants
      m = 1.0;
      cd = 1e-5;
      cf = 1e-3;
      g = 9.81;
      d = 0.3;
      J << 1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0;
  }

  void onDesiredState(const trajectory_msgs::MultiDOFJointTrajectoryPoint& des_state){

      // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
      //  PART 3 | Objective: fill in xd, vd, ad, yawd
      // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
      //
      // 3.1 Get the desired position, velocity and acceleration from the in-
      //     coming ROS message and fill in the class member variables xd, vd
      //     and ad accordingly. You can ignore the angular acceleration.
      //
      // Hint: use "v << vx, vy, vz;" to fill in a vector with Eigen.
      //
      // ~~~~ begin solution
      //
      if (des_state.transforms.empty() || des_state.velocities.empty() ||
          des_state.accelerations.empty()) return;
      const auto& t = des_state.transforms[0].translation;
      const auto& vel = des_state.velocities[0].linear;
      const auto& acc = des_state.accelerations[0].linear;
      xd << t.x, t.y, t.z;
      vd << vel.x, vel.y, vel.z;
      ad << acc.x, acc.y, acc.z;
      const auto& jerk=des_state.accelerations[0].angular;
      desired_jerk << jerk.x,jerk.y,jerk.z;
      yaw_rate = des_state.velocities[0].angular.z;
      //
      // ~~~~ end solution
      //
      // 3.2 Extract the yaw component from the quaternion in the incoming ROS
      //     message and store in the yawd class member variable
      //
      //  Hints:
      //    - use the methods tf2::getYaw(...)
      //    - maybe you want to use also tf2::fromMsg(...)
      //
      // ~~~~ begin solution
      //
      yawd = tf2::getYaw(des_state.transforms[0].rotation);
      if (attitude_rate_feedforward) {
        Eigen::Vector3d force = ad + g*e3;
        if(minimum_vertical_force>0) force.z()=std::max(force.z(),minimum_vertical_force/m);
        const Eigen::Vector3d heading(std::cos(yawd),std::sin(yawd),0);
        if (force.norm()>1e-6 && force.normalized().cross(heading).norm()>1e-6) {
          Eigen::Matrix3d nominal;
          nominal.col(2)=force.normalized();
          nominal.col(1)=nominal.col(2).cross(heading).normalized();
          nominal.col(0)=nominal.col(1).cross(nominal.col(2));
          const double time=des_state.time_from_start.toSec(), dt=time-previous_plan_time;
          if(have_nominal && dt>1e-5 && dt<.1) {
            const Eigen::AngleAxisd delta(previous_nominal.transpose()*nominal);
            const Eigen::Vector3d new_rate=previous_nominal*(delta.axis()*delta.angle()/dt);
            Eigen::Vector3d accel=(new_rate-nominal_rate_world)/dt;
            // Numerical differentiation is bounded and low-pass filtered;
            // this is an optional torque feedforward, not a dynamics change.
            if(accel.norm()>30.) accel*=30./accel.norm();
            nominal_accel_world += (dt/(.03+dt))*(accel-nominal_accel_world);
            nominal_rate_world=new_rate;
          } else if(!have_nominal || dt<0 || dt>=.1 ||
                    (vd.norm()<1e-6 && ad.norm()<1e-6 && std::abs(yaw_rate)<1e-6)) {
            nominal_rate_world.setZero();nominal_accel_world.setZero();
          }
          // /clock advances in 20 ms steps, while the planner timer is 10 ms.
          // Duplicate reference stamps must retain the last rate estimate:
          // resetting it here intermittently disables feedforward every tick.
          previous_nominal=nominal; previous_plan_time=time; have_nominal=true;
        }
      }
      have_desired = true;
      //
      // ~~~~ end solution
      //
      // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
      //                                 end part 3
      // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  }

  void onCurrentState(const nav_msgs::Odometry& cur_state){
      // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
      //  PART 4 | Objective: fill in x, v, R and omega
      // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
      //
      // Get the current position and velocity from the incoming ROS message and
      // fill in the class member variables x, v, R and omega accordingly.
      //
      //  CAVEAT: cur_state.twist.twist.angular is in the world frame, while omega
      //          needs to be in the body frame!
      //
      // ~~~~ begin solution
      //
      const auto& p = cur_state.pose.pose.position;
      const auto& vel = cur_state.twist.twist.linear;
      const auto& rate = cur_state.twist.twist.angular;
      const auto& q = cur_state.pose.pose.orientation;
      Eigen::Quaterniond quat(q.w, q.x, q.y, q.z);
      if (quat.norm() < 1e-8) return;
      R = quat.normalized().toRotationMatrix();
      x << p.x, p.y, p.z;
      v << vel.x, vel.y, vel.z;
      // Lab3's quadrotor bridge supplies BOTH twists in the world frame.
      omega = R.transpose() * Eigen::Vector3d(rate.x, rate.y, rate.z);
      have_current = true;
      if(state_control) controlLoop(ros::TimerEvent());
      //
      // ~~~~ end solution
      //
      // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
      //                                 end part 4
      // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  }

  void controlLoop(const ros::TimerEvent& t){
    if(state_control && t.current_real != ros::Time()) return;
    Eigen::Vector3d ex, ev, er, eomega;

    // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    //  PART 5 | Objective: Implement the controller!
    // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
    //
    // 5.1 Compute position and velocity errors. Objective: fill in ex, ev.
    //  Hint: [1], eq. (6), (7)
    //
    // ~~~~ begin solution
    //
    if (!have_desired || !have_current) return;
    ex = x - xd;
    ev = v - vd;
    //
    // ~~~~ end solution

    // 5.2 Compute the Rd matrix.
    //
    //  Hint: break it down in 3 parts:
    //    - b3d vector = z-body axis of the quadrotor, [1] eq. (12)
    //    - check out [1] fig. (3) for the remaining axes [use cross product]
    //    - assemble the Rd matrix, eigen offers: "MATRIX << col1, col2, col3"
    //
    //  CAVEATS:
    //    - Compare the reference frames in the Lab 3 handout with Fig. 1 in the
    //      paper. The z-axes are flipped, which affects the signs of:
    //         i) the gravity term and
    //        ii) the overall sign (in front of the fraction) in equation (12)
    //            of the paper
    //    - remember to normalize your axes!
    //
    // ~~~~ begin solution
    //
    Eigen::Vector3d A = -kx*ex - kv*ev + m*g*e3 + m*ad;
    A.z() += (kx-kz)*ex.z()+(kv-kvz)*ev.z();
    if (drag_compensation) {
      const Eigen::Vector3d vb = R.transpose()*v;
      const Eigen::Vector3d db(0.1, 0.1, 0.2);
      const Eigen::Vector3d Fdb = -db.cwiseProduct(vb.cwiseProduct(vb.cwiseAbs()));
      A -= drag_scale*R*Fdb;
    }
    // Keep the commanded thrust direction upright when a compressed height
    // spline briefly asks for downward acceleration beyond free fall.
    if(minimum_vertical_force>0 && ad.z()<minimum_vertical_force/m-g)
      A.z()=std::max(A.z(),minimum_vertical_force);
    if (A.norm() < 1e-8) return;
    Eigen::Vector3d b3d = A.normalized();
    if(reversible_thrust && b3d.dot(R.col(2))<0) b3d=-b3d;
    Eigen::Vector3d b1heading(std::cos(yawd), std::sin(yawd), 0.0);
    Eigen::Vector3d cross = b3d.cross(b1heading);
    if (cross.norm() < 1e-8) cross = b3d.cross(Eigen::Vector3d::UnitY());
    const Eigen::Vector3d b2d = cross.normalized();
    const Eigen::Vector3d b1d = b2d.cross(b3d).normalized();
    Eigen::Matrix3d Rd;
    Rd.col(0) = b1d; Rd.col(1) = b2d; Rd.col(2) = b3d;
    //
    // ~~~~ end solution
    //
    // 5.3 Compute the orientation error (er) and the rotation-rate error (eomega)
    //  Hints:
    //     - [1] eq. (10) and (11)
    //     - you can use the Vee() static method implemented above
    //
    //  CAVEAT: feel free to ignore the second addend in eq (11), since it
    //          requires numerical differentiation of Rd and it has negligible
    //          effects on the closed-loop dynamics.
    //
    // ~~~~ begin solution
    //
    er = 0.5 * Vee(Rd.transpose()*R - R.transpose()*Rd);
    // Baseline is the simplified controller explicitly allowed by the lab.
    // Optional FF is exact for a steady circle with constant tilt and yaw rate.
    Eigen::Vector3d omega_ref = Eigen::Vector3d::Zero();
    if (yaw_rate_feedforward) omega_ref = R.transpose()*(yaw_rate*e3);
    if (attitude_rate_feedforward) omega_ref = R.transpose()*nominal_rate_world;
    if (feedback_attitude_rate) {
      const double now=ros::Time::now().toSec(),dt=now-previous_feedback_time;
      if(have_feedback_attitude && dt>1e-5 && dt<.1) {
        const Eigen::AngleAxisd delta(previous_feedback_attitude.transpose()*Rd);
        Eigen::Vector3d rate=previous_feedback_attitude*(delta.axis()*delta.angle()/dt);
        if(rate.norm()>20.) rate*=20./rate.norm();
        feedback_rate_world += (dt/(.02+dt))*(rate-feedback_rate_world);
      } else if(!have_feedback_attitude || dt<0 || dt>=.1) feedback_rate_world.setZero();
      // Keep the previous distinct sample when callbacks share /clock.
      if(!have_feedback_attitude || dt>1e-5) {
        previous_feedback_attitude=Rd;previous_feedback_time=now;have_feedback_attitude=true;
      }
      omega_ref=R.transpose()*feedback_rate_world;
    }
    eomega = omega - omega_ref;
    //
    // ~~~~ end solution
    //
    // 5.4 Compute the desired wrench (force + torques) to control the UAV.
    //  Hints:
    //     - [1] eq. (15), (16)

    // CAVEATS:
    //    - Compare the reference frames in the Lab 3 handout with Fig. 1 in the
    //      paper. The z-axes are flipped, which affects the signs of:
    //         i) the gravity term
    //        ii) the overall sign (in front of the bracket) in equation (15)
    //            of the paper
    //
    //    - feel free to ignore all the terms involving \Omega_d and its time
    //      derivative as they are of the second order and have negligible
    //      effects on the closed-loop dynamics.
    //
    // ~~~~ begin solution
    //
    const double thrust = A.dot(R*e3);
    Eigen::Vector3d moment = -kr*er - komega*eomega + omega.cross(J*omega);
    moment.z() += (kr-yaw_kr)*er.z()+(komega-yaw_komega)*eomega.z();
    if (yaw_rate_feedforward || attitude_rate_feedforward) moment -= J*(omega.cross(omega_ref));
    if (attitude_rate_feedforward) moment += attitude_accel_feedforward*J*(R.transpose()*nominal_accel_world);
    if(rate_tracking) {
      // Original Unity Start() sets inertia (.1,.1,.2) in Unity axes;
      // the quadrotor-specific bridge swaps y/z, giving (.1,.2,.1).
      // Track a bounded angular rate using that actual inertia. Unity's
      // built-in rigid body integration supplies the rotational dynamics.
      Eigen::AngleAxisd delta(R.transpose()*Rd);
      Eigen::Vector3d target=attitude_gain*delta.angle()*delta.axis()+omega_ref;
      if(thrust_axis_only) {
        Eigen::Vector3d axis=R.col(2).cross(b3d);
        const double angle=std::atan2(axis.norm(),R.col(2).dot(b3d));
        target.setZero();
        if(axis.norm()>1e-8) target=R.transpose()*(attitude_gain*angle*axis.normalized());
        if(analytic_thrust_rate) {
          const Eigen::Vector3d nominal_force=ad+g*e3;
          if(nominal_force.squaredNorm()>1e-4)
            target+=R.transpose()*(nominal_force.cross(desired_jerk)/nominal_force.squaredNorm());
        }
      }
      if(target.norm()>max_body_rate) target*=max_body_rate/target.norm();
      moment=physical_inertia*(rate_gain*(target-omega));
    }
    Eigen::Vector4d wrench;
    wrench << thrust, moment.x(), moment.y(), moment.z();
    //
    // ~~~~ end solution

    // 5.5 Recover the rotor speeds from the wrench computed above
    //
    //  Hints:
    //     - [1] eq. (1)
    //
    // CAVEATs:
    //     - we have different conventions for the arodynamic coefficients,
    //       Namely: C_{\tau f} = c_d / c_f
    //               (LHS paper [1], RHS our conventions [lecture notes])
    //
    //     - Compare the reference frames in the Lab 3 handout with Fig. 1 in the
    //       paper. In the paper [1], the x-body axis [b1] is aligned with a
    //       quadrotor arm, whereas for us, it is 45° from it (i.e., "halfway"
    //       between b1 and b2). To resolve this, check out equation 6.9 in the
    //       lecture notes!
    //
    //     - The thrust forces are **in absolute value** proportional to the
    //       square of the propeller speeds. Negative propeller speeds - although
    //       uncommon - should be a possible outcome of the controller when
    //       appropriate. Note that this is the case in unity but not in real
    //       life, where propellers are aerodynamically optimized to spin in one
    //       direction!
    //
    // ~~~~ begin solution
    //
    const double arm = d/std::sqrt(2.0);
    // Rotor order: (+,+), (-,+), (-,-), (+,-); yaw signs: +,-,+,-.
    F2W << cf, cf, cf, cf,
           arm*cf, arm*cf, -arm*cf, -arm*cf,
           -arm*cf, arm*cf, arm*cf, -arm*cf,
           cd, -cd, cd, -cd;
    const Eigen::Matrix4d allocation=F2W.inverse();
    if(prioritize_thrust_tilt) {
      // Reserve actuator authority for thrust/roll/pitch before yaw. The
      // same rotor limit applies; no simulator constants are changed.
      Eigen::Vector4d primary=wrench;primary(3)=0;
      const Eigen::Vector4d base=allocation*primary, yaw_column=allocation.col(3);
      double lower=-1e9,upper=1e9,limit=max_rotor_speed*max_rotor_speed;
      for(int i=0;i<4;++i) {
        double a=(-limit-base(i))/yaw_column(i), b=(limit-base(i))/yaw_column(i);
        lower=std::max(lower,std::min(a,b));upper=std::min(upper,std::max(a,b));
      }
      if(lower<=upper) wrench(3)=std::max(lower,std::min(upper,wrench(3)));
    }
    const Eigen::Vector4d signed_squares = allocation*wrench;
    //
    // ~~~~ end solution
    //
    // 5.6 Populate and publish the control message
    //
    // Hint: do not forget that the propeller speeds are signed (maybe you want
    // to use signed_sqrt function).
    //
    // ~~~~ begin solution
    //
    mav_msgs::Actuators cmd;
    cmd.header.stamp = ros::Time::now();
    cmd.angular_velocities.resize(4);
    double saturated = 0.0;
    for (int i=0; i<4; ++i) {
      double speed = signed_sqrt(signed_squares(i));
      if (std::abs(speed) > max_rotor_speed) saturated += 1.0;
      speed = std::max(-max_rotor_speed, std::min(max_rotor_speed, speed));
      cmd.angular_velocities[i] = speed;
    }
    rotor_pub.publish(cmd);
    std_msgs::Float64MultiArray diag;
    for (int i=0; i<3; ++i) diag.data.push_back(ex(i));
    for (int i=0; i<3; ++i) diag.data.push_back(ev(i));
    for (int i=0; i<3; ++i) diag.data.push_back(er(i));
    for (int i=0; i<3; ++i) diag.data.push_back(eomega(i));
    for (int i=0; i<4; ++i) diag.data.push_back(wrench(i));
    diag.data.push_back(saturated);
    diagnostic_pub.publish(diag);
    //
    // ~~~~ end solution
    //
    // ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~
    //           end part 5, congrats! Start tuning your gains (part 6)
    // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  }
};

int main(int argc, char** argv){
  ros::init(argc, argv, "controller_node");
  controllerNode n;
  ros::spin();
}
