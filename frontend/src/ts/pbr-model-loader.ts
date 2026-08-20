import * as THREE from '../vendor/three.module.js';
import { clone as cloneSkeleton } from '../vendor/SkeletonUtils.js';

import {
  selectIdleClipName,
  selectLocomotionClipName,
} from './actor-animation.js';
import type {
  ActorVisualAnimation,
  ActorVisualModel,
} from './types.js';

interface LoadedGltf {
  scene: any;
  animations: any[];
}

export interface FittedPbrAnimationInstance {
  root: any;
  mixer: any;
  idleAction: any | null;
  locomotionAction: any;
}

export interface FittedPbrAnimation {
  config: ActorVisualAnimation;
  idleClipName: string | null;
  locomotionClipName: string;
  instances: FittedPbrAnimationInstance[];
}

export interface FittedPbrVisual {
  object: any;
  animation: FittedPbrAnimation | null;
}

const gltfCache = new Map<string, Promise<LoadedGltf>>();
let loaderPromise: Promise<any> | null = null;

const materialTextureSlots = [
  'alphaMap',
  'aoMap',
  'bumpMap',
  'clearcoatMap',
  'clearcoatNormalMap',
  'clearcoatRoughnessMap',
  'emissiveMap',
  'iridescenceMap',
  'iridescenceThicknessMap',
  'map',
  'metalnessMap',
  'normalMap',
  'roughnessMap',
  'sheenColorMap',
  'sheenRoughnessMap',
  'specularColorMap',
  'specularIntensityMap',
  'thicknessMap',
  'transmissionMap',
] as const;

function gltfForUrl(url: string): Promise<LoadedGltf> {
  const cached = gltfCache.get(url);
  if (cached) return cached;
  loaderPromise ??= import('../vendor/GLTFLoader.js').then(
    ({ GLTFLoader }) => new GLTFLoader(),
  );
  const loading = loaderPromise
    .then((activeLoader) => activeLoader.loadAsync(url))
    .then((gltf: any) => ({
      scene: gltf.scene,
      animations: Array.isArray(gltf.animations) ? gltf.animations : [],
    }));
  gltfCache.set(url, loading);
  void loading.catch(() => gltfCache.delete(url));
  return loading;
}

interface CloneResources {
  geometries: Map<any, any>;
  materials: Map<any, any>;
  textures: Map<any, any>;
}

function cloneTexture(texture: any, resources: CloneResources, anisotropy: number): any {
  let cloned = resources.textures.get(texture);
  if (!cloned) {
    cloned = texture.clone();
    cloned.anisotropy = Math.min(anisotropy, 8);
    cloned.needsUpdate = true;
    resources.textures.set(texture, cloned);
  }
  return cloned;
}

function cloneMaterial(material: any, resources: CloneResources, anisotropy: number): any {
  let cloned = resources.materials.get(material);
  if (cloned) return cloned;
  cloned = material.clone();
  for (const slot of materialTextureSlots) {
    if (material[slot]) cloned[slot] = cloneTexture(material[slot], resources, anisotropy);
  }
  if (typeof cloned.envMapIntensity === 'number') cloned.envMapIntensity = 1.05;
  cloned.dithering = true;
  cloned.needsUpdate = true;
  resources.materials.set(material, cloned);
  return cloned;
}

function cloneTemplate(
  template: any,
  resources: CloneResources,
  anisotropy: number,
): any {
  // Object3D.clone() leaves a SkinnedMesh pointing at the source skeleton. SkeletonUtils
  // remaps every cloned skin to its cloned bones before we isolate GPU resources below.
  const cloned = cloneSkeleton(template);
  cloned.traverse((child: any) => {
    if (child.geometry) {
      let geometry = resources.geometries.get(child.geometry);
      if (!geometry) {
        geometry = child.geometry.clone();
        resources.geometries.set(child.geometry, geometry);
      }
      child.geometry = geometry;
    }
    if (Array.isArray(child.material)) {
      child.material = child.material.map(
        (material: any) => cloneMaterial(material, resources, anisotropy),
      );
    } else if (child.material) {
      child.material = cloneMaterial(child.material, resources, anisotropy);
    }
    if (child.isMesh) {
      child.castShadow = true;
      child.receiveShadow = true;
      child.userData.actorDetail = true;
      child.userData.photorealVisual = true;
    }
  });
  return cloned;
}

