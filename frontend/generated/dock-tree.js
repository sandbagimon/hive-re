// Binary dock layout tree — pure logic ported from the new_ui_ref design.
//
// A workspace is a tree of splits (row/column with fractional sizes) whose
// leaves are tab stacks of panels. Every mutation returns a new tree; ad-hoc
// empty leaves are pruned while named workspace slots retain their geometry.
/**
 * Named workspace slots are kept even when their last tab closes. Collapsing
 * these structural leaves would make the viewport jump in size whenever a
 * utility window is opened or removed.
 */
const STABLE_SLOT_IDS = new Set([
    'left-top', 'left-bottom', 'center-top', 'center-bottom', 'right-top', 'right-bottom',
    'left', 'center', 'right', 'right-a', 'right-b', 'right-c',
]);
let uidCounter = 0;
export function uid(prefix) {
    uidCounter += 1;
    return `${prefix}-${uidCounter}`;
}
export function leaf(id, panels, active = panels[0]) {
    return { type: 'leaf', id, panels, active };
}
export function split(id, direction, sizes, children) {
    return { type: 'split', id, direction, sizes: normalize(sizes), children };
}
export function normalize(sizes) {
    const total = sizes.reduce((sum, value) => sum + value, 0) || 1;
    return sizes.map((value) => value / total);
}
export function collectPanels(node, out = []) {
    if (node.type === 'leaf')
        out.push(...node.panels);
    else
        node.children.forEach((child) => collectPanels(child, out));
    return out;
}
export function findLeafOf(node, panel) {
    if (node.type === 'leaf')
        return node.panels.includes(panel) ? node : null;
    for (const child of node.children) {
        const found = findLeafOf(child, panel);
        if (found)
            return found;
    }
    return null;
}
export function findLeafById(node, leafId) {
    if (node.type === 'leaf')
        return node.id === leafId ? node : null;
    for (const child of node.children) {
        const found = findLeafById(child, leafId);
        if (found)
            return found;
    }
    return null;
}
export function firstLeafId(node) {
    return node.type === 'leaf' ? node.id : firstLeafId(node.children[0]);
}
function mapNode(node, fn) {
    const next = fn(node);
    if (next.type === 'split') {
        return { ...next, children: next.children.map((child) => mapNode(child, fn)) };
    }
    return next;
}
function stripPanel(node, panel) {
    return mapNode(node, (n) => {
        if (n.type !== 'leaf' || !n.panels.includes(panel))
            return n;
        const panels = n.panels.filter((item) => item !== panel);
        const active = n.active === panel ? panels[0] ?? null : n.active;
        return { ...n, panels, active };
    });
}
/** Removes ad-hoc empty leaves and collapses splits with a single child. */
export function prune(node) {
    if (node.type === 'leaf') {
        return node.panels.length || STABLE_SLOT_IDS.has(node.id) ? node : null;
    }
    const kept = node.children
        .map((child, index) => ({ child: prune(child), size: node.sizes[index] ?? 1 }))
        .filter((item) => item.child !== null);
    if (kept.length === 0)
        return null;
    if (kept.length === 1)
        return kept[0].child;
    return {
        ...node,
        children: kept.map((item) => item.child),
        sizes: normalize(kept.map((item) => item.size)),
    };
}
export function setActive(root, leafId, panel) {
    return mapNode(root, (n) => (n.type === 'leaf' && n.id === leafId && n.panels.includes(panel)
        ? { ...n, active: panel }
        : n));
}
export function removePanel(root, panel) {
    return prune(stripPanel(root, panel));
}
export function addPanelToLeaf(root, leafId, panel) {
    return mapNode(root, (n) => {
        if (n.type !== 'leaf' || n.id !== leafId)
            return n;
        if (n.panels.includes(panel))
            return { ...n, active: panel };
        return { ...n, panels: [...n.panels, panel], active: panel };
    });
}
function splitLeaf(leafNode, panel, zone) {
    const direction = zone === 'left' || zone === 'right' ? 'row' : 'column';
    const incoming = { type: 'leaf', id: uid('leaf'), panels: [panel], active: panel };
    const before = zone === 'left' || zone === 'top';
    return {
        type: 'split',
        id: uid('split'),
        direction,
        sizes: [0.5, 0.5],
        children: before ? [incoming, leafNode] : [leafNode, incoming],
    };
}
function insertAt(node, panel, targetLeafId, zone) {
    if (node.type === 'leaf') {
        if (node.id !== targetLeafId)
            return node;
        if (zone === 'center') {
            return node.panels.includes(panel)
                ? { ...node, active: panel }
                : { ...node, panels: [...node.panels, panel], active: panel };
        }
        return splitLeaf(node, panel, zone);
    }
    return { ...node, children: node.children.map((child) => insertAt(child, panel, targetLeafId, zone)) };
}
/** Detach the panel from wherever it lives, then insert at the target leaf/zone. */
export function dropPanel(root, panel, targetLeafId, zone) {
    const stripped = stripPanel(root, panel);
    const inserted = insertAt(stripped, panel, targetLeafId, zone);
    return prune(inserted) ?? leaf(uid('leaf'), [panel]);
}
export function resizeSplit(root, splitId, index, deltaFraction) {
    return mapNode(root, (n) => {
        if (n.type !== 'split' || n.id !== splitId)
            return n;
        const sizes = [...n.sizes];
        const min = 0.08;
        const a = sizes[index] + deltaFraction;
        const b = sizes[index + 1] - deltaFraction;
        if (a < min || b < min)
            return n;
        sizes[index] = a;
        sizes[index + 1] = b;
        return { ...n, sizes };
    });
}
/** Five-zone hit test relative to a leaf body rect (edge = 22%). */
export function zoneFor(rect, clientX, clientY) {
    const rx = (clientX - rect.left) / rect.width;
    const ry = (clientY - rect.top) / rect.height;
    const edge = 0.22;
    const dist = [
        ['left', rx],
        ['right', 1 - rx],
        ['top', ry],
        ['bottom', 1 - ry],
    ];
    dist.sort((a, b) => a[1] - b[1]);
    return dist[0][1] < edge ? dist[0][0] : 'center';
}
// ---------------------------------------------------------------- presets
/**
 * Keep the initial viewport close to the pre-dock editor's pixel footprint.
 * The previous shell used 238 px / 286 px fixed sidebars. The dock shell adds
 * its own padding, splitters and leaf borders, so 230 px / 278 px produces the
 * same viewport canvas width. Below desktop width the side regions yield first
 * so the viewport keeps at least ~500 px whenever possible.
 */
