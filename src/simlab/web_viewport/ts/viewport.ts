import * as THREE from '../vendor/three.module.js';
import { OrbitControls } from '../vendor/OrbitControls.js';
import { TransformControls } from '../vendor/TransformControls.js';

import { sourceGeometry } from './geometry-contract.js';
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

transformControls.addEventListener('dragging-changed', (event) => {
  orbitControls.enabled = !event.value;
});

transformControls.addEventListener('mouseUp', () => {
  const object = transformControls.object;
  if (!object?.userData.actorId) return;
  const transform: Transform = {
    position: [object.position.x, object.position.y, object.position.z],
    rotation: [object.rotation.x, object.rotation.y, object.rotation.z],
    scale: [object.scale.x, object.scale.y, object.scale.z],
  };
  actorTransformCallback(object.userData.actorId, transform);
});

const grid = new THREE.GridHelper(20, 20, 0x4a5568, 0x2d3748);
grid.rotation.x = Math.PI / 2;
scene.add(grid);
scene.add(new THREE.AxesHelper(2));

const ambient = new THREE.HemisphereLight(0xffffff, 0x20242b, 1.6);
scene.add(ambient);

const keyLight = new THREE.DirectionalLight(0xffffff, 1.3);
keyLight.position.set(4, -5, 8);
scene.add(keyLight);

const actorGroup = new THREE.Group();
scene.add(actorGroup);

const selectionOutline = new THREE.BoxHelper(new THREE.Object3D(), 0xffd166);
selectionOutline.visible = false;
selectionOutline.material.depthTest = false;
selectionOutline.renderOrder = 10;
scene.add(selectionOutline);

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const actorMeshes = new Map<string, any>();
let selectedActorId: string | null = null;
let currentScene: Scene = {
  version: '1.0',
  name: 'Untitled Scene',
  units: 'meters',
  actors: [],
  simulation_config: { timestep: 0.01, duration: 1 },
};
let simulationState: SimulationState | null = null;
let colliderDebugVisible = false;
let sceneRevision = 0;
const focusBox = new THREE.Box3();
const focusSphere = new THREE.Sphere();
const viewDirections: Record<CameraView, any> = {
  iso: new THREE.Vector3(1, -1, 0.75).normalize(),
  front: new THREE.Vector3(0, -1, 0),
  right: new THREE.Vector3(1, 0, 0),
  top: new THREE.Vector3(0, 0, 1),
};
const materialVisuals: Record<string, { roughness: number; metalness: number }> = {
  default: { roughness: 0.55, metalness: 0.04 },
  rubber: { roughness: 0.86, metalness: 0 },
  wood: { roughness: 0.72, metalness: 0 },
  metal: { roughness: 0.24, metalness: 0.82 },
  ice: { roughness: 0.12, metalness: 0.08 },
};

