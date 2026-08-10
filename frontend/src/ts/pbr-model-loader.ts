import * as THREE from '../vendor/three.module.js';

import type { ActorVisualModel } from './types.js';

const modelCache = new Map<string, Promise<any>>();
let loaderPromise: Promise<any> | null = null;

const materialTextureSlots = [
  'alphaMap',
  'aoMap',
  'bumpMap',
  'emissiveMap',
  'map',
  'metalnessMap',
  'normalMap',
  'roughnessMap',
] as const;

function templateForUrl(url: string): Promise<any> {
  const cached = modelCache.get(url);
  if (cached) return cached;
  loaderPromise ??= import('../vendor/GLTFLoader.js').then(
    ({ GLTFLoader }) => new GLTFLoader(),
  );
  const loading: Promise<any> = loaderPromise
    .then((activeLoader) => activeLoader.loadAsync(url))
    .then((gltf: any) => gltf.scene);
  modelCache.set(url, loading);
  void loading.catch(() => modelCache.delete(url));
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
  const cloned = template.clone(true);
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

function fittedInstance(
  template: any,
  instance: ActorVisualModel['instances'][number],
  resources: CloneResources,
  anisotropy: number,
): any {
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
  return root;
}

export async function createFittedPbrVisual(
  config: ActorVisualModel,
  anisotropy: number,
): Promise<any> {
  const url = new URL(config.url, document.baseURI).href;
  const template = await templateForUrl(url);
  const resources: CloneResources = {
    geometries: new Map(),
    materials: new Map(),
    textures: new Map(),
  };
  const visual = new THREE.Group();
  visual.name = `PBR visual: ${config.url}`;
  visual.userData.photorealVisual = true;
  for (const instance of config.instances) {
    visual.add(fittedInstance(template, instance, resources, anisotropy));
  }
  return visual;
}
