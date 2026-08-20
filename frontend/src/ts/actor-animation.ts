import type {
  ActorLocomotionMode,
  ActorVisualAnimation,
} from './types.js';

const fallbackClipPatterns: Record<ActorLocomotionMode, RegExp[]> = {
  walking: [/^walk(?:$|[\s_-])/i, /walk/i, /jog/i],
  cycling: [/^cycl(?:e|ing)?(?:$|[\s_-])/i, /bicycle/i, /bike/i, /ride/i, /driv/i],
};

function matchingClip(available: string[], requested: string | undefined): string | null {
  if (!requested) return null;
  return available.find((name) => name === requested)
    ?? available.find((name) => name.toLocaleLowerCase() === requested.toLocaleLowerCase())
    ?? null;
}

export function selectLocomotionClipName(
  available: string[],
  animation: ActorVisualAnimation,
): string | null {
  const configured = matchingClip(available, animation.clips[animation.locomotion]);
  if (configured) return configured;
  for (const pattern of fallbackClipPatterns[animation.locomotion]) {
    const fallback = available.find((name) => pattern.test(name));
    if (fallback) return fallback;
  }
  return null;
}

export function selectIdleClipName(
  available: string[],
  animation: ActorVisualAnimation,
): string | null {
  return matchingClip(available, animation.clips.idle)
    ?? available.find((name) => /^idle(?:$|[\s_-])/i.test(name))
    ?? available.find((name) => /idle/i.test(name))
    ?? null;
}

export function playbackRateForSpeed(
  speed: number,
  animation: ActorVisualAnimation,
): number {
  const absoluteSpeed = Number.isFinite(speed) ? Math.abs(speed) : 0;
  const stopSpeed = Math.max(0, animation.stop_speed ?? 0.04);
  if (absoluteSpeed <= stopSpeed) return 0;
  const referenceSpeed = Math.max(animation.reference_speed, 1e-6);
  const minimum = Math.max(0, animation.min_playback_rate ?? 0.55);
  const maximum = Math.max(minimum, animation.max_playback_rate ?? 2.2);
  return Math.min(maximum, Math.max(minimum, absoluteSpeed / referenceSpeed));
}
