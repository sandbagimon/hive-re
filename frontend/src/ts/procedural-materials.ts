import * as THREE from '../vendor/three.module.js';

export type ProceduralSurfaceKind =
  | 'concrete'
  | 'cardboard'
  | 'woven_fabric'
  | 'powder_coat'
  | 'epoxy';

interface SurfaceSample {
  shade: number;
  height: number;
  roughness: number;
}

const clamp01 = (value: number): number => Math.max(0, Math.min(value, 1));

function noise2d(x: number, y: number, seed: number): number {
  let value = Math.imul(x + seed * 17, 374761393) + Math.imul(y - seed * 29, 668265263);
  value = Math.imul(value ^ (value >>> 13), 1274126177);
  return ((value ^ (value >>> 16)) >>> 0) / 0xffffffff;
}

function surfaceSample(
  kind: ProceduralSurfaceKind,
  x: number,
  y: number,
): SurfaceSample {
  const fine = noise2d(x, y, 41);
  const medium = noise2d(Math.floor(x / 4), Math.floor(y / 4), 79);
  const coarse = noise2d(Math.floor(x / 18), Math.floor(y / 18), 113);
  if (kind === 'concrete') {
    const aggregate = fine > 0.965 ? -0.12 : fine < 0.035 ? 0.08 : 0;
    return {
      shade: clamp01(0.9 + (medium - 0.5) * 0.1 + (coarse - 0.5) * 0.08 + aggregate),
      height: clamp01(0.46 + (fine - 0.5) * 0.32 + (medium - 0.5) * 0.16),
      roughness: clamp01(0.82 + (medium - 0.5) * 0.16),
    };
  }
  if (kind === 'cardboard') {
    const fiber = Math.sin(x * 0.62 + medium * 2.4) * 0.5 + 0.5;
    const fleck = fine > 0.985 ? -0.14 : 0;
    return {
      shade: clamp01(0.91 + (medium - 0.5) * 0.08 + fleck),
      height: clamp01(0.44 + fiber * 0.14 + (fine - 0.5) * 0.08),
      roughness: clamp01(0.84 + (fine - 0.5) * 0.1),
    };
  }
  if (kind === 'woven_fabric') {
    const warp = Math.sin(x * 0.72 + medium * 0.8) * 0.5 + 0.5;
    const weft = Math.sin(y * 0.72 - medium * 0.8) * 0.5 + 0.5;
    const weave = warp * weft + (1 - warp) * (1 - weft);
    return {
      shade: clamp01(0.82 + weave * 0.15 + (coarse - 0.5) * 0.05),
      height: clamp01(0.35 + weave * 0.35 + (fine - 0.5) * 0.05),
      roughness: clamp01(0.76 + (medium - 0.5) * 0.12),
    };
  }
  if (kind === 'epoxy') {
    const speckle = fine > 0.975 ? -0.08 : fine < 0.025 ? 0.06 : 0;
    return {
      shade: clamp01(0.96 + (medium - 0.5) * 0.035 + speckle),
      height: clamp01(0.5 + (fine - 0.5) * 0.055),
      roughness: clamp01(0.3 + (medium - 0.5) * 0.09),
    };
  }
  const orangePeel = (fine - 0.5) * 0.2 + (medium - 0.5) * 0.08;
  return {
    shade: clamp01(0.94 + (coarse - 0.5) * 0.05),
    height: clamp01(0.5 + orangePeel),
    roughness: clamp01(0.48 + (medium - 0.5) * 0.12),
  };
}

function textureFromCanvas(
  canvas: HTMLCanvasElement,
  options: {
    color: boolean;
    repeat: [number, number];
    anisotropy: number;
  },
): any {
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = options.color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(...options.repeat);
  texture.anisotropy = Math.min(options.anisotropy, 8);
  return texture;
}

