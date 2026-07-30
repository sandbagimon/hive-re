const MAGIC = 'SIMGEOM1';

type Slice = [offset: number, count: number];

interface GeometryBundleHeaderEntry {
  positions: Slice;
  indices: Slice;
  normals: Slice;
  colors?: Slice;
  uvs?: Slice;
  bounds: {
    min: [number, number, number];
    max: [number, number, number];
    sphere: [number, number, number, number];
  };
}

interface GeometryBundleHeader {
  format: 'simlab-geometry-bundle';
  version: 1;
  geometries: Record<string, GeometryBundleHeaderEntry>;
}

export interface BundledGeometry {
  positions: Float32Array;
  indices: Uint32Array;
  normals: Float32Array;
  colors: Uint8Array | null;
  uvs: Float32Array | null;
  bounds: GeometryBundleHeaderEntry['bounds'];
}

const align4 = (value: number): number => (value + 3) & ~3;

const validateSlice = (
  slice: Slice,
  elementBytes: number,
  payloadStart: number,
  byteLength: number,
): number => {
  const [offset, count] = slice;
  if (!Number.isSafeInteger(offset) || !Number.isSafeInteger(count) || offset < 0 || count < 0) {
    throw new Error('Geometry bundle contains an invalid buffer slice');
  }
  const absoluteOffset = payloadStart + offset;
  if (absoluteOffset % elementBytes !== 0 || absoluteOffset + count * elementBytes > byteLength) {
    throw new Error('Geometry bundle buffer slice is out of range');
  }
  return absoluteOffset;
};

export function decodeGeometryBundle(buffer: ArrayBuffer): Map<string, BundledGeometry> {
  if (buffer.byteLength < 12) throw new Error('Geometry bundle is truncated');
  const magic = new TextDecoder().decode(new Uint8Array(buffer, 0, 8));
  if (magic !== MAGIC) throw new Error('Geometry bundle has invalid magic');
  const headerLength = new DataView(buffer).getUint32(8, true);
  const headerEnd = 12 + headerLength;
  if (headerEnd > buffer.byteLength) throw new Error('Geometry bundle header is truncated');
  const header = JSON.parse(
    new TextDecoder().decode(new Uint8Array(buffer, 12, headerLength)),
  ) as GeometryBundleHeader;
  if (header.format !== 'simlab-geometry-bundle' || header.version !== 1) {
    throw new Error('Unsupported geometry bundle format');
  }
  const payloadStart = align4(headerEnd);
  const output = new Map<string, BundledGeometry>();
  for (const [geometryId, entry] of Object.entries(header.geometries)) {
    const positionOffset = validateSlice(entry.positions, 4, payloadStart, buffer.byteLength);
    const indexOffset = validateSlice(entry.indices, 4, payloadStart, buffer.byteLength);
    const normalOffset = validateSlice(entry.normals, 4, payloadStart, buffer.byteLength);
    const colorOffset = entry.colors
      ? validateSlice(entry.colors, 1, payloadStart, buffer.byteLength)
      : null;
    const uvOffset = entry.uvs
      ? validateSlice(entry.uvs, 4, payloadStart, buffer.byteLength)
      : null;
    output.set(geometryId, {
      positions: new Float32Array(buffer, positionOffset, entry.positions[1]),
      indices: new Uint32Array(buffer, indexOffset, entry.indices[1]),
      normals: new Float32Array(buffer, normalOffset, entry.normals[1]),
      colors: colorOffset === null
        ? null
        : new Uint8Array(buffer, colorOffset, entry.colors![1]),
      uvs: uvOffset === null
        ? null
        : new Float32Array(buffer, uvOffset, entry.uvs![1]),
      bounds: entry.bounds,
    });
  }
  return output;
}
