#!/usr/bin/env python3
"""Verify that the smoke payload is held, detached, and released under gravity."""

import json
import sys
import time

from gazebo_msgs.srv import GetEntityState
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger


class SmokeVerifier(Node):
    """Synchronous client used only by the self-contained smoke world."""

    def __init__(self) -> None:
        super().__init__('grasp_joint_smoke_verifier')
        self.status = self.create_client(Trigger, '/grasp/status')
        self.detach = self.create_client(Trigger, '/grasp/detach')
        self.get_state = self.create_client(GetEntityState, '/gazebo/get_entity_state')

    def call(self, client, request, timeout: float = 5.0):
        if not client.wait_for_service(timeout_sec=timeout):
            raise RuntimeError(f'服务未就绪：{client.srv_name}')
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        if not future.done():
            raise RuntimeError(f'服务调用超时：{client.srv_name}')
        error = future.exception()
        if error is not None:
            raise RuntimeError(f'服务调用异常：{client.srv_name}: {error}')
        return future.result()

    def payload_z(self) -> float:
        request = GetEntityState.Request()
        request.name = 'test_payload'
        request.reference_frame = 'world'
        response = self.call(self.get_state, request)
        if not response.success:
            raise RuntimeError('Gazebo 拒绝读取 test_payload')
        return float(response.state.pose.position.z)


def run() -> int:
    rclpy.init()
    node = SmokeVerifier()
    try:
        deadline = time.monotonic() + 8.0
        status = None
        while time.monotonic() < deadline:
            status = node.call(node.status, Trigger.Request(), timeout=2.0)
            if status.success and 'attached=true' in status.message:
                break
            time.sleep(0.1)
        if status is None or 'attached=true' not in status.message:
            raise RuntimeError(f'插件未进入附着状态：{getattr(status, "message", "无响应")}')

        held_z_first = node.payload_z()
        time.sleep(0.4)
        held_z_second = node.payload_z()
        if abs(held_z_second - held_z_first) > 1.0e-4:
            raise RuntimeError(
                f'附着期间负载漂移：{held_z_first:.6f} -> {held_z_second:.6f} m',
            )

        detached = node.call(node.detach, Trigger.Request())
        if not detached.success:
            raise RuntimeError(f'拆除 fixed joint 失败：{detached.message}')
        time.sleep(0.5)
        released_z = node.payload_z()
        if released_z > held_z_second - 0.20:
            raise RuntimeError(
                f'拆除后负载未明显下落：{held_z_second:.6f} -> {released_z:.6f} m',
            )

        print(
            json.dumps(
                {
                    'result': 'GRASP_JOINT_SMOKE_PASS',
                    'held_z_first': round(held_z_first, 6),
                    'held_z_second': round(held_z_second, 6),
                    'released_z': round(released_z, 6),
                    'detach_message': detached.message,
                },
                ensure_ascii=False,
            ),
        )
        return 0
    except Exception as error:  # The CLI must report a concise acceptance failure.
        print(f'GRASP_JOINT_SMOKE_FAIL: {error}', file=sys.stderr)
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(run())
