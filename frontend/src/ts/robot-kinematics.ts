import type { Quaternion, RobotJoint, Vector3 } from './types.js';

export interface RigidPose {
  position: Vector3;
  quaternion: Quaternion;
}

function normalizeQuaternion(value: Quaternion): Quaternion {
  const length = Math.hypot(...value);
  if (length < 1e-12) return [0, 0, 0, 1];
  return value.map((component) => component / length) as Quaternion;
}

function multiplyQuaternions(left: Quaternion, right: Quaternion): Quaternion {
  const [lx, ly, lz, lw] = left;
  const [rx, ry, rz, rw] = right;
  return [
    lw * rx + lx * rw + ly * rz - lz * ry,
    lw * ry - lx * rz + ly * rw + lz * rx,
    lw * rz + lx * ry - ly * rx + lz * rw,
    lw * rw - lx * rx - ly * ry - lz * rz,
  ];
}

function rotateVector(quaternion: Quaternion, vector: Vector3): Vector3 {
  const rotation = normalizeQuaternion(quaternion);
  const inverse: Quaternion = [-rotation[0], -rotation[1], -rotation[2], rotation[3]];
  const result = multiplyQuaternions(
    multiplyQuaternions(rotation, [...vector, 0]),
    inverse,
  );
  return result.slice(0, 3) as Vector3;
}

function compose(left: RigidPose, right: RigidPose): RigidPose {
  const offset = rotateVector(left.quaternion, right.position);
  return {
    position: left.position.map(
      (component, index) => component + offset[index],
    ) as Vector3,
    quaternion: normalizeQuaternion(
      multiplyQuaternions(left.quaternion, right.quaternion),
    ),
  };
}

function inverse(value: RigidPose): RigidPose {
  const rotation = normalizeQuaternion(value.quaternion);
  const quaternion: Quaternion = [-rotation[0], -rotation[1], -rotation[2], rotation[3]];
  return {
    position: rotateVector(
      quaternion,
      value.position.map((component) => -component) as Vector3,
    ),
    quaternion,
  };
}

function normalizedAxis(value: Vector3): Vector3 {
  const length = Math.hypot(...value);
  if (length < 1e-12) return [0, 0, 0];
  return value.map((component) => component / length) as Vector3;
}

function jointMotion(joint: RobotJoint): RigidPose {
  if (joint.type === 'fixed') {
    return { position: [0, 0, 0], quaternion: [0, 0, 0, 1] };
  }
  const axis = normalizedAxis(joint.axis);
  if (joint.type === 'prismatic') {
    return {
      position: axis.map(
        (component) => component * joint.initial_position,
      ) as Vector3,
      quaternion: [0, 0, 0, 1],
    };
  }
  const halfAngle = joint.initial_position / 2;
  const sine = Math.sin(halfAngle);
  return {
    position: [0, 0, 0],
    quaternion: [
      axis[0] * sine,
      axis[1] * sine,
      axis[2] * sine,
      Math.cos(halfAngle),
    ],
  };
}

/** Evaluate T_parent_joint * Motion(q) * inverse(T_child_joint). */
export function jointLocalPose(joint: RobotJoint): RigidPose | null {
  if (!joint.parent_frame || !joint.child_frame) return null;
  return compose(
    compose(joint.parent_frame, jointMotion(joint)),
    inverse(joint.child_frame),
  );
}
