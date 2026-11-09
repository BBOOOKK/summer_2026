# Unity drone race: 0.640 s

The controller follows the included rigid-body reference using feedforward rotor commands and state feedback. Gate-to-gate timing uses the Unity simulation clock.

## Launch

On the configured Windows/WSL machine, open PowerShell in this directory and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\local\Start-SubsecondInteractive.ps1"
```

The control panel provides Start/Restart, Reset, and Stop. The Unity view opens at `http://localhost:6085/vnc.html?autoconnect=1&resize=scale`. Clicking the Unity window and pressing R resets the drone and stops the controller.

The launcher uses WSL Ubuntu-22.04 and the ROS Noetic/Unity installation at `/opt/vnav-lab4`. The simulator and ROS installation are separate runtime dependencies.

## Main files

| File | Purpose |
|---|---|
| `scripts/rigid_reference_node.py` | Reads the simulator state and publishes four rotor speeds. |
| `scripts/optimize_rigid_race.py` | Solves the rigid-body trajectory optimization problem. |
| `scripts/race_timer.py` | Times ordered gate crossings with position/velocity interpolation. |
| `scripts/read_flight_data.py` | Reads flight measurements and collision events from the rosbag. |
| `local/interactive_app.py` | Runs the Unity view, controller, timer, and video recording. |
| `local/subsecond_profile.json` | Selects the reference trajectory and feedback gains. |
| `results/reference_subsecond/…/reference.csv` | Contains the reference sampled at 20 ms intervals. |
| `local/interpolation_fix/level0` | Configures the scene to display the current physics pose. |

The rotor speed limit is ±2000 rad/s. Synchronous stepping and frame capture make wall-clock execution longer than the measured simulation interval. The C++ course nodes remain available for the baseline mode; the 0.640 s configuration uses the Python rigid-body controller.

Trajectory optimization requires NumPy, SciPy, and CasADi. Controller execution uses the ROS Noetic environment.
