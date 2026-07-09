import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { TransformControls } from './vendor/TransformControls.js';

const canvas = document.querySelector('#viewport');
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
transformControls.setMode('translate');
transformControls.setSpace('world');
scene.add(transformControls);

transformControls.addEventListener('dragging-changed', (event) => {
  orbitControls.enabled = !event.value;
});

transformControls.addEventListener('mouseUp', () => {
  const object = transformControls.object;
  if (!object || !object.userData.actorId || !window.simlabBridge) {
    return;
  }
  const transform = object.userData.transform;
  transform.position = [object.position.x, object.position.y, object.position.z];
  window.simlabBridge.updateActorTransform(object.userData.actorId, JSON.stringify(transform));
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

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const actorMeshes = new Map();
let selectedActorId = null;
let currentScene = { name: 'Untitled Scene', actors: [] };

function resize() {
  const width = canvas.clientWidth || window.innerWidth;
  const height = canvas.clientHeight || window.innerHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / Math.max(height, 1);
  camera.updateProjectionMatrix();
}

window.addEventListener('resize', resize);

function materialForActor(actor) {
  const rgba = actor.properties?.rgba || [0.55, 0.62, 0.7, 1.0];
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(rgba[0], rgba[1], rgba[2]),
    roughness: 0.55,
    metalness: 0.04,
    transparent: rgba[3] < 1.0,
    opacity: rgba[3],
  });
}

function geometryForActor(actor) {
  const primitive = actor.properties?.primitive || actor.asset_id;
  const size = actor.properties?.size || [0.5, 0.5, 0.5];
  if (primitive.includes('sphere')) {
    return new THREE.SphereGeometry(size[0] || 0.5, 40, 24);
  }
  if (primitive.includes('cylinder')) {
    const radius = size[0] || 0.35;
    const height = size[1] || 0.8;
    const geometry = new THREE.CylinderGeometry(radius, radius, height, 40);
    geometry.rotateX(Math.PI / 2);
    return geometry;
  }
  const x = (size[0] || 0.5) * 2;
  const y = (size[1] || 0.5) * 2;
  const z = (size[2] || 0.5) * 2;
  return new THREE.BoxGeometry(x, y, z);
}

function clearActors() {
  transformControls.detach();
  actorMeshes.clear();
  while (actorGroup.children.length > 0) {
    const child = actorGroup.children.pop();
    child.geometry?.dispose();
    child.material?.dispose();
  }
}

function setScene(sceneData) {
  currentScene = sceneData || { name: 'Untitled Scene', actors: [] };
  clearActors();

  for (const actor of currentScene.actors || []) {
    if (actor.type !== 'object') {
      continue;
    }
    const mesh = new THREE.Mesh(geometryForActor(actor), materialForActor(actor));
    const position = actor.transform?.position || [0, 0, 0];
    const rotation = actor.transform?.rotation || [0, 0, 0];
    const scale = actor.transform?.scale || [1, 1, 1];
    mesh.position.set(position[0], position[1], position[2]);
    mesh.rotation.set(rotation[0], rotation[1], rotation[2]);
    mesh.scale.set(scale[0], scale[1], scale[2]);
    mesh.name = actor.name;
    mesh.userData.actorId = actor.id;
    mesh.userData.transform = {
      position: [...position],
      rotation: [...rotation],
      scale: [...scale],
    };
    actorGroup.add(mesh);
    actorMeshes.set(actor.id, mesh);
  }

  selectActor(selectedActorId, false);
  updateHud();
}

function selectActor(actorId, notifyPython = true) {
  selectedActorId = actorId || null;
  for (const [id, mesh] of actorMeshes.entries()) {
    mesh.material.emissive = new THREE.Color(id === selectedActorId ? 0x2b6cb0 : 0x000000);
    mesh.material.emissiveIntensity = id === selectedActorId ? 0.45 : 0;
  }
  const selectedMesh = actorMeshes.get(selectedActorId);
  if (selectedMesh) {
    transformControls.attach(selectedMesh);
  } else {
    transformControls.detach();
  }
  updateHud();
  if (notifyPython && selectedActorId && window.simlabBridge) {
    window.simlabBridge.selectActor(selectedActorId);
  }
}

function updateHud() {
  const actors = currentScene.actors || [];
  const selected = actors.find((actor) => actor.id === selectedActorId);
  document.querySelector('#scene-name').textContent = currentScene.name || 'Untitled Scene';
  document.querySelector('#scene-stats').textContent = `${actors.length} actors`;
  document.querySelector('#selection').textContent = `Selected: ${selected?.name || 'None'}`;
}

function onPointerDown(event) {
  if (transformControls.dragging) {
    return;
  }
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects([...actorMeshes.values()], false);
  selectActor(hits[0]?.object?.userData?.actorId || null);
}

renderer.domElement.addEventListener('pointerdown', onPointerDown);

function animate() {
  requestAnimationFrame(animate);
  resize();
  orbitControls.update();
  renderer.render(scene, camera);
}

new QWebChannel(qt.webChannelTransport, (channel) => {
  window.simlabBridge = channel.objects.simlabBridge;
  window.simlabViewportReady = true;
  if (window.simlabBridge?.viewportReady) {
    window.simlabBridge.viewportReady();
  }
});

window.simlabViewport = {
  setSceneFromJson(sceneJson) {
    setScene(JSON.parse(sceneJson));
  },
  selectActor(actorId) {
    selectActor(actorId || null, false);
  },
};

resize();
animate();
