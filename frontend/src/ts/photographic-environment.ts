import * as THREE from '../vendor/three.module.js';

export async function loadPhotographicEnvironment(url: string): Promise<any> {
  const { RGBELoader } = await import('../vendor/RGBELoader.js');
  const loader = new RGBELoader();
  const texture = await loader.loadAsync(new URL(url, document.baseURI).href);
  texture.mapping = THREE.EquirectangularReflectionMapping;
  texture.colorSpace = THREE.LinearSRGBColorSpace;
  texture.name = 'Poly Haven: Abandoned Hopper Terminal 03';
  return texture;
}
