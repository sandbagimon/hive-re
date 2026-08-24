const MAGIC = 'SIMGEOM1';
const align4 = (value) => (value + 3) & ~3;
const validateSlice = (slice, elementBytes, payloadStart, byteLength) => {
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
export function decodeGeometryBundle(buffer) {
    if (buffer.byteLength < 12)
        throw new Error('Geometry bundle is truncated');
    const magic = new TextDecoder().decode(new Uint8Array(buffer, 0, 8));
    if (magic !== MAGIC)
        throw new Error('Geometry bundle has invalid magic');
    const headerLength = new DataView(buffer).getUint32(8, true);
    const headerEnd = 12 + headerLength;
    if (headerEnd > buffer.byteLength)
        throw new Error('Geometry bundle header is truncated');
    const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 12, headerLength)));
    if (header.format !== 'beefoundrysim-geometry-bundle' || header.version !== 1) {
        throw new Error('Unsupported geometry bundle format');
    }
    const payloadStart = align4(headerEnd);
    const output = new Map();
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
        const instanceOffset = entry.instances
            ? validateSlice(entry.instances, 4, payloadStart, buffer.byteLength)
            : null;
        if (entry.instances && (!entry.instances[1] || entry.instances[1] % 16 !== 0)) {
            throw new Error('Geometry bundle contains invalid instance matrices');
        }
        output.set(geometryId, {
            positions: new Float32Array(buffer, positionOffset, entry.positions[1]),
            indices: new Uint32Array(buffer, indexOffset, entry.indices[1]),
            normals: new Float32Array(buffer, normalOffset, entry.normals[1]),
            colors: colorOffset === null
                ? null
                : new Uint8Array(buffer, colorOffset, entry.colors[1]),
            uvs: uvOffset === null
                ? null
                : new Float32Array(buffer, uvOffset, entry.uvs[1]),
            materialId: entry.material ?? null,
            instanceMatrices: instanceOffset === null
                ? null
                : new Float32Array(buffer, instanceOffset, entry.instances[1]),
            bounds: entry.bounds,
        });
    }
    return output;
}
