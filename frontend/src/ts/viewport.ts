import * as THREE from '../vendor/three.module.js';
import { OrbitControls } from '../vendor/OrbitControls.js';
import { TransformControls } from '../vendor/TransformControls.js';

import { sourceGeometry } from './geometry-contract.js';
import { decodeGeometryBundle, type BundledGeometry } from './geometry-bundle.js';
import { createFittedPbrVisual } from './pbr-model-loader.js';
import { loadPhotographicEnvironment } from './photographic-environment.js';
import {
  applyProceduralSurface,
  createProceduralEnvironmentTexture,
  type ProceduralSurfaceKind,
} from './procedural-materials.js';
import {
  advanceRotorAnimation,
  jointLocalPose,
  type RotorAnimationState,
} from './robot-kinematics.js';
import type {
  Actor,
  RobotArticulation,
  RobotSensor,
  RangefinderSensorSample,
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
const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  powerPreference: 'high-performance',
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setClearColor(0x101d29, 1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.08;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
canvas.dataset.renderQuality = 'enhanced';
canvas.dataset.renderFpsCap = '45';

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x243746, 28, 90);
const environmentTexture = createProceduralEnvironmentTexture();
if (environmentTexture) {
  scene.environment = environmentTexture;
  canvas.dataset.environmentLighting = 'procedural-pmrem';
}
canvas.dataset.photographicEnvironment = 'loading';
void loadPhotographicEnvironment(
  './environments/polyhaven/abandoned_hopper_terminal_03_1k.hdr',
).then((texture) => {
  const previous = scene.environment;
  scene.environment = texture;
  canvas.dataset.environmentLighting = 'photographic-hdri-pmrem';
  canvas.dataset.photographicEnvironment = 'loaded';
  if (previous && previous !== texture) previous.dispose();
}).catch(() => {
  canvas.dataset.photographicEnvironment = 'failed';
});

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
grid.position.z = 0.012;
grid.material.transparent = true;
grid.material.opacity = 0.42;
grid.material.depthWrite = false;
scene.add(grid);
const axes = new THREE.AxesHelper(2);
scene.add(axes);

const editorFloor = new THREE.Mesh(
  new THREE.PlaneGeometry(60, 60),
  new THREE.MeshStandardMaterial({
    color: 0x23323c,
    roughness: 0.96,
    metalness: 0.02,
  }),
);
editorFloor.position.z = -0.065;
editorFloor.receiveShadow = true;
editorFloor.userData.editorEnvironment = true;
applyProceduralSurface(editorFloor.material, 'concrete', {
  repeat: [24, 24],
  anisotropy: renderer.capabilities.getMaxAnisotropy(),
  bumpScale: 0.014,
  envMapIntensity: 0.46,
});
scene.add(editorFloor);

const ambient = new THREE.HemisphereLight(0xd9edff, 0x56636b, 1.72);
scene.add(ambient);

const keyLightDirection = new THREE.Vector3(-0.45, 0.3, 0.72).normalize();
const keyLight = new THREE.DirectionalLight(0xffedcf, 2.45);
keyLight.position.copy(keyLightDirection).multiplyScalar(15);
keyLight.castShadow = true;
keyLight.shadow.mapSize.set(2048, 2048);
keyLight.shadow.bias = -0.00035;
keyLight.shadow.normalBias = 0.025;
keyLight.shadow.camera.near = 0.5;
keyLight.shadow.camera.far = 50;
keyLight.shadow.camera.left = -12;
keyLight.shadow.camera.right = 12;
keyLight.shadow.camera.top = 12;
keyLight.shadow.camera.bottom = -12;
scene.add(keyLight, keyLight.target);

const fillLight = new THREE.DirectionalLight(0x9dc9ef, 0.72);
fillLight.position.set(-5, 3, 4);
scene.add(fillLight);

const editorSky = new THREE.Mesh(
  new THREE.SphereGeometry(1, 32, 16),
  new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      lowerColor: { value: new THREE.Color(0x314653) },
      horizonColor: { value: new THREE.Color(0xa6c0ce) },
      zenithColor: { value: new THREE.Color(0x3b6b8b) },
      sunColor: { value: new THREE.Color(0xffd49c) },
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
      uniform vec3 lowerColor;
      uniform vec3 horizonColor;
      uniform vec3 zenithColor;
      uniform vec3 sunColor;
      void main() {
        float height = clamp(vSkyDirection.z, -1.0, 1.0);
        float horizonMix = smoothstep(-0.32, 0.08, height);
        float skyMix = pow(max(height, 0.0), 0.58);
        vec3 upper = mix(horizonColor, zenithColor, skyMix);
        vec3 color = mix(lowerColor, upper, horizonMix);
        vec3 sunDirection = normalize(vec3(-0.45, 0.30, 0.72));
        float glow = pow(max(dot(vSkyDirection, sunDirection), 0.0), 48.0);
        float sun = smoothstep(0.996, 0.9993, dot(vSkyDirection, sunDirection));
        color += sunColor * (glow * 0.22 + sun * 1.15);
        gl_FragColor = vec4(color, 1.0);
      }
    `,
  }),
);
editorSky.frustumCulled = false;
editorSky.renderOrder = -101;
scene.add(editorSky);

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
const rangefinderGroup = new THREE.Group();
scene.add(rangefinderGroup);
const navigationGroup = new THREE.Group();
scene.add(navigationGroup);

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
const photorealModelStates = new Map<string, 'loading' | 'loaded' | 'failed'>();
const attachmentVisuals = new Map<string, {
  line: any;
  parentMarker: any;
  childMarker: any;
  indicator: any;
}>();
let attachmentRenderSignature = '';
const rangefinderVisuals = new Map<string, { line: any; sensor: RobotSensor }>();
let rangefinderRenderSignature = '';
let navigationRenderSignature = '';
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
  canvas.dataset.shadowMode = cityEnvironmentVisible ? 'disabled' : 'soft';
  grid.visible = !cityEnvironmentVisible;
  axes.visible = !cityEnvironmentVisible;
  editorFloor.visible = !cityEnvironmentVisible;
  editorSky.visible = !cityEnvironmentVisible;
  citySky.visible = cityEnvironmentVisible;
  renderer.setClearColor(cityEnvironmentVisible ? 0xb9d3e3 : 0x101d29, 1);
  renderer.toneMappingExposure = 1.08;
  keyLight.castShadow = !cityEnvironmentVisible;
  if (scene.fog instanceof THREE.Fog) {
    scene.fog.color.set(cityEnvironmentVisible ? 0xc4d8e2 : 0x243746);
  }
  ambient.color.set(cityEnvironmentVisible ? 0xcce5ff : 0xd9edff);
  ambient.groundColor.set(cityEnvironmentVisible ? 0x53665d : 0x56636b);
  ambient.intensity = cityEnvironmentVisible ? 1.25 : 1.72;
  keyLight.intensity = cityEnvironmentVisible ? 2.1 : 2.45;
  fillLight.intensity = cityEnvironmentVisible ? 0.5 : 0.72;
  const environmentModeChanged = cityEnvironmentVisible !== wasCityEnvironmentVisible;
  if (scene.fog instanceof THREE.Fog && environmentModeChanged) {
    // A large environment gets camera-dependent fog distances in frameObject(). Preserve those
    // distances while reconciling unrelated actors; resetting them to the editor defaults would
    // fog out a kilometre-scale scene and make it flash white after every scene edit.
    scene.fog.near = cityEnvironmentVisible ? 18 : 28;
    scene.fog.far = cityEnvironmentVisible ? 60 : 90;
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
  const importedMesh = actor.properties.geometry?.kind === 'mesh';
  const primitive = importedMesh
    ? 'mesh'
    : sourceGeometry(actor).geomType;
  const physics = actor.properties.physics ?? { dynamic: true };
  const materialVisual = materialVisuals[physics.material ?? 'default'] ?? materialVisuals.default;
  const options = {
    color: new THREE.Color(rgba[0], rgba[1], rgba[2]),
    roughness: physics.roughness ?? materialVisual.roughness,
    metalness: physics.metalness ?? materialVisual.metalness,
    transparent: rgba[3] < 1,
    opacity: rgba[3],
    side: primitive === 'plane' ? THREE.DoubleSide : THREE.FrontSide,
    dithering: true,
    envMapIntensity: importedMesh ? 0.68 : 0.78,
  };
  if (importedMesh) return new THREE.MeshStandardMaterial(options);
  const style = actor.properties.visual_style;
  const highFidelityCoating = style === 'insulated_delivery_bag'
    || style?.startsWith('landing_pad_');
  const material = highFidelityCoating
    ? new THREE.MeshPhysicalMaterial({
      ...options,
      clearcoat: style?.startsWith('landing_pad_') ? 0.58 : 0.08,
      clearcoatRoughness: style?.startsWith('landing_pad_') ? 0.3 : 0.72,
      ior: 1.48,
      sheen: style === 'insulated_delivery_bag' ? 0.28 : 0,
      sheenRoughness: 0.88,
      sheenColor: new THREE.Color(0x89939a),
    })
    : new THREE.MeshStandardMaterial(options);
  let surface: ProceduralSurfaceKind | null = null;
  let repeat: [number, number] = [2, 2];
  let bumpScale = 0.006;
  if (style === 'operations_ground') {
    surface = 'concrete';
    const size = actor.properties.size ?? [5, 5, 0.05];
    repeat = [Math.max(size[0] ?? 5, 1), Math.max(size[1] ?? 5, 1)];
    bumpScale = 0.012;
  } else if (style === 'shipping_package') {
    surface = 'cardboard';
    repeat = [3.5, 3];
    bumpScale = 0.007;
  } else if (style === 'insulated_delivery_bag') {
    surface = 'woven_fabric';
    repeat = [1.35, 1.35];
    bumpScale = 0.009;
  } else if (style?.startsWith('landing_pad_')) {
    surface = 'epoxy';
    repeat = [2.2, 2.2];
    bumpScale = 0.0025;
  } else if (
    style === 'known_obstacle'
    || style === 'unmapped_obstacle'
    || style === 'safety_pillar'
  ) {
    surface = 'powder_coat';
    repeat = [2.5, 5];
    bumpScale = 0.0045;
  }
  if (surface) {
    applyProceduralSurface(material, surface, {
      repeat,
      anisotropy: renderer.capabilities.getMaxAnisotropy(),
      bumpScale,
      envMapIntensity: style === 'operations_ground' ? 0.58 : 0.82,
    });
  }
  return material;
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
  mesh.material.roughness = 1;
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

function roundedRectangleGeometry(
  width: number,
  depth: number,
  height: number,
  radius: number,
): any {
  const bevel = Math.min(0.006, radius * 0.35, height * 0.16);
  const halfWidth = width * 0.5 - bevel;
  const halfDepth = depth * 0.5 - bevel;
  const corner = Math.min(radius, halfWidth * 0.45, halfDepth * 0.45);
  const shape = new THREE.Shape();
  shape.moveTo(-halfWidth + corner, -halfDepth);
  shape.lineTo(halfWidth - corner, -halfDepth);
  shape.quadraticCurveTo(halfWidth, -halfDepth, halfWidth, -halfDepth + corner);
  shape.lineTo(halfWidth, halfDepth - corner);
  shape.quadraticCurveTo(halfWidth, halfDepth, halfWidth - corner, halfDepth);
  shape.lineTo(-halfWidth + corner, halfDepth);
  shape.quadraticCurveTo(-halfWidth, halfDepth, -halfWidth, halfDepth - corner);
  shape.lineTo(-halfWidth, -halfDepth + corner);
  shape.quadraticCurveTo(-halfWidth, -halfDepth, -halfWidth + corner, -halfDepth);
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: Math.max(height - bevel * 2, 0.005),
    steps: 1,
    curveSegments: 8,
    bevelEnabled: true,
    bevelSegments: 4,
    bevelSize: bevel,
    bevelThickness: bevel,
  });
  geometry.translate(0, 0, -height * 0.5 + bevel);
  geometry.computeVertexNormals();
  return geometry;
}

function addInsulatedDeliveryBagDetails(
  mesh: any,
  actor: Actor,
  loadRevision: number,
): void {
  if (actor.properties.visual_style !== 'insulated_delivery_bag') return;
  const size = actor.properties.size ?? [0.18, 0.14, 0.11];
  const halfX = size[0] ?? 0.18;
  const halfY = size[1] ?? 0.14;
  const halfZ = size[2] ?? 0.11;
  const width = halfX * 2;
  const depth = halfY * 2;
  const bodyHeight = halfZ * 2 - 0.028;
  mesh.geometry.dispose();
  mesh.geometry = roundedRectangleGeometry(width, depth, bodyHeight, 0.025);
  mesh.material.color.set(0xffffff);
  mesh.material.metalness = 0;
  mesh.material.roughness = 1;
  mesh.material.clearcoat = 0.08;
  mesh.material.clearcoatRoughness = 0.72;
  mesh.userData.deliveryBagFabric = true;

  const lid = new THREE.Mesh(
    roundedRectangleGeometry(width * 0.98, depth * 0.98, 0.032, 0.022),
    mesh.material,
  );
  lid.position.z = halfZ - 0.017;
  lid.castShadow = true;
  lid.receiveShadow = true;
  lid.userData.actorDetail = true;
  lid.userData.deliveryBagFabric = true;
  mesh.add(lid);

  const accentMaterial = new THREE.MeshStandardMaterial({
    color: 0xf28a28,
    roughness: 0.34,
    metalness: 0.08,
    envMapIntensity: 0.9,
  });
  const zipperMaterial = new THREE.MeshStandardMaterial({
    color: 0x15181b,
    roughness: 0.38,
    metalness: 0.62,
  });
  const rubberMaterial = new THREE.MeshStandardMaterial({
    color: 0x090a0b,
    roughness: 0.92,
    metalness: 0,
  });
  const addDetail = (
    geometry: any,
    material: any,
    position: [number, number, number],
  ): any => {
    const detail = new THREE.Mesh(geometry, material);
    detail.position.set(...position);
    detail.castShadow = false;
    detail.receiveShadow = true;
    detail.userData.actorDetail = true;
    mesh.add(detail);
    return detail;
  };

  const seamZ = halfZ - 0.034;
  for (const y of [-halfY * 0.97, halfY * 0.97]) {
    addDetail(
      new THREE.BoxGeometry(width * 0.84, 0.009, 0.009),
      accentMaterial.clone(),
      [0, y, seamZ],
    );
    addDetail(
      new THREE.BoxGeometry(width * 0.88, 0.007, 0.008),
      zipperMaterial.clone(),
      [0, y * 1.012, seamZ + 0.011],
    );
  }
  for (const x of [-halfX * 0.97, halfX * 0.97]) {
    addDetail(
      new THREE.BoxGeometry(0.009, depth * 0.84, 0.009),
      accentMaterial.clone(),
      [x, 0, seamZ],
    );
    addDetail(
      new THREE.BoxGeometry(0.007, depth * 0.88, 0.008),
      zipperMaterial.clone(),
      [x * 1.012, 0, seamZ + 0.011],
    );
  }
  const verticalSeamGeometry = new THREE.CylinderGeometry(
    0.0045,
    0.0045,
    bodyHeight * 0.72,
    12,
  ).rotateX(Math.PI / 2);
  for (const x of [-halfX * 0.94, halfX * 0.94]) {
    for (const y of [-halfY * 0.94, halfY * 0.94]) {
      addDetail(verticalSeamGeometry.clone(), accentMaterial.clone(), [x, y, -0.006]);
    }
  }

  for (const y of [-halfY * 0.88, halfY * 0.88]) {
    const handleCurve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-halfX * 0.58, y, halfZ - 0.012),
      new THREE.Vector3(-halfX * 0.42, y, halfZ + 0.032),
      new THREE.Vector3(halfX * 0.42, y, halfZ + 0.032),
      new THREE.Vector3(halfX * 0.58, y, halfZ - 0.012),
    ]);
    addDetail(
      new THREE.TubeGeometry(handleCurve, 28, 0.007, 8, false),
      rubberMaterial.clone(),
      [0, 0, 0],
    );
  }

  const frontPanel = addDetail(
    roundedRectangleGeometry(width * 0.58, 0.008, bodyHeight * 0.42, 0.012),
    new THREE.MeshStandardMaterial({
      color: 0x22282d,
      roughness: 0.66,
      metalness: 0.02,
    }),
    [0, -halfY - 0.005, -0.005],
  );
  frontPanel.userData.deliveryBagPanel = true;
  const reflectiveStrip = addDetail(
    new THREE.BoxGeometry(width * 0.46, 0.004, 0.018),
    new THREE.MeshPhysicalMaterial({
      color: 0xc9d5d8,
      roughness: 0.22,
      metalness: 0.72,
      clearcoat: 0.55,
      clearcoatRoughness: 0.18,
      envMapIntensity: 1.1,
    }),
    [0, -halfY - 0.011, -0.005],
  );
  reflectiveStrip.userData.deliveryBagReflector = true;

  const zipperPull = addDetail(
    new THREE.BoxGeometry(0.022, 0.012, 0.006),
    accentMaterial.clone(),
    [halfX * 0.52, -halfY - 0.012, seamZ + 0.016],
  );
  zipperPull.rotation.z = -0.28;
  for (const x of [-halfX * 0.72, halfX * 0.72]) {
    for (const y of [-halfY * 0.68, halfY * 0.68]) {
      addDetail(
        new THREE.CylinderGeometry(0.013, 0.015, 0.012, 16).rotateX(Math.PI / 2),
        rubberMaterial.clone(),
        [x, y, -halfZ - 0.002],
      );
    }
  }

  const textureUrl = new URL(
    './textures/delivery-bag-oxford-albedo.png',
    document.baseURI,
  ).href;
  canvas.dataset.deliveryBagTexture = 'loading';
  new THREE.TextureLoader().load(textureUrl, (texture) => {
    if (!actorLoadIsCurrent(actor.id, mesh, loadRevision)) {
      texture.dispose();
      return;
    }
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(1.35, 1.35);
    texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);
    const previousMap = mesh.material.map;
    mesh.material.map = texture;
    mesh.material.color.set(0xffffff);
    mesh.material.needsUpdate = true;
    if (previousMap && previousMap !== texture) previousMap.dispose();
    canvas.dataset.deliveryBagTexture = 'loaded';
    updateSelectionOutline();
  }, undefined, () => {
    if (actorLoadIsCurrent(actor.id, mesh, loadRevision)) {
      canvas.dataset.deliveryBagTexture = 'failed';
    }
  });
}

function canvasTexture(
  size: number,
  paint: (context: CanvasRenderingContext2D, size: number) => void,
): any | null {
  const surface = document.createElement('canvas');
  surface.width = size;
  surface.height = size;
  const context = surface.getContext('2d');
  if (!context) return null;
  paint(context, size);
  const texture = new THREE.CanvasTexture(surface);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);
  return texture;
}

function operationsDeckTexture(repeatX: number, repeatY: number): any | null {
  const texture = canvasTexture(256, (context, size) => {
    context.clearRect(0, 0, size, size);
    context.strokeStyle = 'rgba(190, 218, 224, 0.18)';
    context.lineWidth = 2;
    context.strokeRect(1, 1, size - 2, size - 2);
    context.strokeStyle = 'rgba(8, 18, 23, 0.2)';
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(size / 2, 0);
    context.lineTo(size / 2, size);
    context.moveTo(0, size / 2);
    context.lineTo(size, size / 2);
    context.stroke();
  });
  if (!texture) return null;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(repeatX, repeatY);
  return texture;
}

function landingPadTexture(label: string, accent: string): any | null {
  return canvasTexture(512, (context, size) => {
    context.clearRect(0, 0, size, size);
    const center = size / 2;
    const radius = size * 0.4;
    const glow = context.createRadialGradient(center, center, radius * 0.2, center, center, radius);
    glow.addColorStop(0, 'rgba(255, 255, 255, 0.08)');
    glow.addColorStop(0.7, 'rgba(255, 255, 255, 0.025)');
    glow.addColorStop(1, 'rgba(255, 255, 255, 0)');
    context.fillStyle = glow;
    context.beginPath();
    context.arc(center, center, radius, 0, Math.PI * 2);
    context.fill();
    context.strokeStyle = 'rgba(244, 250, 255, 0.95)';
    context.lineWidth = size * 0.025;
    context.beginPath();
    context.arc(center, center, radius * 0.82, 0, Math.PI * 2);
    context.stroke();
    context.strokeStyle = accent;
    context.lineWidth = size * 0.012;
    context.setLineDash([size * 0.07, size * 0.045]);
    context.beginPath();
    context.arc(center, center, radius * 0.64, 0, Math.PI * 2);
    context.stroke();
    context.setLineDash([]);
    context.fillStyle = 'rgba(247, 251, 255, 0.98)';
    context.font = `700 ${Math.round(size * 0.34)}px system-ui, sans-serif`;
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(label, center, center * 1.02);
    context.font = `600 ${Math.round(size * 0.052)}px system-ui, sans-serif`;
    context.letterSpacing = `${Math.round(size * 0.012)}px`;
    context.fillText(label === 'A' ? 'PICKUP' : 'DROPOFF', center, size * 0.82);
  });
}

function addOperationsGroundDetails(mesh: any, actor: Actor): void {
  const size = actor.properties.size ?? [5, 5, 0.05];
  const halfX = size[0] ?? 5;
  const halfY = size[1] ?? 5;
  const halfZ = size[2] ?? 0.05;
  mesh.material.color.set(0x43545d);
  const texture = operationsDeckTexture(Math.max(halfX, 1), Math.max(halfY, 1));
  const markings = new THREE.Mesh(
    new THREE.PlaneGeometry(halfX * 2, halfY * 2),
    new THREE.MeshBasicMaterial({
      map: texture,
      transparent: true,
      depthWrite: false,
      toneMapped: false,
    }),
  );
  markings.position.z = halfZ + 0.002;
  markings.renderOrder = 1;
  markings.userData.actorDetail = true;
  mesh.add(markings);
}

function addLandingPadDetails(mesh: any, actor: Actor, label: string, accent: string): void {
  const size = actor.properties.size ?? [0.75, 0.75, 0.025];
  const halfX = size[0] ?? 0.75;
  const halfY = size[1] ?? 0.75;
  const halfZ = size[2] ?? 0.025;
  mesh.material.roughness = 1;
  mesh.material.metalness = 0.04;
  const texture = landingPadTexture(label, accent);
  const decal = new THREE.Mesh(
    new THREE.PlaneGeometry(halfX * 1.86, halfY * 1.86),
    new THREE.MeshBasicMaterial({
      map: texture,
      transparent: true,
      depthWrite: false,
      toneMapped: false,
    }),
  );
  decal.position.z = halfZ + 0.003;
  decal.renderOrder = 2;
  decal.userData.actorDetail = true;
  mesh.add(decal);
}

function addObstacleDetails(mesh: any, actor: Actor, accent: number, beacon = false): void {
  const size = actor.properties.size ?? [0.25, 0.25, 1];
  const halfX = size[0] ?? 0.25;
  const halfY = size[1] ?? 0.25;
  const halfZ = size[2] ?? 1;
  mesh.material.roughness = 1;
  mesh.material.metalness = 0.06;
  const bandMaterial = new THREE.MeshStandardMaterial({
    color: accent,
    emissive: accent,
    emissiveIntensity: beacon ? 0.28 : 0.12,
    roughness: 0.3,
    metalness: 0.58,
    envMapIntensity: 0.9,
  });
  for (const [index, z] of [-halfZ * 0.72, halfZ * 0.72].entries()) {
    const band = new THREE.Mesh(
      new THREE.BoxGeometry(halfX * 2 + 0.018, halfY * 2 + 0.018, 0.055),
      index === 0 ? bandMaterial : bandMaterial.clone(),
    );
    band.position.z = z;
    band.castShadow = true;
    band.receiveShadow = true;
    band.userData.actorDetail = true;
    mesh.add(band);
  }
  const cap = new THREE.Mesh(
    new THREE.BoxGeometry(halfX * 2 + 0.012, halfY * 2 + 0.012, 0.035),
    bandMaterial.clone(),
  );
  cap.position.z = halfZ + 0.017;
  cap.castShadow = true;
  cap.userData.actorDetail = true;
  mesh.add(cap);
  if (beacon) {
    const light = new THREE.Mesh(
      new THREE.SphereGeometry(Math.min(halfX, halfY) * 0.24, 20, 12),
      new THREE.MeshStandardMaterial({
        color: 0xffa8f5,
        emissive: accent,
        emissiveIntensity: 2.6,
        roughness: 0.18,
      }),
    );
    light.position.z = halfZ + 0.075;
    light.userData.actorDetail = true;
    mesh.add(light);
  }
}

function updatePhotorealModelDataset(): void {
  const states = [...photorealModelStates.values()];
  canvas.dataset.photorealObstacleCount = states.length.toString();
  canvas.dataset.photorealObstacleLoaded = states
    .filter((state) => state === 'loaded').length.toString();
  canvas.dataset.photorealObstacleStatus = states.some((state) => state === 'failed')
    ? 'failed'
    : states.length > 0 && states.every((state) => state === 'loaded')
      ? 'loaded'
      : states.length > 0 ? 'loading' : 'none';
}

function addConstructionFenceExtension(mesh: any, actor: Actor): void {
  if (actor.properties.visual_style !== 'known_obstacle') return;
  const size = actor.properties.size ?? [0.25, 0.8, 1.2];
  const halfX = size[0] ?? 0.25;
  const halfY = size[1] ?? 0.8;
  const extensionHeight = size[2] ?? 1.2;
  const steel = new THREE.MeshStandardMaterial({
    color: 0x67737a,
    roughness: 0.38,
    metalness: 0.82,
    envMapIntensity: 1.08,
  });
  const addSteel = (geometry: any, position: [number, number, number]): any => {
    const detail = new THREE.Mesh(geometry, steel.clone());
    detail.position.set(...position);
    detail.castShadow = true;
    detail.receiveShadow = true;
    detail.userData.actorDetail = true;
    detail.userData.constructionFence = true;
    mesh.add(detail);
    return detail;
  };

  const postGeometry = new THREE.CylinderGeometry(
    0.027,
    0.032,
    extensionHeight,
    16,
  ).rotateX(Math.PI / 2);
  for (const y of [-halfY * 0.9, 0, halfY * 0.9]) {
    addSteel(postGeometry.clone(), [0, y, extensionHeight * 0.5]);
  }
  for (const z of [0.07, extensionHeight - 0.07]) {
    addSteel(
      new THREE.CylinderGeometry(0.018, 0.018, halfY * 1.8, 12),
      [0, 0, z],
    );
  }

  const wirePoints: any[] = [];
  const bottom = 0.1;
  const top = extensionHeight - 0.1;
  const span = halfY * 1.72;
  const step = 0.16;
  for (let y = -span; y <= span; y += step) {
    wirePoints.push(
      new THREE.Vector3(0, y, bottom),
      new THREE.Vector3(0, Math.min(y + 0.55, span), top),
      new THREE.Vector3(0, y, top),
      new THREE.Vector3(0, Math.min(y + 0.55, span), bottom),
    );
  }
  const wire = new THREE.LineSegments(
    new THREE.BufferGeometry().setFromPoints(wirePoints),
    new THREE.LineBasicMaterial({
      color: 0x9aa5aa,
      transparent: true,
      opacity: 0.68,
    }),
  );
  wire.position.x = -halfX - 0.008;
  wire.userData.actorDetail = true;
  wire.userData.constructionFence = true;
  mesh.add(wire);

  const warning = addSteel(
    new THREE.PlaneGeometry(0.22, 0.38),
    [-halfX - 0.012, 0, extensionHeight * 0.54],
  );
  warning.rotation.y = Math.PI / 2;
  warning.material.color.set(0xe9a42b);
  warning.material.roughness = 0.32;
  warning.material.metalness = 0.18;
  warning.material.side = THREE.DoubleSide;
}

function addPhotorealActorVisual(mesh: any, actor: Actor, loadRevision: number): boolean {
  const config = actor.properties.visual_model;
  if (!config) return false;
  photorealModelStates.set(actor.id, 'loading');
  updatePhotorealModelDataset();

  // The primitive stays raycastable and remains the physics/collider-debug proxy, but it does
  // not compete visually with the authored glTF surface.
  mesh.material.transparent = true;
  mesh.material.opacity = 0;
  mesh.material.depthWrite = false;
  mesh.material.colorWrite = false;
  mesh.material.needsUpdate = true;
  mesh.castShadow = false;
  mesh.userData.photorealProxy = true;
  addConstructionFenceExtension(mesh, actor);

  void createFittedPbrVisual(
    config,
    renderer.capabilities.getMaxAnisotropy(),
  ).then((visual) => {
    if (!actorLoadIsCurrent(actor.id, mesh, loadRevision)) {
      disposeObject(visual);
      return;
    }
    visual.userData.actorDetail = true;
    visual.userData.actorId = actor.id;
    mesh.add(visual);
    photorealModelStates.set(actor.id, 'loaded');
    updatePhotorealModelDataset();
    updateSelectionMaterials();
    updateSelectionOutline();
  }).catch(() => {
    if (!actorLoadIsCurrent(actor.id, mesh, loadRevision)) return;
    // A local asset failure should degrade to the existing procedural obstacle, never to an
    // invisible physics body.
    mesh.material.opacity = 1;
    mesh.material.depthWrite = true;
    mesh.material.colorWrite = true;
    mesh.material.transparent = false;
    mesh.material.needsUpdate = true;
    mesh.castShadow = true;
    const style = actor.properties.visual_style;
    addObstacleDetails(
      mesh,
      actor,
      style === 'unmapped_obstacle' ? 0xff5ce1
        : style === 'known_obstacle' ? 0xffc247 : 0xffb647,
      style === 'unmapped_obstacle',
    );
    photorealModelStates.set(actor.id, 'failed');
    updatePhotorealModelDataset();
  });
  return true;
}

function addActorVisualDetails(mesh: any, actor: Actor, loadRevision: number): void {
  if (addPhotorealActorVisual(mesh, actor, loadRevision)) return;
  const visualStyle = actor.properties.visual_style;
  if (visualStyle === 'shipping_package') addShippingPackageDetails(mesh, actor);
  else if (visualStyle === 'insulated_delivery_bag') {
    addInsulatedDeliveryBagDetails(mesh, actor, loadRevision);
  }
  else if (visualStyle === 'operations_ground') addOperationsGroundDetails(mesh, actor);
  else if (visualStyle === 'landing_pad_pickup') {
    addLandingPadDetails(mesh, actor, 'A', 'rgba(95, 190, 255, 0.95)');
  } else if (visualStyle === 'landing_pad_dropoff') {
    addLandingPadDetails(mesh, actor, 'B', 'rgba(102, 235, 151, 0.95)');
  } else if (visualStyle === 'known_obstacle') {
    addObstacleDetails(mesh, actor, 0xffc247);
  } else if (visualStyle === 'unmapped_obstacle') {
    addObstacleDetails(mesh, actor, 0xff5ce1, true);
  } else if (visualStyle === 'safety_pillar') {
    addObstacleDetails(mesh, actor, 0xffb647);
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
          dithering: true,
          envMapIntensity: 0.72,
        }),
      );
      mesh.castShadow = true;
      mesh.receiveShadow = true;
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
  const materials = new Set<any>();
  const textures = new Set<any>();
  object.traverse((child) => {
    child.geometry?.dispose();
    const childMaterials = Array.isArray(child.material)
      ? child.material
      : child.material ? [child.material] : [];
    for (const material of childMaterials) {
      materials.add(material);
      for (const slot of ['map', 'bumpMap', 'normalMap', 'roughnessMap', 'metalnessMap']) {
        if (material[slot]) textures.add(material[slot]);
      }
    }
  });
  for (const texture of textures) texture.dispose();
  for (const material of materials) material.dispose();
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

function updateShadowFrustum(): void {
  if (cityEnvironmentVisible || actorGroup.children.length === 0) return;
  focusBox.setFromObject(actorGroup);
  if (focusBox.isEmpty()) return;
  focusBox.getBoundingSphere(focusSphere);
  const shadowRadius = Math.max(6, Math.min(focusSphere.radius * 1.3, 35));
  const lightDistance = shadowRadius * 2.4 + 8;
  keyLight.target.position.copy(focusSphere.center);
  keyLight.position.copy(focusSphere.center).addScaledVector(
    keyLightDirection,
    lightDistance,
  );
  keyLight.shadow.camera.left = -shadowRadius;
  keyLight.shadow.camera.right = shadowRadius;
  keyLight.shadow.camera.top = shadowRadius;
  keyLight.shadow.camera.bottom = -shadowRadius;
  keyLight.shadow.camera.near = Math.max(0.5, lightDistance - shadowRadius * 1.8);
  keyLight.shadow.camera.far = lightDistance + shadowRadius * 2.2;
  keyLight.shadow.camera.updateProjectionMatrix();
  keyLight.target.updateMatrixWorld();
  canvas.dataset.shadowRadius = shadowRadius.toFixed(3);
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
  photorealModelStates.delete(actorId);
  updatePhotorealModelDataset();
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
  mesh.castShadow = actor.properties.visual_style !== 'operations_ground';
  mesh.receiveShadow = true;
  addColliderDebug(mesh, actor);
  addActorVisualDetails(mesh, actor, loadRevision);
  mesh.traverse((child) => {
    if (!child.geometry || !child.material) return;
    if (!child.userData.actorDetail) child.castShadow = mesh.castShadow;
    child.receiveShadow = true;
  });
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

function syncRangefinderVisuals(sceneData: Scene): void {
  const sensors = (sceneData.robotics?.articulations ?? [])
    .flatMap((articulation) => articulation.sensors)
    .filter((sensor) => sensor.sensor_type === 'rangefinder');
  const signature = JSON.stringify(sensors);
  if (signature === rangefinderRenderSignature) return;
  for (const visual of rangefinderVisuals.values()) {
    rangefinderGroup.remove(visual.line);
    disposeObject(visual.line);
  }
  rangefinderVisuals.clear();
  rangefinderRenderSignature = signature;
  for (const sensor of sensors) {
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(),
        new THREE.Vector3(0, 0, sensor.max_distance ?? 1),
      ]),
      new THREE.LineBasicMaterial({
        color: 0x73808c,
        transparent: true,
        opacity: 0.72,
        depthTest: false,
      }),
    );
    line.visible = false;
    line.frustumCulled = false;
    line.renderOrder = 7;
    rangefinderGroup.add(line);
    rangefinderVisuals.set(sensor.id, { line, sensor });
  }
}

function updateRangefinderVisuals(): void {
  const samples = new Map(
    (simulationState?.sensors ?? [])
      .filter((sensor) => sensor.sensor_type === 'rangefinder')
      .map((sensor) => [sensor.id, sensor]),
  );
  const origin = new THREE.Vector3();
  const endpoint = new THREE.Vector3();
  const direction = new THREE.Vector3();
  const sensorQuaternion = new THREE.Quaternion();
  const parentQuaternion = new THREE.Quaternion();
  for (const [sensorId, visual] of rangefinderVisuals.entries()) {
    const parent = visual.sensor.link_id
      ? robotLinkGroups.get(visual.sensor.link_id)
      : null;
    const transform = visual.sensor.local_transform;
    const sample = samples.get(sensorId);
    if (!simulationState || !parent || !transform || !sample) {
      visual.line.visible = false;
      continue;
    }
    parent.updateWorldMatrix(true, false);
    origin.set(...transform.position).applyMatrix4(parent.matrixWorld);
    sensorQuaternion.set(...transform.quaternion);
    parent.getWorldQuaternion(parentQuaternion);
    direction.set(0, 0, 1)
      .applyQuaternion(sensorQuaternion)
      .applyQuaternion(parentQuaternion)
      .normalize();
    endpoint.copy(origin).addScaledVector(direction, sample.distance);
    const positions = visual.line.geometry.attributes.position;
    positions.setXYZ(0, origin.x, origin.y, origin.z);
    positions.setXYZ(1, endpoint.x, endpoint.y, endpoint.z);
    positions.needsUpdate = true;
    visual.line.material.color.set(
      !sample.hit ? 0x73808c
        : sample.distance < 0.7 ? 0xff4d4f
          : sample.distance < 1.5 ? 0xffbf3f : 0x43d3a5,
    );
    visual.line.visible = true;
  }
}

function syncNavigationVisual(sceneData: Scene): void {
  const navigation = sceneData.simulation_config.navigation as {
    route?: [number, number, number][];
  } | undefined;
  const runtimeNavigation = simulationState?.navigation;
  const route = runtimeNavigation?.route.length
    ? runtimeNavigation.route
    : navigation?.route ?? [];
  const status = runtimeNavigation?.status ?? 'ready';
  const signature = JSON.stringify({ route, status });
  if (signature === navigationRenderSignature) return;
  for (const child of [...navigationGroup.children]) {
    navigationGroup.remove(child);
    disposeObject(child);
  }
  navigationRenderSignature = signature;
  canvas.dataset.navigationStatus = status;
  canvas.dataset.navigationReplans = String(runtimeNavigation?.replan_count ?? 0);
  canvas.dataset.navigationRouteRevision = String(runtimeNavigation?.route_revision ?? 0);
  if (route.length < 2) return;
  const color = status === 'blocked' ? 0xff4d4f
    : status === 'planning' ? 0xffbf3f
      : status === 'complete' ? 0x43d3a5 : 0x44c7f4;
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(
      route.map((point) => new THREE.Vector3(...point)),
    ),
    new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.9,
      depthTest: false,
    }),
  );
  line.renderOrder = 6;
  line.frustumCulled = false;
  navigationGroup.add(line);
  const routePoints = route.map((point) => new THREE.Vector3(...point));
  const routeDirection = new THREE.Vector3();
  const routeMidpoint = new THREE.Vector3();
  const up = new THREE.Vector3(0, 1, 0);
  for (let index = 0; index < routePoints.length - 1; index += 1) {
    const start = routePoints[index];
    const end = routePoints[index + 1];
    routeDirection.copy(end).sub(start);
    const length = routeDirection.length();
    if (length < 1e-6) continue;
    const ribbon = new THREE.Mesh(
      new THREE.CylinderGeometry(0.018, 0.018, length, 8, 1, true),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.42,
        depthTest: false,
        toneMapped: false,
      }),
    );
    ribbon.position.copy(routeMidpoint.copy(start).add(end).multiplyScalar(0.5));
    ribbon.quaternion.setFromUnitVectors(up, routeDirection.normalize());
    ribbon.renderOrder = 5;
    ribbon.frustumCulled = false;
    navigationGroup.add(ribbon);
  }
  for (const [index, point] of route.entries()) {
    const marker = new THREE.Mesh(
      new THREE.TorusGeometry(index === route.length - 1 ? 0.09 : 0.064, 0.012, 8, 24),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.92,
        depthTest: false,
        toneMapped: false,
      }),
    );
    marker.position.set(...point);
    marker.renderOrder = 7;
    marker.userData.navigationPulse = true;
    marker.userData.navigationPulsePhase = index * 0.65;
    navigationGroup.add(marker);
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
  const shouldFrameNewScene = previousActorIds.size === 0 && renderableActors.length > 1;
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
  updateShadowFrustum();
  syncAttachmentVisuals(currentScene);
  syncRangefinderVisuals(currentScene);
  syncNavigationVisual(currentScene);
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
  } else if (shouldFrameNewScene) {
    requestAnimationFrame(() => frameObject(actorGroup, viewDirections.iso.clone()));
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
  updateShadowFrustum();
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
  const nearestRange = simulationState?.sensors
    .filter((sensor): sensor is RangefinderSensorSample => (
      sensor.sensor_type === 'rangefinder' && sensor.hit
    ))
    .reduce((nearest, sensor) => Math.min(nearest, sensor.distance), Number.POSITIVE_INFINITY);
  const rangeText = nearestRange !== undefined && Number.isFinite(nearestRange)
    ? ` | clearance ${nearestRange.toFixed(2)} m`
    : '';
  const navigation = simulationState?.navigation;
  const navigationText = navigation && navigation.status !== 'idle'
    ? ` | nav ${navigation.status} · replans ${navigation.replan_count}`
    : '';
  requiredElement('#scene-name').textContent = currentScene.name;
  requiredElement('#scene-stats').textContent = `${currentScene.actors.length} actors${simText}${taskText}${rangeText}${navigationText}`;
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
  updateRangefinderVisuals();
  syncNavigationVisual(currentScene);
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

function setFocusBounds(object: any): void {
  if (object !== actorGroup) {
    focusBox.setFromObject(object);
    return;
  }
  focusBox.makeEmpty();
  for (const child of actorGroup.children) {
    const actor = child.userData.actor as Actor | undefined;
    if (actor?.properties.visual_style === 'operations_ground') continue;
    focusBox.expandByObject(child);
  }
  if (focusBox.isEmpty()) focusBox.setFromObject(actorGroup);
}

function frameObject(object: any, direction: any = null): void {
  if (!object || (object === actorGroup && actorGroup.children.length === 0)) return;
  setFocusBounds(object);
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

const viewportFrameInterval = 1000 / 45;
let lastViewportFrame = 0;

function animate(frameTime = performance.now()): void {
  requestAnimationFrame(animate);
  if (frameTime - lastViewportFrame < viewportFrameInterval) return;
  lastViewportFrame = frameTime;
  resize();
  const activeSky = cityEnvironmentVisible ? citySky : editorSky;
  activeSky.position.copy(camera.position);
  activeSky.scale.setScalar(Math.max(camera.far * 0.8, 500));
  const pulseTime = performance.now() * 0.0024;
  for (const marker of navigationGroup.children) {
    if (!marker.userData.navigationPulse) continue;
    const pulse = 1 + 0.12 * Math.sin(pulseTime + marker.userData.navigationPulsePhase);
    marker.scale.setScalar(pulse);
  }
  orbitControls.update();
  updateColliderDebugMarkers();
  updateAttachmentVisuals();
  updateRangefinderVisuals();
  updateSelectionOutline();
  renderer.render(scene, camera);
}

window.addEventListener('resize', resize);
resize();
animate();
