const aliases = {
    primitive_box: 'box',
    primitive_sphere: 'sphere',
    primitive_cylinder: 'cylinder',
    primitive_ground: 'box',
    box: 'box',
    sphere: 'sphere',
    cylinder: 'cylinder',
    ellipsoid: 'ellipsoid',
    ground: 'plane',
    plane: 'plane',
};
const defaults = {
    box: [0.5, 0.5, 0.5],
    sphere: [0.5],
    cylinder: [0.5, 0.5],
    ellipsoid: [0.5, 0.5, 0.5],
    plane: [5, 5, 0.1],
};
export function sourceGeometry(actor) {
    const primitive = actor.properties.primitive;
    const geomType = aliases[String(primitive)] ?? aliases[actor.asset_id];
    if (!geomType) {
        throw new Error(`Unsupported primitive: ${primitive ?? actor.asset_id}`);
    }
    return { geomType, size: [...(actor.properties.size ?? defaults[geomType])] };
}
export function colliderGeometry(actor) {
    const source = sourceGeometry(actor);
    const scale = actor.transform.scale;
    if (source.geomType === 'box' || source.geomType === 'ellipsoid') {
        return {
            geomType: source.geomType,
            size: source.size.map((value, index) => value * scale[index]),
        };
    }
    if (source.geomType === 'sphere') {
        const radii = scale.map((value) => source.size[0] * value);
        const uniform = Math.abs(radii[0] - radii[1]) < 1e-9
            && Math.abs(radii[1] - radii[2]) < 1e-9;
        return { geomType: uniform ? 'sphere' : 'ellipsoid', size: uniform ? [radii[0]] : radii };
    }
    if (source.geomType === 'cylinder') {
        if (Math.abs(scale[0] - scale[1]) > 1e-9) {
            throw new Error('Cylinder X and Y scale must match');
        }
        return {
            geomType: 'cylinder',
            size: [source.size[0] * scale[0], source.size[1] * scale[2]],
        };
    }
    return {
        geomType: 'plane',
        size: [source.size[0] * scale[0], source.size[1] * scale[1], source.size[2]],
    };
}
