import type { JointTrajectory, JointTrajectoryKeyframe } from './types.js';

export interface EditableTrajectoryKeyframe extends JointTrajectoryKeyframe {
  id: string;
}

export interface TrajectoryDraft {
  actorId: string;
  name: string;
  loop: boolean;
  keyframes: EditableTrajectoryKeyframe[];
}

const cloneTargets = (targets: Record<string, number>): Record<string, number> => ({ ...targets });

const sortKeyframes = (
  keyframes: EditableTrajectoryKeyframe[],
): EditableTrajectoryKeyframe[] => [...keyframes].sort(
  (left, right) => left.time - right.time || left.id.localeCompare(right.id),
);

export function createTrajectoryDraft(
  actorId: string,
  homeTargets: Record<string, number>,
  duration = 2,
): TrajectoryDraft {
  if (!Number.isFinite(duration) || duration <= 0) {
    throw new Error('Trajectory duration must be greater than zero');
  }
  return {
    actorId,
    name: 'Joint Motion',
    loop: false,
    keyframes: [
      { id: 'keyframe-0', time: 0, targets: cloneTargets(homeTargets) },
      { id: 'keyframe-1', time: duration, targets: cloneTargets(homeTargets) },
    ],
  };
}

export function trajectoryDraftFromTrajectory(
  actorId: string,
  trajectory: JointTrajectory,
): TrajectoryDraft {
  return {
    actorId,
    name: trajectory.name,
    loop: trajectory.loop,
    keyframes: trajectory.keyframes.map((keyframe, index) => ({
      id: `keyframe-${index}`,
      time: keyframe.time,
      targets: cloneTargets(keyframe.targets),
    })),
  };
}

export function trajectoryDuration(draft: TrajectoryDraft): number {
  return draft.keyframes.at(-1)?.time ?? 0;
}

export function setTrajectoryDuration(
  draft: TrajectoryDraft,
  duration: number,
): TrajectoryDraft {
  if (!Number.isFinite(duration) || duration <= 0) {
    throw new Error('Trajectory duration must be greater than zero');
  }
  const previousDuration = trajectoryDuration(draft);
  const scale = previousDuration > 0 ? duration / previousDuration : 1;
  const keyframes = draft.keyframes.map((keyframe, index) => ({
    ...keyframe,
    time: index === 0 ? 0 : keyframe.time * scale,
    targets: cloneTargets(keyframe.targets),
  }));
  if (keyframes.length > 1) keyframes[keyframes.length - 1].time = duration;
  return { ...draft, keyframes };
}

export function captureTrajectoryKeyframe(
  draft: TrajectoryDraft,
  id: string,
  time: number,
  targets: Record<string, number>,
): TrajectoryDraft {
  return {
    ...draft,
    keyframes: sortKeyframes([
      ...draft.keyframes.map((keyframe) => ({
        ...keyframe,
        targets: cloneTargets(keyframe.targets),
      })),
      { id, time, targets: cloneTargets(targets) },
    ]),
  };
}

export function updateTrajectoryKeyframeTime(
  draft: TrajectoryDraft,
  id: string,
  time: number,
): TrajectoryDraft {
  return {
    ...draft,
    keyframes: sortKeyframes(draft.keyframes.map((keyframe) => ({
      ...keyframe,
      time: keyframe.id === id ? time : keyframe.time,
      targets: cloneTargets(keyframe.targets),
    }))),
  };
}

export function updateTrajectoryKeyframeTarget(
  draft: TrajectoryDraft,
  id: string,
  jointId: string,
  target: number,
): TrajectoryDraft {
  return {
    ...draft,
    keyframes: draft.keyframes.map((keyframe) => ({
      ...keyframe,
      targets: keyframe.id === id
        ? { ...keyframe.targets, [jointId]: target }
        : cloneTargets(keyframe.targets),
    })),
  };
}

export function removeTrajectoryKeyframe(
  draft: TrajectoryDraft,
  id: string,
): TrajectoryDraft {
  if (draft.keyframes.length <= 2) {
    throw new Error('Trajectory must contain at least two keyframes');
  }
  return {
    ...draft,
    keyframes: draft.keyframes
      .filter((keyframe) => keyframe.id !== id)
      .map((keyframe) => ({ ...keyframe, targets: cloneTargets(keyframe.targets) })),
  };
}

export function validateTrajectoryDraft(draft: TrajectoryDraft): string[] {
  const issues: string[] = [];
  if (!draft.name.trim()) issues.push('Trajectory name cannot be empty');
  if (draft.keyframes.length < 2) {
    issues.push('Trajectory must contain at least two keyframes');
    return issues;
  }
  const expectedJointIds = Object.keys(draft.keyframes[0].targets).sort();
  if (expectedJointIds.length === 0) {
    issues.push('Trajectory keyframes must contain at least one joint target');
  }
  let previousTime: number | null = null;
  draft.keyframes.forEach((keyframe, index) => {
    if (!Number.isFinite(keyframe.time) || keyframe.time < 0) {
      issues.push(`Keyframe ${index} time must be finite and >= 0`);
    }
    if (index === 0 && keyframe.time !== 0) {
      issues.push('The first trajectory keyframe must start at time 0');
    }
    if (previousTime !== null && keyframe.time <= previousTime) {
      issues.push(`Keyframe ${index} time must be strictly increasing`);
    }
    previousTime = keyframe.time;
    const jointIds = Object.keys(keyframe.targets).sort();
    if (jointIds.join('\n') !== expectedJointIds.join('\n')) {
      issues.push(`Keyframe ${index} must target the same joint IDs as keyframe 0`);
    }
    for (const [jointId, target] of Object.entries(keyframe.targets)) {
      if (!jointId) issues.push(`Keyframe ${index} contains an empty joint ID`);
      if (!Number.isFinite(target)) {
        issues.push(`Keyframe ${index} target for ${jointId || '<empty>'} must be finite`);
      }
    }
  });
  return issues;
}

export function trajectoryFromDraft(draft: TrajectoryDraft): JointTrajectory {
  const issues = validateTrajectoryDraft(draft);
  if (issues.length) throw new Error(issues.join('; '));
  return {
    version: '1.0',
    name: draft.name.trim(),
    loop: draft.loop,
    keyframes: draft.keyframes.map(({ time, targets }) => ({
      time,
      targets: cloneTargets(targets),
    })),
  };
}
