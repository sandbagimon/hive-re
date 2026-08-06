import * as THREE from '../vendor/three.module.js';
import { OrbitControls } from '../vendor/OrbitControls.js';
import { TransformControls } from '../vendor/TransformControls.js';

import { sourceGeometry } from './geometry-contract.js';
import { decodeGeometryBundle, type BundledGeometry } from './geometry-bundle.js';
import {
  advanceRotorAnimation,
  jointLocalPose,
  type RotorAnimationState,
} from './robot-kinematics.js';
import type {
  Actor,
  RobotArticulation,
  RobotVisualGeometry,
  Scene,
  SimulationState,
  Transform,
  VisualGeometryPayload,
} from './types.js';

type TransformMode = 'translate' | 'rotate' | 'scale';
type CameraView = 'iso' | 'front' | 'right' | 'top';

const requiredElement = <T extends Element>(selector: string): T => {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing viewport element: ${selector}`);
  return element;
};

const canvas = requiredElement<HTMLCanvasElement>('#viewport');
const toolbar = requiredElement<HTMLElement>('#viewport-toolbar');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setClearColor(0x171a1f, 1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x171a1f, 18, 60);

const camera = new THREE.PerspectiveCamera(50, 1, 0.05, 1000);
camera.position.set(5, -7, 5);
camera.up.set(0, 0, 1);

const orbitControls = new OrbitControls(camera, renderer.domElement);
orbitControls.target.set(0, 0, 0.5);
orbitControls.enableDamping = true;
orbitControls.dampingFactor = 0.08;

const transformControls = new TransformControls(camera, renderer.domElement);
let transformMode: TransformMode = 'translate';
transformControls.setMode(transformMode);
transformControls.setSpace('world');
scene.add(transformControls);

let actorSelectedCallback: (actorId: string | null) => void = () => undefined;
let actorTransformCallback: (actorId: string, transform: Transform) => void = () => undefined;
let visualGeometryResolver: (cachePath: string) => Promise<VisualGeometryPayload | null> =
  async () => null;
let visualGeometryBundleResolver: (artifactId: string) => Promise<ArrayBuffer | null> =
  async () => null;
const geometryBundleCache = new Map<
  string,
  Promise<Map<string, BundledGeometry> | null>
>();

transformControls.addEventListener('dragging-changed', (event) => {
  orbitControls.enabled = !event.value;
});

transformControls.addEventListener('mouseUp', () => {
  const object = transformControls.object;
  if (!object?.userData.actorId) return;
  const actorId = String(object.userData.actorId);
  const transform: Transform = {
    position: [object.position.x, object.position.y, object.position.z],
    rotation: [object.rotation.x, object.rotation.y, object.rotation.z],
    scale: [object.scale.x, object.scale.y, object.scale.z],
  };
  // TransformControls dispatches mouseUp before it clears its dragging/axis state. Updating the
  // store synchronously rebuilds the scene and detaches the control in the middle of that event.
  // Commit immediately after TransformControls has finished its pointer-up lifecycle instead.
  queueMicrotask(() => {
    actorTransformCallback(actorId, transform);
    // Moving an actor is also an explicit selection action. Re-select it after the scene update
    // so the rebuilt mesh, outline, transform gizmo, and editor store all point to the same actor.
    selectViewportActor(actorId, true);
  });
});

const grid = new THREE.GridHelper(20, 20, 0x4a5568, 0x2d3748);
grid.rotation.x = Math.PI / 2;
scene.add(grid);
const axes = new THREE.AxesHelper(2);
scene.add(axes);

const ambient = new THREE.HemisphereLight(0xffffff, 0x20242b, 1.6);
scene.add(ambient);

const keyLight = new THREE.DirectionalLight(0xfff1d6, 1.3);
keyLight.position.set(4, -5, 8);
scene.add(keyLight);

const fillLight = new THREE.DirectionalLight(0x8ab8e6, 0.28);
fillLight.position.set(-5, 3, 4);
scene.add(fillLight);

const citySky = new THREE.Mesh(
  new THREE.SphereGeometry(1, 32, 16),
  new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      horizonColor: { value: new THREE.Color(0xd9e7ee) },
      zenithColor: { value: new THREE.Color(0x4f8fc4) },
      sunColor: { value: new THREE.Color(0xffdca3) },
    },
    vertexShader: `
      varying vec3 vSkyDirection;
      void main() {
        vSkyDirection = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying vec3 vSkyDirection;
      uniform vec3 horizonColor;
      uniform vec3 zenithColor;
      uniform vec3 sunColor;
      void main() {
        float skyMix = pow(vSkyDirection.z * 0.5 + 0.5, 0.58);
        vec3 color = mix(horizonColor, zenithColor, skyMix);
        vec3 sunDirection = normalize(vec3(-0.45, 0.30, 0.72));
        float sun = smoothstep(0.996, 0.9992, dot(vSkyDirection, sunDirection));
        color += sunColor * sun * 1.25;
        gl_FragColor = vec4(color, 1.0);
      }
    `,
  }),
);
citySky.visible = false;
citySky.frustumCulled = false;
citySky.renderOrder = -100;
scene.add(citySky);

const actorGroup = new THREE.Group();
scene.add(actorGroup);
const attachmentGroup = new THREE.Group();
scene.add(attachmentGroup);

const selectionOutline = new THREE.BoxHelper(new THREE.Object3D(), 0xffd166);
selectionOutline.visible = false;
selectionOutline.material.depthTest = false;
selectionOutline.renderOrder = 10;
scene.add(selectionOutline);

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const actorMeshes = new Map<string, any>();
const robotLinkGroups = new Map<string, any>();
const rotorAnimationStates = new Map<string, RotorAnimationState>();
const actorRenderSignatures = new Map<string, string>();
const actorLoadRevisions = new Map<string, number>();
const attachmentVisuals = new Map<string, {
  line: any;
  parentMarker: any;
  childMarker: any;
  indicator: any;
}>();
let attachmentRenderSignature = '';
let selectedActorId: string | null = null;
let selectedLinkId: string | null = null;
let currentScene: Scene = {
  version: '1.0',
  name: 'Untitled Scene',
  units: 'meters',
  actors: [],
  simulation_config: { timestep: 0.01, duration: 1 },
};
let simulationState: SimulationState | null = null;
let colliderDebugVisible = false;
let cityEnvironmentVisible = false;
const focusBox = new THREE.Box3();
const focusSphere = new THREE.Sphere();
const viewDirections: Record<CameraView, any> = {
  iso: new THREE.Vector3(1, -1, 0.75).normalize(),
  front: new THREE.Vector3(0, -1, 0),
  right: new THREE.Vector3(1, 0, 0),
  top: new THREE.Vector3(0, 0, 1),
};
const largeEnvironmentViewDirection = new THREE.Vector3(1, -1, 1.05).normalize();
const materialVisuals: Record<string, { roughness: number; metalness: number }> = {
  default: { roughness: 0.55, metalness: 0.04 },
  rubber: { roughness: 0.86, metalness: 0 },
  wood: { roughness: 0.72, metalness: 0 },
  metal: { roughness: 0.24, metalness: 0.82 },
  ice: { roughness: 0.12, metalness: 0.08 },
};

function isLargeEnvironment(actor: Actor): boolean {
  const bounds = actor.properties.geometry?.bounds;
  if (!bounds) return false;
  return Math.max(...bounds.max.map((value, index) => value - bounds.min[index])) >= 250;
}

function updateEnvironmentAppearance(sceneData: Scene): void {
  const wasCityEnvironmentVisible = cityEnvironmentVisible;
  cityEnvironmentVisible = sceneData.actors.some(isLargeEnvironment);
  canvas.dataset.environmentMode = cityEnvironmentVisible ? 'city' : 'editor';
  grid.visible = !cityEnvironmentVisible;
  axes.visible = !cityEnvironmentVisible;
  citySky.visible = cityEnvironmentVisible;
  renderer.setClearColor(cityEnvironmentVisible ? 0xb9d3e3 : 0x171a1f, 1);
  renderer.toneMappingExposure = cityEnvironmentVisible ? 1.08 : 1.0;
  if (scene.fog instanceof THREE.Fog) {
    scene.fog.color.set(cityEnvironmentVisible ? 0xc4d8e2 : 0x171a1f);
  }
  ambient.color.set(cityEnvironmentVisible ? 0xcce5ff : 0xffffff);
  ambient.groundColor.set(cityEnvironmentVisible ? 0x53665d : 0x20242b);
  ambient.intensity = cityEnvironmentVisible ? 1.25 : 1.6;
  keyLight.intensity = cityEnvironmentVisible ? 2.1 : 1.3;
  fillLight.intensity = cityEnvironmentVisible ? 0.5 : 0.28;
  const environmentModeChanged = cityEnvironmentVisible !== wasCityEnvironmentVisible;
  if (scene.fog instanceof THREE.Fog && environmentModeChanged) {
    // A large environment gets camera-dependent fog distances in frameObject(). Preserve those
    // distances while reconciling unrelated actors; resetting them to the editor defaults would
    // fog out a kilometre-scale scene and make it flash white after every scene edit.
    scene.fog.near = 18;
    scene.fog.far = 60;
  }
  if (scene.fog instanceof THREE.Fog) {
    canvas.dataset.fogNear = scene.fog.near.toFixed(3);
    canvas.dataset.fogFar = scene.fog.far.toFixed(3);
  }
}

export function configureViewport(callbacks: {
  onActorSelected: (actorId: string | null) => void;
  onActorTransformChanged: (actorId: string, transform: Transform) => void;
  resolveVisualGeometry: (cachePath: string) => Promise<VisualGeometryPayload | null>;
  resolveVisualGeometryBundle: (artifactId: string) => Promise<ArrayBuffer | null>;
}): void {
  actorSelectedCallback = callbacks.onActorSelected;
  actorTransformCallback = callbacks.onActorTransformChanged;
  visualGeometryResolver = callbacks.resolveVisualGeometry;
  visualGeometryBundleResolver = callbacks.resolveVisualGeometryBundle;
}

function resize(): void {
  const width = canvas.clientWidth || window.innerWidth;
  const height = canvas.clientHeight || window.innerHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / Math.max(height, 1);
  camera.updateProjectionMatrix();
}

function materialForActor(actor: Actor): any {
  const rgba = actor.properties.rgba ?? [0.55, 0.62, 0.7, 1];
  const primitive = actor.properties.geometry?.kind === 'mesh'
    ? 'mesh'
    : sourceGeometry(actor).geomType;
  const physics = actor.properties.physics ?? { dynamic: true };
  const materialVisual = materialVisuals[physics.material ?? 'default'] ?? materialVisuals.default;
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(rgba[0], rgba[1], rgba[2]),
    roughness: physics.roughness ?? materialVisual.roughness,
    metalness: physics.metalness ?? materialVisual.metalness,
    transparent: rgba[3] < 1,
    opacity: rgba[3],
    side: primitive === 'plane' ? THREE.DoubleSide : THREE.FrontSide,
  });
}

function geometryForActor(actor: Actor): any {
  if (actor.properties.geometry?.kind === 'mesh') {
    const bounds = actor.properties.geometry.bounds;
    if (!bounds) return new THREE.BoxGeometry(1, 1, 1);
    const size = bounds.max.map((value, index) => Math.max(value - bounds.min[index], 0.01));
    const center = bounds.max.map((value, index) => (value + bounds.min[index]) / 2);
    return new THREE.BoxGeometry(size[0], size[1], size[2]).translate(
      center[0], center[1], center[2],
    );
  }
  const { geomType, size } = sourceGeometry(actor);
  if (geomType === 'plane') return new THREE.PlaneGeometry((size[0] ?? 5) * 2, (size[1] ?? 5) * 2);
  if (geomType === 'sphere') return new THREE.SphereGeometry(size[0] ?? 0.5, 40, 24);
  if (geomType === 'ellipsoid') {
    return new THREE.SphereGeometry(1, 40, 24).scale(
      size[0] ?? 0.5,
      size[1] ?? 0.5,
      size[2] ?? 0.5,
    );
  }
  if (geomType === 'cylinder') {
    const geometry = new THREE.CylinderGeometry(size[0] ?? 0.35, size[0] ?? 0.35, (size[1] ?? 0.8) * 2, 40);
    geometry.rotateX(Math.PI / 2);
    return geometry;
  }
  return new THREE.BoxGeometry((size[0] ?? 0.5) * 2, (size[1] ?? 0.5) * 2, (size[2] ?? 0.5) * 2);
}

function addShippingPackageDetails(mesh: any, actor: Actor): void {
  if (actor.properties.visual_style !== 'shipping_package') return;
  const size = actor.properties.size ?? [0.18, 0.14, 0.11];
  const [halfX, halfY, halfZ] = [
    size[0] ?? 0.18,
    size[1] ?? 0.14,
    size[2] ?? 0.11,
  ];
  mesh.material.color.set(0xb5793f);
  mesh.material.roughness = 0.82;
  mesh.material.metalness = 0;

  const addBox = (
    dimensions: [number, number, number],
    position: [number, number, number],
    color: number,
    roughness = 0.65,
  ): any => {
    const detail = new THREE.Mesh(
      new THREE.BoxGeometry(...dimensions),
      new THREE.MeshStandardMaterial({ color, roughness, metalness: 0 }),
    );
    detail.position.set(...position);
    detail.userData.packageDetail = true;
    mesh.add(detail);
    return detail;
  };

  const tapeWidth = Math.min(halfX * 0.34, 0.065);
  const surfaceOffset = 0.0015;
  addBox(
    [tapeWidth, halfY * 2 + 0.004, 0.003],
    [0, 0, halfZ + surfaceOffset],
    0xd7b36a,
    0.48,
  );
  for (const side of [-1, 1]) {
    addBox(
      [tapeWidth, 0.003, halfZ * 2],
      [0, side * (halfY + surfaceOffset), 0],
      0xd7b36a,
      0.48,
    );
  }

  const strapColor = 0x263746;
  for (const offsetY of [-halfY * 0.52, halfY * 0.52]) {
    addBox(
      [halfX * 2 + 0.004, 0.012, 0.004],
      [0, offsetY, halfZ + 0.002],
      strapColor,
      0.58,
    );
    for (const side of [-1, 1]) {
      addBox(
        [0.003, 0.012, halfZ * 2],
        [side * (halfX + surfaceOffset), offsetY, 0],
        strapColor,
        0.58,
      );
    }
  }

  addBox(
    [halfX * 0.66, halfY * 0.62, 0.0025],
    [halfX * 0.32, 0, halfZ + 0.004],
    0xf0ede4,
    0.9,
  );
  for (let index = 0; index < 7; index += 1) {
    const width = index % 3 === 0 ? 0.004 : 0.002;
    addBox(
      [width, halfY * 0.36, 0.001],
      [halfX * 0.12 + index * halfX * 0.045, 0, halfZ + 0.0055],
      0x222222,
      0.8,
    );
  }

  const seamColor = 0x6f4528;
  addBox(
    [0.002, halfY * 2, 0.002],
    [-halfX * 0.48, 0, halfZ + 0.003],
    seamColor,
    0.9,
  );
  for (const x of [-halfX, halfX]) {
    for (const y of [-halfY, halfY]) {
      addBox(
        [0.018, 0.018, 0.018],
        [x * 0.96, y * 0.95, halfZ * 0.92],
        0x8e5a32,
        0.88,
      );
    }
  }
}

function geometryFromPayload(payload: VisualGeometryPayload): any {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(payload.positions, 3));
  if (payload.colors?.length === (payload.positions.length / 3) * 4) {
    const rgb: number[] = [];
    for (let index = 0; index < payload.colors.length; index += 4) {
      rgb.push(payload.colors[index], payload.colors[index + 1], payload.colors[index + 2]);
    }
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(rgb, 3));
  }
  if (payload.uvs?.length === (payload.positions.length / 3) * 2) {
    geometry.setAttribute('uv', new THREE.Float32BufferAttribute(payload.uvs, 2));
  }
  geometry.setIndex(payload.indices);
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

type MaterialTextureSlot = 'map' | 'normalMap' | 'roughnessMap' | 'metalnessMap';

function visualTextureUrls(payload: VisualGeometryPayload): string[] {
  return [
    payload.base_color_texture_url,
    payload.normal_texture_url,
    payload.roughness_texture_url,
    payload.metallic_texture_url,
  ].filter((value): value is string => Boolean(value));
}

function loadMaterialTexture(
  actorId: string,
  mesh: any,
  loadRevision: number,
  url: string | null | undefined,
  slot: MaterialTextureSlot,
  colorTexture: boolean,
  scalar?: number | null,
): void {
  if (!url) return;
  new THREE.TextureLoader().load(
    url,
    (texture) => {
      URL.revokeObjectURL(url);
      if (!actorLoadIsCurrent(actorId, mesh, loadRevision)) {
        texture.dispose();
        return;
      }
      texture.colorSpace = colorTexture ? THREE.SRGBColorSpace : THREE.NoColorSpace;
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.RepeatWrapping;
      mesh.material[slot]?.dispose();
      mesh.material[slot] = texture;
      if (slot === 'roughnessMap') mesh.material.roughness = scalar ?? 1;
      if (slot === 'metalnessMap') mesh.material.metalness = scalar ?? 1;
      mesh.material.needsUpdate = true;
    },
    undefined,
    () => URL.revokeObjectURL(url),
  );
}

function geometryFromBundle(payload: BundledGeometry): any {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(payload.positions, 3));
  geometry.setAttribute('normal', new THREE.BufferAttribute(payload.normals, 3));
  if (payload.colors) {
    geometry.setAttribute('color', new THREE.Uint8BufferAttribute(payload.colors, 3, true));
  }
  if (payload.uvs) geometry.setAttribute('uv', new THREE.BufferAttribute(payload.uvs, 2));
  geometry.setIndex(new THREE.BufferAttribute(payload.indices, 1));
  geometry.boundingBox = new THREE.Box3(
    new THREE.Vector3(...payload.bounds.min),
    new THREE.Vector3(...payload.bounds.max),
  );
  geometry.boundingSphere = new THREE.Sphere(
    new THREE.Vector3(...payload.bounds.sphere.slice(0, 3)),
    payload.bounds.sphere[3],
  );
  return geometry;
}

function resolveGeometryBundle(
  artifactId: string,
): Promise<Map<string, BundledGeometry> | null> {
  let promise = geometryBundleCache.get(artifactId);
  if (!promise) {
    promise = visualGeometryBundleResolver(artifactId).then((buffer) => (
      buffer ? decodeGeometryBundle(buffer) : null
    ));
    geometryBundleCache.set(artifactId, promise);
    void promise.catch(() => geometryBundleCache.delete(artifactId));
  }
  return promise;
}

function geometryForRobotVisual(visual: RobotVisualGeometry, hasBundle: boolean): any {
  const size = visual.size;
  if (visual.geometry_type === 'mesh' && (hasBundle || visual.visual_cache)) {
    return new THREE.BufferGeometry();
  }
  if (visual.geometry_type === 'sphere') {
    return new THREE.SphereGeometry(size[0] ?? 0.5, 32, 20);
  }
  if (visual.geometry_type === 'ellipsoid') {
    return new THREE.SphereGeometry(1, 32, 20).scale(
      size[0] ?? 0.5, size[1] ?? 0.5, size[2] ?? 0.5,
    );
  }
  if (visual.geometry_type === 'cylinder' || visual.geometry_type === 'capsule') {
    const geometry = new THREE.CylinderGeometry(
      size[0] ?? 0.25, size[0] ?? 0.25, (size[1] ?? 0.5) * 2, 32,
    );
    geometry.rotateX(Math.PI / 2);
    return geometry;
  }
  return new THREE.BoxGeometry(
    (size[0] ?? 0.5) * 2, (size[1] ?? 0.5) * 2, (size[2] ?? 0.5) * 2,
  );
}

function addRobotActor(
  actor: Actor,
  articulation: RobotArticulation,
  visualBundle: string | null,
  loadRevision: number,
): any {
  const root = new THREE.Group();
  root.position.set(...actor.transform.position);
  root.rotation.set(...actor.transform.rotation);
  root.scale.set(...actor.transform.scale);
  root.name = actor.name;
  root.userData.actorId = actor.id;
  root.userData.actor = actor;
  const groups = new Map<string, any>();
  const bundledMeshes = new Map<string, any>();
  for (const link of articulation.links) {
    const group = new THREE.Group();
    group.name = link.name;
    group.position.set(...link.transform.position);
    group.quaternion.set(...link.transform.quaternion);
    group.userData.actorId = actor.id;
    group.userData.linkId = link.id;
    groups.set(link.id, group);
    robotLinkGroups.set(link.id, group);
  }
  for (const link of articulation.links) {
    const group = groups.get(link.id);
    const parent = link.parent_link_id ? groups.get(link.parent_link_id) : root;
    parent?.add(group);
    for (const visual of link.visual_geometries) {
      const rgba = visual.rgba ?? [0.7, 0.7, 0.7, 1];
      const mesh = new THREE.Mesh(
        geometryForRobotVisual(visual, Boolean(visualBundle)),
        new THREE.MeshStandardMaterial({
          color: new THREE.Color(rgba[0], rgba[1], rgba[2]),
          roughness: visual.roughness ?? 0.55,
          metalness: visual.metalness ?? 0.05,
          transparent: rgba[3] < 1,
          opacity: rgba[3],
        }),
      );
      mesh.position.set(...visual.transform.position);
      mesh.quaternion.set(...visual.transform.quaternion);
      mesh.userData.actorId = actor.id;
      mesh.userData.linkId = link.id;
      group.add(mesh);
      if (visual.geometry_type === 'mesh' && visualBundle) {
        bundledMeshes.set(visual.id, mesh);
      }
      if (
        visual.geometry_type === 'mesh'
        && visual.visual_cache
        && !visualBundle
        && visualGeometryResolver
      ) {
        const cachePath = visual.visual_cache;
        void visualGeometryResolver(cachePath).then((payload) => {
          if (
            !payload
            || !actorLoadIsCurrent(actor.id, root, loadRevision)
            || !mesh.parent
          ) return;
          mesh.geometry.dispose();
          mesh.geometry = geometryFromPayload(payload);
          if (payload.colors?.length === (payload.positions.length / 3) * 4) {
            mesh.material.vertexColors = true;
            mesh.material.color.set(0xffffff);
            mesh.material.needsUpdate = true;
          }
          updateSelectionOutline();
        }).catch(() => undefined);
      }
    }
  }
  if (visualBundle && bundledMeshes.size > 0) {
    void resolveGeometryBundle(visualBundle).then((bundle) => {
      if (!bundle || !actorLoadIsCurrent(actor.id, root, loadRevision)) return;
      for (const [geometryId, mesh] of bundledMeshes) {
        const payload = bundle.get(geometryId);
        if (!payload) continue;
        mesh.geometry.dispose();
        mesh.geometry = geometryFromBundle(payload);
        if (payload.colors) {
          mesh.material.vertexColors = true;
          mesh.material.color.set(0xffffff);
          mesh.material.needsUpdate = true;
        }
      }
      updateSelectionOutline();
    }).catch(() => undefined);
  }
  for (const joint of articulation.joints) {
    const child = groups.get(joint.child_link_id);
    if (!child) continue;
    const canonicalPose = jointLocalPose(joint);
    if (canonicalPose) {
      child.position.set(...canonicalPose.position);
      child.quaternion.set(...canonicalPose.quaternion);
      continue;
    }
    if (joint.type === 'fixed' || joint.initial_position === 0) continue;
    const axis = new THREE.Vector3(...joint.axis).normalize();
    if (joint.type === 'prismatic') {
      axis.applyQuaternion(child.quaternion).multiplyScalar(joint.initial_position);
      child.position.add(axis);
    } else {
      child.quaternion.multiply(
        new THREE.Quaternion().setFromAxisAngle(axis, joint.initial_position),
      );
    }
  }
  return root;
}

function actorIsDynamic(actor: Actor): boolean {
  return actor.properties.physics?.dynamic ?? true;
}

function addColliderDebug(mesh: any, actor: Actor): void {
  const wireframe = new THREE.LineSegments(
    new THREE.WireframeGeometry(mesh.geometry),
    new THREE.LineBasicMaterial({
      color: actorIsDynamic(actor) ? 0xff9f43 : 0x55d6be,
      depthTest: false,
      transparent: true,
      opacity: 0.9,
    }),
  );
  wireframe.visible = colliderDebugVisible;
  wireframe.renderOrder = 12;
  wireframe.userData.colliderDebug = true;
  mesh.add(wireframe);

  const center = new THREE.Mesh(
    new THREE.SphereGeometry(0.055, 16, 10),
    new THREE.MeshBasicMaterial({ color: 0xffd166, depthTest: false }),
  );
  center.visible = colliderDebugVisible;
  center.renderOrder = 13;
  center.userData.colliderDebug = true;
  center.userData.centerOfMass = true;
  mesh.add(center);
}

function rebuildColliderDebug(mesh: any, actor: Actor): void {
  for (const child of [...mesh.children]) {
    if (!child.userData.colliderDebug) continue;
    mesh.remove(child);
    disposeObject(child);
  }
  addColliderDebug(mesh, actor);
}

function disposeObject(object: any): void {
  object.traverse((child) => {
    child.geometry?.dispose();
    child.material?.map?.dispose();
    child.material?.dispose();
  });
}

function nextActorLoadRevision(actorId: string): number {
  const revision = (actorLoadRevisions.get(actorId) ?? 0) + 1;
  actorLoadRevisions.set(actorId, revision);
  return revision;
}

function actorLoadIsCurrent(actorId: string, object: any, revision: number): boolean {
  return actorLoadRevisions.get(actorId) === revision && actorMeshes.get(actorId) === object;
}

function articulationForActor(actor: Actor, sceneData: Scene): RobotArticulation | null {
  const articulationIds = actor.properties.articulation_ids as string[] | undefined;
  return sceneData.robotics?.articulations.find(
    (item) => articulationIds?.includes(item.id),
  ) ?? null;
}

function actorRenderSignature(actor: Actor, sceneData: Scene): string {
  return JSON.stringify({
    type: actor.type,
    assetId: actor.asset_id,
    properties: actor.properties,
    articulation: actor.type === 'robot' ? articulationForActor(actor, sceneData) : null,
  });
}

function updateActorObject(object: any, actor: Actor): void {
  object.position.set(...actor.transform.position);
  object.rotation.set(...actor.transform.rotation);
  object.scale.set(...actor.transform.scale);
  object.name = actor.name;
  object.userData.actor = actor;
}

function removeActorObject(actorId: string): void {
  const object = actorMeshes.get(actorId);
  if (!object) return;
  if (transformControls.object === object) transformControls.detach();
  object.traverse((child) => {
    const linkId = child.userData?.linkId;
    if (!linkId) return;
    robotLinkGroups.delete(String(linkId));
    rotorAnimationStates.delete(String(linkId));
  });
  actorGroup.remove(object);
  actorMeshes.delete(actorId);
  actorRenderSignatures.delete(actorId);
  nextActorLoadRevision(actorId);
  disposeObject(object);
}

function createActorObject(actor: Actor, sceneData: Scene): any | null {
  const loadRevision = nextActorLoadRevision(actor.id);
  if (actor.type === 'robot') {
    const articulation = articulationForActor(actor, sceneData);
    if (!articulation) return null;
    const robot = addRobotActor(
      actor,
      articulation,
      articulation.visual_bundle ?? null,
      loadRevision,
    );
    actorGroup.add(robot);
    actorMeshes.set(actor.id, robot);
    return robot;
  }
  if (actor.type !== 'object') return null;
  const mesh = new THREE.Mesh(geometryForActor(actor), materialForActor(actor));
  updateActorObject(mesh, actor);
  mesh.userData.actorId = actor.id;
  addColliderDebug(mesh, actor);
  addShippingPackageDetails(mesh, actor);
  actorGroup.add(mesh);
  actorMeshes.set(actor.id, mesh);
  const cachePath = actor.properties.geometry?.visual_cache;
  if (cachePath) {
    void visualGeometryResolver(cachePath).then((payload) => {
      if (!payload) return;
      if (!actorLoadIsCurrent(actor.id, mesh, loadRevision)) {
        for (const url of visualTextureUrls(payload)) URL.revokeObjectURL(url);
        return;
      }
      mesh.geometry.dispose();
      mesh.geometry = geometryFromPayload(payload);
      const hasVertexColors = Boolean(payload.colors?.length);
      mesh.material.vertexColors = hasVertexColors;
      // Vertex colors already contain the authored USD display color. Multiplying them by the
      // actor fallback color makes large cached environments nearly black.
      if (hasVertexColors) mesh.material.color.set(0xffffff);
      if (typeof payload.roughness === 'number') mesh.material.roughness = payload.roughness;
      if (typeof payload.metalness === 'number') mesh.material.metalness = payload.metalness;
      mesh.material.needsUpdate = true;
      loadMaterialTexture(
        actor.id, mesh, loadRevision, payload.base_color_texture_url, 'map', true,
      );
      loadMaterialTexture(
        actor.id, mesh, loadRevision, payload.normal_texture_url, 'normalMap', false,
      );
      loadMaterialTexture(
        actor.id,
        mesh,
        loadRevision,
        payload.roughness_texture_url,
        'roughnessMap',
        false,
        payload.roughness,
      );
      loadMaterialTexture(
        actor.id,
        mesh,
        loadRevision,
        payload.metallic_texture_url,
        'metalnessMap',
        false,
        payload.metalness,
      );
      rebuildColliderDebug(mesh, actor);
      updateSelectionOutline();
    }).catch(() => undefined);
  }
  return mesh;
}

function syncAttachmentVisuals(sceneData: Scene): void {
  const attachments = sceneData.attachments ?? [];
  const signature = JSON.stringify(attachments);
  if (signature === attachmentRenderSignature) return;
  for (const visual of attachmentVisuals.values()) {
    attachmentGroup.remove(visual.line, visual.parentMarker, visual.childMarker);
    disposeObject(visual.line);
    disposeObject(visual.parentMarker);
    disposeObject(visual.childMarker);
  }
  attachmentVisuals.clear();
  attachmentRenderSignature = signature;
  for (const attachment of attachments) {
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(),
        new THREE.Vector3(),
      ]),
      new THREE.LineBasicMaterial({ color: 0xd7a72f }),
    );
    line.frustumCulled = false;
    line.renderOrder = 8;
    let parentMarker: any;
    let indicator: any;
    if (attachment.gripper) {
      const gripper = attachment.gripper;
      parentMarker = new THREE.Group();
      const metal = new THREE.MeshStandardMaterial({
        color: 0x34434f,
        roughness: 0.32,
        metalness: 0.72,
      });
      const rubber = new THREE.MeshStandardMaterial({
        color: 0x171b1f,
        roughness: 0.94,
        metalness: 0,
      });
      const [plateX, plateY, plateZ] = gripper.plate_half_extents;
      const plate = new THREE.Mesh(
        new THREE.BoxGeometry(plateX * 2, plateY * 2, plateZ * 2),
        metal,
      );
      plate.position.z = gripper.cup_height + plateZ;
      parentMarker.add(plate);
      const mount = new THREE.Mesh(
        new THREE.CylinderGeometry(
          gripper.mount_radius,
          gripper.mount_radius,
          gripper.mount_length,
          20,
        ).rotateX(Math.PI / 2),
        metal.clone(),
      );
      mount.position.z = gripper.cup_height + plateZ * 2 + gripper.mount_length * 0.5;
      parentMarker.add(mount);
      const [cupX, cupY] = gripper.cup_offset;
      for (const [offsetX, offsetY] of [
        [cupX, cupY], [cupX, -cupY], [-cupX, cupY], [-cupX, -cupY],
      ]) {
        const cup = new THREE.Mesh(
          new THREE.CylinderGeometry(
            gripper.cup_radius * 0.72,
            gripper.cup_radius,
            gripper.cup_height,
            24,
          ).rotateX(Math.PI / 2),
          rubber.clone(),
        );
        cup.position.set(offsetX, offsetY, gripper.cup_height * 0.5);
        parentMarker.add(cup);
        const lip = new THREE.Mesh(
          new THREE.TorusGeometry(gripper.cup_radius * 0.82, 0.0025, 8, 24),
          rubber.clone(),
        );
        lip.position.set(offsetX, offsetY, 0.001);
        parentMarker.add(lip);
      }
      indicator = new THREE.Mesh(
        new THREE.SphereGeometry(0.008, 14, 10),
        new THREE.MeshStandardMaterial({
          color: 0xf4b942,
          emissive: 0x5a3500,
          emissiveIntensity: 1.5,
          roughness: 0.25,
        }),
      );
      indicator.position.set(plateX * 0.72, 0, gripper.cup_height + plateZ * 2 + 0.003);
      parentMarker.add(indicator);
    } else {
      parentMarker = new THREE.Mesh(
        new THREE.SphereGeometry(Math.max(attachment.contact_probe_radius, 0.015), 12, 8),
        new THREE.MeshBasicMaterial({ color: 0xf4b942 }),
      );
      indicator = parentMarker;
    }
    const childMarker = new THREE.Mesh(
      new THREE.SphereGeometry(0.015, 12, 8),
      new THREE.MeshBasicMaterial({ color: 0x4ed38a }),
    );
    parentMarker.renderOrder = 9;
    childMarker.renderOrder = 9;
    attachmentGroup.add(line, parentMarker, childMarker);
    attachmentVisuals.set(attachment.id, { line, parentMarker, childMarker, indicator });
  }
  updateAttachmentVisuals();
}

function attachmentBodyObject(bodyId: string): any | null {
  return robotLinkGroups.get(bodyId) ?? actorMeshes.get(bodyId) ?? null;
}

function updateAttachmentVisuals(): void {
  const runtimeStates = new Map(
    (simulationState?.attachments ?? []).map((item) => [item.id, item]),
  );
  const bodyOrigin = new THREE.Vector3();
  const parentPosition = new THREE.Vector3();
  const childPosition = new THREE.Vector3();
  const parentQuaternion = new THREE.Quaternion();
  for (const attachment of currentScene.attachments ?? []) {
    const visual = attachmentVisuals.get(attachment.id);
    const parent = attachmentBodyObject(attachment.parent_body_id);
    const child = attachmentBodyObject(attachment.child_body_id);
    if (!visual || !parent || !child) {
      if (visual) {
        visual.line.visible = false;
        visual.parentMarker.visible = false;
        visual.childMarker.visible = false;
      }
      continue;
    }
    parent.updateWorldMatrix(true, false);
    child.updateWorldMatrix(true, false);
    parent.getWorldPosition(bodyOrigin);
    parent.getWorldQuaternion(parentQuaternion);
    parentPosition.set(...attachment.parent_anchor).applyMatrix4(parent.matrixWorld);
    childPosition.set(...attachment.child_anchor).applyMatrix4(child.matrixWorld);
    const runtime = runtimeStates.get(attachment.id);
    const connected = runtime?.active ?? attachment.initially_active;
    const requested = runtime?.requested_active ?? false;
    const positions = visual.line.geometry.attributes.position;
    positions.setXYZ(0, bodyOrigin.x, bodyOrigin.y, bodyOrigin.z);
    const endpoint = connected ? childPosition : parentPosition;
    positions.setXYZ(1, endpoint.x, endpoint.y, endpoint.z);
    positions.needsUpdate = true;
    visual.line.material.color.set(connected ? 0x4ed38a : requested ? 0xf4b942 : 0x9aa5b1);
    visual.parentMarker.position.copy(parentPosition);
    visual.parentMarker.quaternion.copy(parentQuaternion);
    visual.childMarker.position.copy(childPosition);
    visual.indicator.material.color.set(
      connected ? 0x4ed38a : requested ? 0xf4b942 : 0x75808a,
    );
    if (visual.indicator.material.emissive) {
      visual.indicator.material.emissive.set(
        connected ? 0x0c5c35 : requested ? 0x5a3500 : 0x111820,
      );
    }
    visual.line.visible = true;
    visual.parentMarker.visible = true;
    visual.childMarker.visible = !connected;
  }
}

export function setViewportScene(sceneData: Scene): void {
  const previousActorIds = new Set(actorMeshes.keys());
  const retainedLinkId = selectedLinkId;
  currentScene = sceneData;
  updateEnvironmentAppearance(currentScene);
  const renderableActors = currentScene.actors.filter(
    (actor) => actor.type === 'object' || actor.type === 'robot',
  );
  const nextActorIds = new Set(renderableActors.map((actor) => actor.id));
  for (const actorId of previousActorIds) {
    if (!nextActorIds.has(actorId)) removeActorObject(actorId);
  }
  for (const actor of renderableActors) {
    const signature = actorRenderSignature(actor, currentScene);
    let object = actorMeshes.get(actor.id);
    if (object && actorRenderSignatures.get(actor.id) !== signature) {
      removeActorObject(actor.id);
      object = null;
    }
    if (!object) object = createActorObject(actor, currentScene);
    if (!object) continue;
    updateActorObject(object, actor);
    actorRenderSignatures.set(actor.id, signature);
  }
  for (const linkId of rotorAnimationStates.keys()) {
    if (!robotLinkGroups.has(linkId)) rotorAnimationStates.delete(linkId);
  }
  syncAttachmentVisuals(currentScene);
  selectViewportActor(selectedActorId, false);
  selectViewportLink(retainedLinkId);
  if (simulationState) applySimulationState(simulationState);
  updateHud();
  const addedActors = currentScene.actors.filter((actor) => {
    if (!actorMeshes.has(actor.id) || previousActorIds.has(actor.id)) return false;
    return isLargeEnvironment(actor);
  });
  if (addedActors.length > 0) {
    const focus = addedActors.length === 1 ? actorMeshes.get(addedActors[0].id) : actorGroup;
    requestAnimationFrame(() => frameObject(focus, largeEnvironmentViewDirection.clone()));
  }
}

export function updateViewportTransforms(sceneData: Scene): boolean {
  const renderableActors = sceneData.actors.filter(
    (actor) => actor.type === 'object' || actor.type === 'robot',
  );
  if (
    renderableActors.length !== actorMeshes.size
    || renderableActors.some((actor) => !actorMeshes.has(actor.id))
  ) {
    return false;
  }
  currentScene = sceneData;
  for (const actor of renderableActors) {
    const object = actorMeshes.get(actor.id);
    object.position.set(...actor.transform.position);
    object.rotation.set(...actor.transform.rotation);
    object.scale.set(...actor.transform.scale);
    object.name = actor.name;
    object.userData.actor = actor;
  }
  updateColliderDebugMarkers();
  updateSelectionOutline();
  updateHud();
  return true;
}

export function selectViewportActor(actorId: string | null, notify = false): void {
  selectedActorId = actorId;
  selectedLinkId = null;
  updateSelectionMaterials();
  const selectedMesh = selectedActorId ? actorMeshes.get(selectedActorId) : null;
  if (selectedMesh && !simulationState) transformControls.attach(selectedMesh);
  else transformControls.detach();
  updateSelectionOutline();
  updateHud();
  if (notify) actorSelectedCallback(actorId);
}

export function selectViewportLink(linkId: string | null): void {
  const group = linkId ? robotLinkGroups.get(linkId) : null;
  selectedLinkId = group ? linkId : null;
  if (group?.userData.actorId) selectedActorId = group.userData.actorId;
  transformControls.detach();
  updateSelectionMaterials();
  updateSelectionOutline();
  updateHud();
}

function updateSelectionMaterials(): void {
  for (const [id, object] of actorMeshes.entries()) {
    const actor = currentScene.actors.find((item) => item.id === id);
    const bounds = actor?.properties.geometry?.bounds;
    const largestExtent = bounds
      ? Math.max(...bounds.max.map((value, index) => value - bounds.min[index]))
      : 0;
    const largeEnvironment = largestExtent >= 250;
    object.traverse((mesh) => {
      if (!mesh.material?.emissive) return;
      const linkSelected = selectedLinkId !== null && mesh.userData.linkId === selectedLinkId;
      const actorSelected = selectedLinkId === null && id === selectedActorId;
      const fillHighlight = actorSelected && !largeEnvironment;
      mesh.material.emissive = new THREE.Color(
        linkSelected ? 0x9a6a16 : fillHighlight ? 0x2b6cb0 : 0,
      );
      mesh.material.emissiveIntensity = linkSelected ? 0.65 : fillHighlight ? 0.45 : 0;
    });
  }
}

function updateHud(): void {
  const selected = currentScene.actors.find((actor) => actor.id === selectedActorId);
  const simText = simulationState ? ` | sim t=${simulationState.time.toFixed(3)}` : '';
  const deliveryTask = simulationState?.delivery_tasks?.[0];
  const taskText = deliveryTask ? ` | task ${deliveryTask.status.replace('_', ' ')}` : '';
  requiredElement('#scene-name').textContent = currentScene.name;
  requiredElement('#scene-stats').textContent = `${currentScene.actors.length} actors${simText}${taskText}`;
  const colliderState = selected && colliderDebugVisible
    ? ` | ${actorIsDynamic(selected) ? 'Dynamic' : 'Static'} collider`
    : '';
  const materialState = selected?.properties.physics?.material
    ? ` | ${selected.properties.physics.material}`
    : '';
  const linkName = selectedLinkId ? robotLinkGroups.get(selectedLinkId)?.name : null;
  const linkState = linkName ? ` / ${linkName}` : '';
  requiredElement('#selection').textContent = `Selected: ${selected?.name ?? 'None'}${linkState}${colliderState}${materialState}`;
}

export function applySimulationState(state: SimulationState | null): void {
  simulationState = state;
  if (!state) {
    setViewportScene(currentScene);
    return;
  }
  transformControls.detach();
  for (const actorState of state.actors) {
    const mesh = actorMeshes.get(actorState.id);
    if (!mesh) continue;
    mesh.position.set(...actorState.position);
    const [w, x, y, z] = actorState.quaternion;
    mesh.quaternion.set(x, y, z, w);
  }
  const worldPosition = new THREE.Vector3();
  const worldQuaternion = new THREE.Quaternion();
  const parentQuaternion = new THREE.Quaternion();
  for (const linkState of state.links) {
    const group = robotLinkGroups.get(linkState.id);
    if (!group?.parent) continue;
    group.parent.updateMatrixWorld(true);
    worldPosition.set(...linkState.position);
    group.position.copy(group.parent.worldToLocal(worldPosition));
    const [w, x, y, z] = linkState.quaternion;
    worldQuaternion.set(x, y, z, w);
    group.parent.getWorldQuaternion(parentQuaternion);
    group.quaternion.copy(parentQuaternion.invert().multiply(worldQuaternion));
    group.updateMatrixWorld(true);
  }
  const actuatorControls = new Map(
    state.actuators.map((actuator) => [actuator.id, actuator.ctrl]),
  );
  const rotorAxis = new THREE.Vector3();
  const rotorRotation = new THREE.Quaternion();
  for (const actor of currentScene.actors) {
    const propulsion = actor.properties.propulsion;
    if (propulsion?.type !== 'quadrotor') continue;
    for (const rotor of propulsion.rotors) {
      const group = robotLinkGroups.get(rotor.link_id);
      if (!group) continue;
      const animation = advanceRotorAnimation(
        rotorAnimationStates.get(rotor.link_id),
        state.time,
        actuatorControls.get(rotor.actuator_id) ?? 0,
        rotor.direction,
      );
      rotorAnimationStates.set(rotor.link_id, animation);
      rotorAxis.set(...rotor.axis).normalize();
      rotorRotation.setFromAxisAngle(rotorAxis, animation.angle);
      group.quaternion.multiply(rotorRotation);
      group.updateMatrixWorld(true);
    }
  }
  updateAttachmentVisuals();
  updateSelectionOutline();
  updateHud();
}

function updateSelectionOutline(): void {
  const selectedMesh = (selectedLinkId ? robotLinkGroups.get(selectedLinkId) : null)
    ?? (selectedActorId ? actorMeshes.get(selectedActorId) : null);
  if (!selectedMesh) {
    selectionOutline.visible = false;
    return;
  }
  selectionOutline.visible = true;
  selectionOutline.setFromObject(selectedMesh);
}

function setTransformMode(mode: TransformMode): void {
  transformMode = mode;
  transformControls.setMode(mode);
  for (const button of toolbar.querySelectorAll<HTMLButtonElement>('[data-tool]')) {
    button.classList.toggle('active', button.dataset.tool === mode);
  }
  const selectedMesh = selectedActorId ? actorMeshes.get(selectedActorId) : null;
  if (selectedMesh && !selectedLinkId && !simulationState) transformControls.attach(selectedMesh);
}

function setColliderDebugVisible(visible: boolean): void {
  colliderDebugVisible = visible;
  for (const mesh of actorMeshes.values()) {
    mesh.traverse((child) => {
      if (child.userData.colliderDebug) child.visible = visible;
    });
  }
  const button = toolbar.querySelector<HTMLButtonElement>('[data-action="collider-debug"]');
  button?.classList.toggle('active', visible);
  button?.setAttribute('aria-pressed', String(visible));
  const legend = requiredElement<HTMLElement>('#collider-legend');
  legend.hidden = !visible;
  updateHud();
}

function updateColliderDebugMarkers(): void {
  for (const mesh of actorMeshes.values()) {
    mesh.traverse((child) => {
      if (child.userData.centerOfMass) {
        child.scale.set(1 / mesh.scale.x, 1 / mesh.scale.y, 1 / mesh.scale.z);
      }
    });
  }
}

function getFocusObject(): any {
  return (selectedLinkId ? robotLinkGroups.get(selectedLinkId) : null)
    ?? (selectedActorId ? actorMeshes.get(selectedActorId) : null)
    ?? actorGroup;
}

function frameObject(object: any, direction: any = null): void {
  if (!object || (object === actorGroup && actorGroup.children.length === 0)) return;
  focusBox.setFromObject(object);
  if (focusBox.isEmpty()) return;
  focusBox.getBoundingSphere(focusSphere);
  const radius = Math.max(focusSphere.radius, 0.35);
  const viewDirection = direction ?? camera.position.clone().sub(orbitControls.target).normalize();
  if (viewDirection.lengthSq() < 0.0001) viewDirection.copy(viewDirections.iso);
  const distance = Math.max(radius / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2), 0.75);
  orbitControls.target.copy(focusSphere.center);
  const framePadding = radius >= 250 ? 1.08 : 1.35;
  camera.position.copy(focusSphere.center).add(viewDirection.multiplyScalar(distance * framePadding));
  const cameraDistance = camera.position.distanceTo(orbitControls.target);
  camera.near = Math.max(distance / 2000, 0.01);
  camera.far = Math.max(cameraDistance + radius * 20, 1000);
  // Keep the focused object fully ahead of the fog. Fixed meter-scale fog made kilometre-scale
  // city assets disappear even after the camera itself had been framed correctly.
  if (scene.fog instanceof THREE.Fog) {
    scene.fog.near = Math.max(cameraDistance + radius * 1.25, 18);
    scene.fog.far = Math.max(cameraDistance + radius * 5, 60);
  }
  const gridScale = Math.max((radius * 2.4) / 20, 1);
  grid.scale.setScalar(gridScale);
  canvas.dataset.focusRadius = radius.toFixed(3);
  canvas.dataset.cameraDistance = cameraDistance.toFixed(3);
  canvas.dataset.cameraFar = camera.far.toFixed(3);
  canvas.dataset.fogNear = scene.fog instanceof THREE.Fog
    ? scene.fog.near.toFixed(3)
    : 'none';
  canvas.dataset.fogFar = scene.fog instanceof THREE.Fog
    ? scene.fog.far.toFixed(3)
    : 'none';
  camera.updateProjectionMatrix();
  orbitControls.update();
}

function setCameraView(viewName: CameraView): void {
  const direction = viewDirections[viewName]?.clone();
  if (!direction) return;
  camera.up.set(0, 0, 1);
  if (viewName === 'top') camera.up.set(0, 1, 0);
  frameObject(getFocusObject(), direction);
}

function actorIdForObject(object: any): string | null {
  let current = object;
  while (current && current !== actorGroup) {
    if (current.userData?.actorId) return String(current.userData.actorId);
    current = current.parent;
  }
  return null;
}

renderer.domElement.addEventListener('pointerdown', (event: PointerEvent) => {
  // A gizmo press is not a click on empty scene space. Clearing selection here detaches the
  // TransformControls object and makes the actor lose its highlight after a move.
  if (transformControls.dragging || transformControls.axis !== null) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects([...actorMeshes.values()], true);
  const actorId = hits.map((hit) => actorIdForObject(hit.object))
    .find((id) => id !== null) ?? null;
  selectViewportActor(actorId, true);
});

toolbar.addEventListener('click', (event) => {
  const button = (event.target as Element).closest<HTMLButtonElement>('button');
  if (!button) return;
  if (button.dataset.tool) setTransformMode(button.dataset.tool as TransformMode);
  else if (button.dataset.action === 'frame') frameObject(getFocusObject());
  else if (button.dataset.action === 'collider-debug') setColliderDebugVisible(!colliderDebugVisible);
  else if (button.dataset.camera) setCameraView(button.dataset.camera as CameraView);
});

window.addEventListener('keydown', (event) => {
  if ((event.target as HTMLElement)?.matches('input, select, textarea')) return;
  const shortcuts: Record<string, () => void> = {
    w: () => setTransformMode('translate'),
    e: () => setTransformMode('rotate'),
    r: () => setTransformMode('scale'),
    f: () => frameObject(getFocusObject()),
    c: () => setColliderDebugVisible(!colliderDebugVisible),
    '1': () => setCameraView('front'),
    '3': () => setCameraView('right'),
    '7': () => setCameraView('top'),
    '0': () => setCameraView('iso'),
  };
  const action = shortcuts[event.key.toLowerCase()];
  if (!action) return;
  event.preventDefault();
  action();
});

function animate(): void {
  requestAnimationFrame(animate);
  resize();
  if (cityEnvironmentVisible) {
    citySky.position.copy(camera.position);
    citySky.scale.setScalar(Math.max(camera.far * 0.8, 500));
  }
  orbitControls.update();
  updateColliderDebugMarkers();
  updateAttachmentVisuals();
  updateSelectionOutline();
  renderer.render(scene, camera);
}

window.addEventListener('resize', resize);
resize();
animate();