function defaultRootSizes() {
    const viewportWidth = typeof window === 'undefined' ? 1440 : window.innerWidth;
    const usable = Math.max(1, viewportWidth - 14);
    const sideScale = Math.min(1, Math.max(0, (usable - 500) / (230 + 278)));
    const left = 230 * sideScale;
    const right = 278 * sideScale;
    return normalize([left, Math.max(1, usable - left - right), right]);
}
/**
 * Reserve only the height needed for the compact diagnostics tab strip. This
 * compensates for the new header, status bar and dock chrome, leaving the
 * viewport canvas almost exactly as tall as it was before the redesign.
 */
function defaultCenterSizes() {
    const viewportHeight = typeof window === 'undefined' ? 900 : window.innerHeight;
    const usable = Math.max(1, viewportHeight - 75);
    const diagnostics = Math.min(90, Math.max(60, usable - 320));
    return normalize([Math.max(1, usable - diagnostics), diagnostics]);
}
/**
 * Default workspace: viewport dominates the centre, authoring on the left,
 * inspection on the right, logs and diagnostics along the bottom.
 */
export function createDefaultLayout() {
    return split('root', 'row', defaultRootSizes(), [
        split('left-col', 'column', [0.44, 0.56], [
            leaf('left-top', ['scene-tree']),
            leaf('left-bottom', ['assets', 'project'], 'assets'),
        ]),
        split('center-col', 'column', defaultCenterSizes(), [
            leaf('center-top', ['viewport']),
            leaf('center-bottom', ['console', 'validation', 'recording'], 'console'),
        ]),
        split('right-col', 'column', [0.34, 0.66], [
            leaf('right-top', ['sim-control', 'sim-speed'], 'sim-control'),
            leaf('right-bottom', ['properties', 'agent', 'materials', 'arm-control'], 'properties'),
        ]),
    ]);
}
export const LAYOUT_PRESETS = [
    { id: 'default', label: 'Default', build: createDefaultLayout },
    {
        id: 'authoring',
        label: 'Scene Authoring',
        build: () => split('root', 'row', [0.22, 0.56, 0.22], [
            split('left-col', 'column', [0.5, 0.5], [
                leaf('left-top', ['assets']),
                leaf('left-bottom', ['scene-tree']),
            ]),
            leaf('center', ['viewport']),
            split('right-col', 'column', [0.42, 0.58], [
                leaf('right-a', ['properties']),
                leaf('right-b', ['materials', 'arm-control']),
            ]),
        ]),
    },
    {
        id: 'motion',
        label: 'Motion & Control',
        build: () => split('root', 'row', [0.26, 0.46, 0.28], [
            leaf('left', ['arm-control', 'drone-control'], 'arm-control'),
            split('center-col', 'column', [0.62, 0.38], [
                leaf('center-top', ['viewport']),
                leaf('center-bottom', ['trajectory-editor', 'controller'], 'trajectory-editor'),
            ]),
            split('right-col', 'column', [0.3, 0.7], [
                leaf('right-a', ['sim-speed', 'sim-control']),
                leaf('right-b', ['properties', 'materials']),
            ]),
        ]),
    },
    {
        id: 'telemetry',
        label: 'Telemetry & Capture',
        build: () => split('root', 'row', [0.44, 0.56], [
            split('left-col', 'column', [0.55, 0.45], [
                leaf('left-top', ['viewport']),
                leaf('left-bottom', ['console', 'validation'], 'console'),
            ]),
            split('right-col', 'column', [0.5, 0.5], [
                leaf('right-a', ['sensors']),
                leaf('right-b', ['recording', 'controller'], 'recording'),
            ]),
        ]),
    },
];
/** Leaf that auto-opened panels join when they have no home yet. */
export const FALLBACK_LEAF_ID = 'center-bottom';