export function configureViewport(callbacks: {
  onActorSelected: (actorId: string | null) => void;
  onActorTransformChanged: (actorId: string, transform: Transform) => void;
  resolveVisualGeometry: (cachePath: string) => Promise<VisualGeometryPayload | null>;
}): void {
  actorSelectedCallback = callbacks.onActorSelected;
  actorTransformCallback = callbacks.onActorTransformChanged;
  visualGeometryResolver = callbacks.resolveVisualGeometry;
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

function geometryFromPayload(payload: VisualGeometryPayload): any {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(payload.positions, 3));
  geometry.setIndex(payload.indices);
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function geometryForRobotVisual(visual: RobotVisualGeometry): any {
  const size = visual.size;
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

function addRobotActor(actor: Actor, articulation: RobotArticulation): any {
  const root = new THREE.Group();
  root.position.set(...actor.transform.position);
  root.rotation.set(...actor.transform.rotation);
  root.scale.set(...actor.transform.scale);
  root.name = actor.name;
  root.userData.actorId = actor.id;
  root.userData.actor = actor;
  const groups = new Map<string, any>();
  for (const link of articulation.links) {
    const group = new THREE.Group();
    group.name = link.name;
    group.position.set(...link.transform.position);
    group.quaternion.set(...link.transform.quaternion);
    group.userData.actorId = actor.id;
    group.userData.linkId = link.id;
    groups.set(link.id, group);
  }
  for (const link of articulation.links) {
    const group = groups.get(link.id);
    const parent = link.parent_link_id ? groups.get(link.parent_link_id) : root;
    parent?.add(group);
    for (const visual of link.visual_geometries) {
      const rgba = visual.rgba ?? [0.7, 0.7, 0.7, 1];
      const mesh = new THREE.Mesh(
        geometryForRobotVisual(visual),
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
    child.material?.dispose();
  });
}

function clearActors(): void {
  transformControls.detach();
  selectionOutline.visible = false;
  actorMeshes.clear();
  while (actorGroup.children.length > 0) {
    const child = actorGroup.children.pop();
    if (child) disposeObject(child);
  }
}

export function setViewportScene(sceneData: Scene): void {
  const revision = ++sceneRevision;
  currentScene = sceneData;
  clearActors();
  for (const actor of currentScene.actors) {
    if (actor.type === 'robot') {
      const articulationIds = actor.properties.articulation_ids as string[] | undefined;
      const articulation = currentScene.robotics?.articulations.find(
        (item) => articulationIds?.includes(item.id),
      );
      if (!articulation) continue;
      const robot = addRobotActor(actor, articulation);
      actorGroup.add(robot);
      actorMeshes.set(actor.id, robot);
      continue;
    }
    if (actor.type !== 'object') continue;
    const mesh = new THREE.Mesh(geometryForActor(actor), materialForActor(actor));
    mesh.position.set(...actor.transform.position);
    mesh.rotation.set(...actor.transform.rotation);
    mesh.scale.set(...actor.transform.scale);
    mesh.name = actor.name;
    mesh.userData.actorId = actor.id;
    mesh.userData.actor = actor;
    addColliderDebug(mesh, actor);
    actorGroup.add(mesh);
    actorMeshes.set(actor.id, mesh);
    const cachePath = actor.properties.geometry?.visual_cache;
    if (cachePath) {
      void visualGeometryResolver(cachePath).then((payload) => {
        if (!payload || revision !== sceneRevision || actorMeshes.get(actor.id) !== mesh) return;
        mesh.geometry.dispose();
        mesh.geometry = geometryFromPayload(payload);
        rebuildColliderDebug(mesh, actor);
        updateSelectionOutline();
      });
    }
  }
  selectViewportActor(selectedActorId, false);
  if (simulationState) applySimulationState(simulationState);
  updateHud();
}

export function selectViewportActor(actorId: string | null, notify = false): void {
  selectedActorId = actorId;
  for (const [id, object] of actorMeshes.entries()) {
    object.traverse((mesh) => {
      if (!mesh.material?.emissive) return;
      mesh.material.emissive = new THREE.Color(id === selectedActorId ? 0x2b6cb0 : 0);
      mesh.material.emissiveIntensity = id === selectedActorId ? 0.45 : 0;
    });
  }
  const selectedMesh = selectedActorId ? actorMeshes.get(selectedActorId) : null;
  if (selectedMesh && !simulationState) transformControls.attach(selectedMesh);
  else transformControls.detach();
  updateSelectionOutline();
  updateHud();
  if (notify) actorSelectedCallback(actorId);
}

function updateHud(): void {
  const selected = currentScene.actors.find((actor) => actor.id === selectedActorId);
  const simText = simulationState ? ` | sim t=${simulationState.time.toFixed(3)}` : '';
  requiredElement('#scene-name').textContent = currentScene.name;
  requiredElement('#scene-stats').textContent = `${currentScene.actors.length} actors${simText}`;
  const colliderState = selected && colliderDebugVisible
    ? ` | ${actorIsDynamic(selected) ? 'Dynamic' : 'Static'} collider`
    : '';
  const materialState = selected?.properties.physics?.material
    ? ` | ${selected.properties.physics.material}`
    : '';
  requiredElement('#selection').textContent = `Selected: ${selected?.name ?? 'None'}${colliderState}${materialState}`;
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
  updateSelectionOutline();
  updateHud();
}

function updateSelectionOutline(): void {
  const selectedMesh = selectedActorId ? actorMeshes.get(selectedActorId) : null;
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
  if (selectedMesh && !simulationState) transformControls.attach(selectedMesh);
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
  return (selectedActorId ? actorMeshes.get(selectedActorId) : null) ?? actorGroup;
}

function frameObject(object: any, direction: any = null): void {
  if (!object || (object === actorGroup && actorGroup.children.length === 0)) return;
  focusBox.setFromObject(object);
  if (focusBox.isEmpty()) return;
  focusBox.getBoundingSphere(focusSphere);
  const radius = Math.max(focusSphere.radius, 0.35);
  const viewDirection = direction ?? camera.position.clone().sub(orbitControls.target).normalize();
  if (viewDirection.lengthSq() < 0.0001) viewDirection.copy(viewDirections.iso);
  const distance = Math.max(radius / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2), 2.5);
  orbitControls.target.copy(focusSphere.center);
  camera.position.copy(focusSphere.center).add(viewDirection.multiplyScalar(distance * 1.35));
  camera.near = Math.max(distance / 1000, 0.01);
  camera.far = Math.max(distance * 100, 1000);
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

renderer.domElement.addEventListener('pointerdown', (event: PointerEvent) => {
  if (transformControls.dragging) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects([...actorMeshes.values()], true);
  selectViewportActor(hits[0]?.object?.userData.actorId ?? null, true);
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
  orbitControls.update();
  updateColliderDebugMarkers();
  updateSelectionOutline();
  renderer.render(scene, camera);
}

window.addEventListener('resize', resize);
resize();
animate();