interface FittedInstance {
  root: any;
  model: any;
}

function fittedInstance(
  template: any,
  instance: ActorVisualModel['instances'][number],
  resources: CloneResources,
  anisotropy: number,
): FittedInstance {
  const root = new THREE.Group();
  const model = cloneTemplate(template, resources, anisotropy);
  model.rotation.set(...instance.rotation);
  model.updateMatrixWorld(true);

  const bounds = new THREE.Box3().setFromObject(model);
  const nativeSize = bounds.getSize(new THREE.Vector3());
  model.scale.multiply(new THREE.Vector3(
    instance.size[0] / Math.max(nativeSize.x, 1e-6),
    instance.size[1] / Math.max(nativeSize.y, 1e-6),
    instance.size[2] / Math.max(nativeSize.z, 1e-6),
  ));
  model.updateMatrixWorld(true);
  const fittedCenter = new THREE.Box3().setFromObject(model)
    .getCenter(new THREE.Vector3());
  model.position.sub(fittedCenter);
  root.position.set(...instance.position);
  root.add(model);
  root.userData.photorealInstance = true;
  return { root, model };
}

function animationForInstances(
  config: ActorVisualAnimation | undefined,
  clips: any[],
  instances: FittedInstance[],
): FittedPbrAnimation | null {
  if (!config) return null;
  const availableNames = clips.map((clip) => String(clip.name ?? ''));
  const locomotionClipName = selectLocomotionClipName(availableNames, config);
  if (!locomotionClipName) {
    throw new Error(`No ${config.locomotion} animation clip found in glTF`);
  }
  const idleClipName = selectIdleClipName(availableNames, config);
  const locomotionClip = clips.find((clip) => clip.name === locomotionClipName);
  const idleClip = idleClipName
    ? clips.find((clip) => clip.name === idleClipName) ?? null
    : null;

  return {
    config,
    idleClipName,
    locomotionClipName,
    instances: instances.map(({ model }) => {
      const mixer = new THREE.AnimationMixer(model);
      const locomotionAction = mixer.clipAction(locomotionClip);
      const idleAction = idleClip ? mixer.clipAction(idleClip) : null;
      locomotionAction.play();
      locomotionAction.setEffectiveTimeScale(0);
      locomotionAction.setEffectiveWeight(idleAction ? 0 : 1);
      if (idleAction) {
        idleAction.play();
        idleAction.setEffectiveTimeScale(1);
        idleAction.setEffectiveWeight(1);
      }
      mixer.update(0);
      return {
        root: model,
        mixer,
        idleAction,
        locomotionAction,
      };
    }),
  };
}

export async function createFittedPbrVisual(
  config: ActorVisualModel,
  anisotropy: number,
): Promise<FittedPbrVisual> {
  const url = new URL(config.url, document.baseURI).href;
  const animationUrl = config.animation?.clip_url
    ? new URL(config.animation.clip_url, document.baseURI).href
    : url;
  const [template, animationSource] = await Promise.all([
    gltfForUrl(url),
    animationUrl === url ? gltfForUrl(url) : gltfForUrl(animationUrl),
  ]);
  const resources: CloneResources = {
    geometries: new Map(),
    materials: new Map(),
    textures: new Map(),
  };
  const visual = new THREE.Group();
  visual.name = `PBR visual: ${config.url}`;
  visual.userData.photorealVisual = true;
  const fitted: FittedInstance[] = [];
  for (const instance of config.instances) {
    const item = fittedInstance(template.scene, instance, resources, anisotropy);
    fitted.push(item);
    visual.add(item.root);
  }
  return {
    object: visual,
    animation: animationForInstances(
      config.animation,
      animationSource.animations,
      fitted,
    ),
  };
}