export function applyProceduralSurface(
  material: any,
  kind: ProceduralSurfaceKind,
  options: {
    repeat: [number, number];
    anisotropy: number;
    bumpScale?: number;
    envMapIntensity?: number;
  },
): void {
  const size = 256;
  const colorCanvas = document.createElement('canvas');
  const heightCanvas = document.createElement('canvas');
  const roughnessCanvas = document.createElement('canvas');
  for (const canvas of [colorCanvas, heightCanvas, roughnessCanvas]) {
    canvas.width = size;
    canvas.height = size;
  }
  const colorContext = colorCanvas.getContext('2d');
  const heightContext = heightCanvas.getContext('2d');
  const roughnessContext = roughnessCanvas.getContext('2d');
  if (!colorContext || !heightContext || !roughnessContext) return;
  const colorPixels = colorContext.createImageData(size, size);
  const heightPixels = heightContext.createImageData(size, size);
  const roughnessPixels = roughnessContext.createImageData(size, size);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const sample = surfaceSample(kind, x, y);
      const offset = (y * size + x) * 4;
      const shade = Math.round(sample.shade * 255);
      const height = Math.round(sample.height * 255);
      const roughness = Math.round(sample.roughness * 255);
      colorPixels.data.set([shade, shade, shade, 255], offset);
      heightPixels.data.set([height, height, height, 255], offset);
      roughnessPixels.data.set([roughness, roughness, roughness, 255], offset);
    }
  }
  colorContext.putImageData(colorPixels, 0, 0);
  heightContext.putImageData(heightPixels, 0, 0);
  roughnessContext.putImageData(roughnessPixels, 0, 0);
  material.map = textureFromCanvas(colorCanvas, {
    color: true,
    repeat: options.repeat,
    anisotropy: options.anisotropy,
  });
  material.bumpMap = textureFromCanvas(heightCanvas, {
    color: false,
    repeat: options.repeat,
    anisotropy: options.anisotropy,
  });
  material.roughnessMap = textureFromCanvas(roughnessCanvas, {
    color: false,
    repeat: options.repeat,
    anisotropy: options.anisotropy,
  });
  material.bumpScale = options.bumpScale ?? 0.01;
  material.roughness = 1;
  material.envMapIntensity = options.envMapIntensity ?? 0.72;
  material.needsUpdate = true;
}

export function createProceduralEnvironmentTexture(): any | null {
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 512;
  const context = canvas.getContext('2d');
  if (!context) return null;
  const sky = context.createLinearGradient(0, 0, 0, canvas.height);
  sky.addColorStop(0, '#315f83');
  sky.addColorStop(0.44, '#9ebdce');
  sky.addColorStop(0.56, '#b8c8c8');
  sky.addColorStop(1, '#35444a');
  context.fillStyle = sky;
  context.fillRect(0, 0, canvas.width, canvas.height);
  const sunX = canvas.width * 0.36;
  const sunY = canvas.height * 0.24;
  const sun = context.createRadialGradient(sunX, sunY, 0, sunX, sunY, canvas.height * 0.22);
  sun.addColorStop(0, 'rgba(255, 249, 222, 1)');
  sun.addColorStop(0.08, 'rgba(255, 226, 172, .9)');
  sun.addColorStop(0.34, 'rgba(255, 207, 145, .18)');
  sun.addColorStop(1, 'rgba(255, 194, 126, 0)');
  context.fillStyle = sun;
  context.fillRect(0, 0, canvas.width, canvas.height);
  for (let index = 0; index < 16; index += 1) {
    const x = (index * 193) % canvas.width;
    const y = 140 + ((index * 47) % 90);
    const width = 90 + (index % 5) * 42;
    const cloud = context.createRadialGradient(x, y, 0, x, y, width);
    cloud.addColorStop(0, 'rgba(239, 247, 250, .08)');
    cloud.addColorStop(1, 'rgba(239, 247, 250, 0)');
    context.fillStyle = cloud;
    context.fillRect(x - width, y - width, width * 2, width * 2);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.mapping = THREE.EquirectangularReflectionMapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.generateMipmaps = true;
  return texture;
}
